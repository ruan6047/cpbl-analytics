"""GAME-RECAP-PA1-BUILD1：canonical 打席 [plate appearance / PA] 批次 builder。

依 [[GAME-RECAP-PA1_CONTRACT]] 與 TAXONOMY1（消費 ``docs/design/pa_transition_taxonomy.v1.json``，
taxonomy_version=1.1.0）把來源 revision 物化為 deterministic、持久化的 ``pa_id``、event
membership 與 ordered pitch mapping，寫入 EXPAND1（migration 066）建的表。

設計（供跨家族查核者複核）:

* **純核心 + 薄 DB 層**：island 偵測、分類、``pa_id`` 生成、fingerprint、逐球映射、
  reconciliation 全為純函式（對 event/pitch dict list 操作，無 DB），便於紅燈測試；
  DB 層只做 fetch/upsert/atomic publish。
* **island 語意不重定義**：分組規則對齊 TAXONOMY1 ``island_rule``（連續同
  ``(inning, half, hitter)``、換人列附掛不切界、``main_event_no::bigint`` 全序），
  **但打者變化不等於打席變化**——打席中途代打換人不切界，見
  :func:`continues_same_plate_appearance`（FIX1）；
  ``tests/test_pa_builder.py`` 有 conformance 測試釘住與 ``scripts.pa_transition_taxonomy``
  ``_island_starts`` 的一致性，杜絕語意漂移。分類 role/outcome_family 直接讀版本化 JSON。
* **狀態數值不信來源欄位**：``pre_state``／``post_state`` 的 outs 由
  :func:`derive_half_inning_outs` 自 ``content`` 敘述推導，不讀會落後的 ``out_cnt``（FIX1）。
* **打席可跨兩位打者**：代打中途接替時 ``hitter_acnt`` 依記錄規則 9.15(b) 決定記錄歸屬、
  ``end_hitter_acnt`` 記實際完成者，見 :func:`charged_hitter`（FIX1，migration 068）。
* **不變式 fail closed**：任一半局的打者出局 PA > 3 → 整場不 publish，
  見 :func:`half_inning_out_violations`（FIX1）。
* **穩定 ``pa_id``**：deterministic UUIDv5，seed = ``year|kind|game|start_event_no|event_order_version``；
  同一 start 事件跨 build/revision 產生相同 ``pa_id``（契約不變量 #1/#2）。
* **逐球映射**：pitch_tracking ``(pitcher_acnt, pitch_cnt)`` 全場逐投手唯一，映射靠
  member event ``(pitcher_acnt, pitch_cnt, hitter_acnt)`` 對齊（牽制列沿用前 pitch_cnt 但
  hitter 可能已換人 → 用 hitter 排除跨 PA 誤綁）。候選相異島 >1 或投打不一致 → ``failed``
  （契約紅燈：每顆球至多綁定一個 PA）。
* **reconciliation / fail closed**：晚到或修正 revision 先比對既有 published build 的
  ``pa_id`` × PA fingerprint；有變更 → 產出 ``reconciliation_required`` build（**不** publish、
  **不** 刪舊、**不** 換 ID），保留舊 published 供稽核；完全等價才 atomic swap 發布。

紅線: 逐球來源 (pitch_tracking) **唯讀**；不改逐球 parser／refresh 正式路徑／schema。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from cpbl.ingest.game_source_revisions import canonical_source_version

log = logging.getLogger("cpbl.pa_build")

Event = dict[str, Any]
Pitch = dict[str, Any]

# ---------------------------------------------------------------------------
# 版本 pin（改動任一者都會改變 build 身分；pa_id seed 只含 event_order_version）
# ---------------------------------------------------------------------------
BUILDER_VERSION = "pa-build-1.2.0"  # FIX1：代打續打席合併 + outs 推導 + 出局不變式 + 9.15(b) 歸屬
EVENT_ORDER_VERSION = "evord-1.0"  # main_event_no::bigint 嚴格全序
# 固定 UUIDv5 namespace（勿更動：更動會使全部 pa_id 漂移）。
PA_ID_NAMESPACE = uuid.UUID("5f3b9d2a-1c47-5e60-9a8b-6d2f0c1e7a44")

_TAXONOMY_FILENAME = "pa_transition_taxonomy.v1.json"


def _default_taxonomy_path() -> Path:
    """解析 taxonomy JSON 路徑。

    優先用**隨 wheel 打包**的 package data（``src/cpbl/resources/``→ 安裝後
    ``site-packages/cpbl/resources/``），使生產容器（Dockerfile 只 COPY src，不含 repo
    ``docs/``）也能載入；本機 editable／repo 佈局則退回 canonical ``docs/design/``。
    （不用 ``data/`` 目錄名：專案 .gitignore 忽略 ``data/``，會使檔案未被 commit／打包。）
    """
    packaged = Path(__file__).resolve().parent.parent / "resources" / _TAXONOMY_FILENAME
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[3] / "docs" / "design" / _TAXONOMY_FILENAME


_TAXONOMY_PATH = _default_taxonomy_path()

# PA state（對齊 migration 066 CHECK 值域）
STATE_READY = "ready"
STATE_UNRELIABLE = "unreliable"
STATE_TRUNCATED = "truncated"
STATE_NON_PA = "non_pa"
STATE_RECONCILIATION = "reconciliation_required"

# tracking_availability（契約固定 public 值域）
AVAIL_AVAILABLE = "available"
AVAIL_SOURCE_MISSING = "source_missing"
AVAIL_MAPPING_FAILED = "mapping_failed"


# ===========================================================================
# taxonomy 消費
# ===========================================================================
@dataclass(frozen=True)
class Taxonomy:
    version: str
    actions: dict[str, dict[str, str]]  # action_name -> {role, outcome_family}

    def entry(self, action_name: str) -> dict[str, str] | None:
        return self.actions.get(action_name)


@lru_cache(maxsize=1)
def load_taxonomy(path: str | None = None) -> Taxonomy:
    """讀版本化 taxonomy JSON（builder 消費前置產物，不重定義語意）。"""
    p = Path(path) if path else _TAXONOMY_PATH
    doc = json.loads(p.read_text(encoding="utf-8"))
    actions = {
        a["action_name"]: {"role": a["role"], "outcome_family": a.get("outcome_family", "")}
        for a in doc["actions"]
    }
    return Taxonomy(version=str(doc["taxonomy_version"]), actions=actions)


# ===========================================================================
# 純核心：排序、fingerprint、pa_id
# ===========================================================================
def event_sort_key(event: Event) -> tuple[int, str]:
    """main_event_no::bigint 嚴格全序（非數字排最後，再以字串 tie-break）。"""
    raw = str(event.get("main_event_no") or "")
    if raw.isdigit():
        return (0, f"{int(raw):020d}")
    return (1, raw)


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    return text or None


def event_fingerprint(event: Event) -> str:
    """事件顯著欄位雜湊；晚到/修正比對用。含結果與狀態欄位，排除 name 冗餘。"""
    significant = {
        "main_event_no": str(event.get("main_event_no") or ""),
        "inning_seq": _clean(event.get("inning_seq")),
        "visiting_home_type": _clean(event.get("visiting_home_type")),
        "batting_order": _clean(event.get("batting_order")),
        "hitter_acnt": _clean(event.get("hitter_acnt")),
        "pitcher_acnt": _clean(event.get("pitcher_acnt")),
        "pitch_cnt": _clean(event.get("pitch_cnt")),
        "out_cnt": _clean(event.get("out_cnt")),
        "ball_cnt": _clean(event.get("ball_cnt")),
        "strike_cnt": _clean(event.get("strike_cnt")),
        "action_name": _clean(event.get("action_name")),
        "batting_action_name": _clean(event.get("batting_action_name")),
        "content": _clean(event.get("content")),
        "is_score": bool(event.get("is_score")),
        "is_change_player": bool(event.get("is_change_player")),
        "is_special_event": bool(event.get("is_special_event")),
        "first_base": _clean(event.get("first_base")),
        "second_base": _clean(event.get("second_base")),
        "third_base": _clean(event.get("third_base")),
        "visiting_score": _clean(event.get("visiting_score")),
        "home_score": _clean(event.get("home_score")),
    }
    return canonical_source_version(significant)


def pa_seed(year: int, kind_code: str, game_sno: int, start_event_no: str) -> str:
    return f"{year}|{kind_code}|{game_sno}|{start_event_no}|{EVENT_ORDER_VERSION}"


def pa_id_for(year: int, kind_code: str, game_sno: int, start_event_no: str) -> uuid.UUID:
    """deterministic UUIDv5：同 start 事件跨 build/revision 相同（契約不變量 #1/#2）。"""
    return uuid.uuid5(PA_ID_NAMESPACE, pa_seed(year, kind_code, game_sno, start_event_no))


# ===========================================================================
# 純核心：island 偵測（對齊 TAXONOMY1 island_rule）
# ===========================================================================
def _usable(event: Event) -> bool:
    return not event.get("is_change_player") and bool(_clean(event.get("hitter_acnt")))


PINCH_HIT_MARKER = "更換代打"


def _count_of(event: Event) -> tuple[int | None, int | None]:
    b, s = event.get("ball_cnt"), event.get("strike_cnt")
    return (
        int(b) if b not in (None, "") else None,
        int(s) if s not in (None, "") else None,
    )


def _last_member(island: list[Event]) -> Event | None:
    """island 中最後一個非換人成員列（換人列不帶球數/棒次可比對資訊）。"""
    for ev in reversed(island):
        if not ev.get("is_change_player"):
            return ev
    return None


def _trailing_change_rows(island: list[Event]) -> list[Event]:
    """附掛在 island 尾端（最後一個成員列之後）的換人公告列。"""
    trailing: list[Event] = []
    for ev in reversed(island):
        if not ev.get("is_change_player"):
            break
        trailing.append(ev)
    return trailing


def continues_same_plate_appearance(island: list[Event], event: Event) -> str | None:
    """判定「打者變化」是否為**同一打席內的代打換人**，而非新打席開始。

    為什麼需要這條規則：livelog 的 ``action_name`` 是**打席層級的最終結果，被複製到
    該打席的每一列**（證據：``2018/A/116`` 的 ``0720010000``／``0720011000`` 在三振
    發生前就已標 ``三振``）。而打席中途換代打會使 ``hitter_acnt`` 在打席內就改變，
    若照打者切界，兩段碎片會各自被 ``_terminal_event`` 取到**同一個被複製的結果**，
    同一打席被記成兩個 PA、同一個出局被記兩次（全庫 303 對，見 GAME-RECAP-PA1-FIX1）。

    **必要條件**：兩段同一 ``batting_order``（livelog 語意＝該半局第幾位打者；代打接替
    不另開棒次槽，換下一位打者才會進位）。棒次槽前進即為兩個真打席，一律切界。

    在該必要條件上，下列任一佐證成立即視為同一打席：

    * ``count_continues``：新打者首列球數 ≥2 且相對前一列未回退。此判準**不要求公告列**
      ——官方偶有漏記代打公告（``2023/A/73`` 8 局下）；``batting_order`` 為 0 的早年資料
      只要兩段同為 0 仍適用（``2020/A/239`` 3 局上）。
    * ``pinch_hit_slot``：有 ``更換代打`` 公告列，**且**原打者未面對任何真實投球
      （只有牽制／公告列）或球數未回退。

    **為什麼球數不能單獨成立**（iteration 1 查核 Critical，實證推翻）：原先假設
    「新打席首列球數必 ≤1」，實測**為假**——部分來源列的球數在換打者時不歸零：
    ``2021/D/64`` 6 局下棒次 5 於 1-1 結束（「2人出局。」），棒次 6 首列是 **2-1**；
    ``2018/A/4`` 棒次 11 的 (1,0) 接棒次 12 的 (2,0)。全母體有 7 對這種假象，
    若只看球數會合併兩個真打席（違反紅線 1）。棒次槽是擋住它們的必要條件。

    不得合併的邊界（查核重點）：**零投球故意四壞完成的打席 + 緊接著的打席間代打**
    （``2018/A/9`` 9 局上、``2018/A/16`` 8 局下）——棒次槽已前進，兩條佐證皆不適用。
    """
    prev = _last_member(island)
    if prev is None:
        return None
    bo_a, bo_b = prev.get("batting_order"), event.get("batting_order")
    if bo_a is None or bo_b is None or bo_a != bo_b:
        return None
    b_a, s_a = _count_of(prev)
    b_b, s_b = _count_of(event)
    non_decreasing = False
    if b_a is not None and s_a is not None and b_b is not None and s_b is not None:
        non_decreasing = b_b >= b_a and s_b >= s_a
        if non_decreasing and b_b + s_b >= 2:
            return "count_continues"
    if not any(PINCH_HIT_MARKER in str(c.get("content") or "")
               for c in _trailing_change_rows(island)):
        return None
    if not bo_a:  # batting_order=0 是早年資料的缺值哨兵，不足以單獨支撐弱佐證
        return None
    if not any(_is_real_pitch(ev) for ev in island):
        return "pinch_hit_slot"
    return "pinch_hit_slot" if non_decreasing else None


def build_islands(events: list[Event]) -> list[list[Event]]:
    """把逐事件切成 island（候選 PA）。

    語意對齊 TAXONOMY1 ``island_rule``：
    * 換人列 (``is_change_player``) 與空 hitter 列不 seed／不切界，附掛於當前 island。
    * 以 ``(inning_seq, visiting_home_type, hitter_acnt)`` 變化切界，**但**同半局內的
      打者變化若經 :func:`continues_same_plate_appearance` 判定為打席中途代打換人，
      則不切界（FIX1；打者變化不等於打席變化）。
    * 事件先以 ``main_event_no::bigint`` 全序排序。
    """
    ordered = sorted(events, key=event_sort_key)
    islands: list[list[Event]] = []
    prev_key: tuple[Any, str, Any] | None = None
    for ev in ordered:
        if not _usable(ev):
            if islands:  # 換人／空 hitter 列附掛於當前 PA，不切界、不 seed
                islands[-1].append(ev)
            continue
        key = (
            ev.get("inning_seq"),
            str(ev.get("visiting_home_type")),
            _clean(ev.get("hitter_acnt")),
        )
        if key != prev_key:
            same_half = prev_key is not None and key[:2] == prev_key[:2]
            if (islands and same_half
                    and continues_same_plate_appearance(islands[-1], ev)):
                prev_key = key  # 代打續打席：沿用當前 island，只更新打者
            else:
                islands.append([])
                prev_key = key
        islands[-1].append(ev)
    return islands


# ===========================================================================
# 純核心：island 分類（島 → island_class → PA state）
# ===========================================================================
def _terminal_event(island: list[Event]) -> Event | None:
    """終結事件 = 事件序中最後一個非換人、action 非空的成員事件。"""
    for ev in reversed(island):
        if ev.get("is_change_player"):
            continue
        if _clean(ev.get("action_name")):
            return ev
    return None


def _distinct_pitches(island: list[Event]) -> int:
    return len({
        int(ev["pitch_cnt"])
        for ev in island
        if ev.get("pitch_cnt") not in (None, "") and int(ev["pitch_cnt"]) > 0
    })


@dataclass(frozen=True)
class IslandClass:
    island_class: str  # completed_pa / truncated_fragment / non_pa_tiebreak / non_pa_running_fragment / unknown_action
    state: str         # migration 066 PA state
    result_action: str | None
    outcome_family: str | None


def classify_island(island: list[Event], taxonomy: Taxonomy) -> IslandClass:
    """把 island 歸入 canonical 分類並映射為 PA state（fail-closed）。

    對齊 TAXONOMY1 ``island_classes`` 與 migration 066 state 映射：
      completed_pa            → ready       （登錄 pa_terminal；含無投球 award）
      unknown_action          → unreliable  （有 action 未登錄 → fail closed）
      truncated_fragment      → truncated   （空 action 但有投球）
      non_pa_tiebreak         → non_pa      （突破僵局跑者）
      non_pa_running_fragment → non_pa      （空 action 無投球純跑壘殘列）
    """
    terminal = _terminal_event(island)
    action = _clean(terminal.get("action_name")) if terminal else None
    has_pitch = _distinct_pitches(island) > 0

    if not action:
        if has_pitch:
            return IslandClass("truncated_fragment", STATE_TRUNCATED, None, None)
        return IslandClass("non_pa_running_fragment", STATE_NON_PA, None, None)

    entry = taxonomy.entry(action)
    if entry is None:
        # 有 action 但未登錄 taxonomy → fail closed（保留成員事件，state=unreliable）
        return IslandClass("unknown_action", STATE_UNRELIABLE, action, None)
    if entry["role"] == "non_pa":
        return IslandClass("non_pa_tiebreak", STATE_NON_PA, action, entry.get("outcome_family"))
    # pa_terminal：無投球但為 award（故意四壞/妨礙打擊）仍是完成 PA。
    return IslandClass("completed_pa", STATE_READY, action, entry.get("outcome_family"))


# ===========================================================================
# 純核心：把 island 物化為 PlateAppearance
# ===========================================================================
def _occupied_bases(event: Event) -> list[str]:
    bases = []
    for slot, name in (("first_base", "1"), ("second_base", "2"), ("third_base", "3")):
        if _clean(event.get(slot)):
            bases.append(name)
    return bases


_OUT_MARKER = re.compile(r"([0-9])人出局")


def derive_half_inning_outs(events: list[Event]) -> dict[str, tuple[int, int]]:
    """逐事件推導 ``(該事件前, 該事件後)`` 的半局累計出局數。

    權威來源是 livelog ``content`` 的「N人出局」敘述（＝該事件**後**的半局累計出局數），
    **不是** ``out_cnt`` 欄位——後者會落後：全庫 328,508 個有真實投球的 island 中
    2,157 個（0.657%）與本推導值不一致，差值 ``-1`` 佔 2,148 例
    （見 GAME-RECAP-PA1-FIX1）。推導值自身可對帳：71,023 個半局收在恰好 3 出局。

    半局界線以 ``(inning_seq, visiting_home_type)`` 變化判定。累計值取 ``max`` 保持
    單調（出局數不可能減少），使單一敘述異常不會讓後續事件整段偏移。
    """
    derived: dict[str, tuple[int, int]] = {}
    running = 0
    prev_half: tuple[Any, str] | None = None
    for ev in sorted(events, key=event_sort_key):
        half = (ev.get("inning_seq"), str(ev.get("visiting_home_type")))
        if half != prev_half:
            running = 0
            prev_half = half
        before = running
        marks = _OUT_MARKER.findall(str(ev.get("content") or ""))
        if marks:
            running = max(running, max(int(m) for m in marks))
        derived[str(ev.get("main_event_no"))] = (before, running)
    return derived


def _state_snapshot(event: Event, outs: int | None) -> dict[str, Any]:
    """PA 邊界狀態快照。``outs`` 由 :func:`derive_half_inning_outs` 提供（不讀 out_cnt）。"""
    return {
        "inning": _clean(event.get("inning_seq")),
        "half": _clean(event.get("visiting_home_type")),
        "outs": outs,
        "bases": _occupied_bases(event),
        "away_score": _clean(event.get("visiting_score")),
        "home_score": _clean(event.get("home_score")),
    }


def compute_pa_fingerprint(
    *,
    members: list[str],
    hitter: str | None,
    start_pitcher: str | None,
    end_pitcher: str | None,
    result_action: str | None,
    start_event_no: str | None,
    end_event_no: str | None,
    end_hitter: str | None = None,
) -> str:
    """PA 內容指紋的單一實作；新 build 與 published 重建共用，杜絕算法漂移。"""
    return canonical_source_version({
        "members": list(members),
        "hitter": hitter,
        "end_hitter": end_hitter,
        "start_pitcher": start_pitcher,
        "end_pitcher": end_pitcher,
        "result_action": result_action,
        "start_event_no": start_event_no,
        "end_event_no": end_event_no,
    })


@dataclass
class MemberEvent:
    event_no: str
    event_position: int
    fingerprint: str


@dataclass
class PlateAppearance:
    pa_id: uuid.UUID
    pa_index: int
    year: int
    kind_code: str
    game_sno: int
    start_event_no: str
    end_event_no: str | None
    hitter_acnt: str | None       # 記錄歸屬打者（記錄規則 9.15(b)）
    end_hitter_acnt: str | None   # 實際完成打席者（無代打接替時同上）
    start_pitcher_acnt: str | None
    end_pitcher_acnt: str | None
    state: str
    island_class: str
    result_action: str | None
    outcome_family: str | None
    pre_state: dict[str, Any]
    post_state: dict[str, Any]
    members: list[MemberEvent]
    # 逐球映射前置：本 PA 內「真實投球」member 的 (pitcher_acnt, pitch_cnt, hitter, min_event_no)
    pitch_slots: list[tuple[str, int, str, str]] = field(default_factory=list)
    tracking_availability: str | None = None
    reconciliation_reason: str | None = None

    def pa_fingerprint(self) -> str:
        """PA 內容指紋（reconciliation 比對）：成員指紋序 + 投打身份 + 起訖事件 + 終結 action。

        只由「published build 已儲存的欄位」組成，故可自 DB 無損重建
        （見 ``compute_pa_fingerprint``）；不含 build-assigned state（state 會在
        reconciliation 中被改寫，不屬來源內容身分）。
        """
        return compute_pa_fingerprint(
            members=[m.fingerprint for m in self.members],
            hitter=self.hitter_acnt,
            end_hitter=self.end_hitter_acnt,
            start_pitcher=self.start_pitcher_acnt,
            end_pitcher=self.end_pitcher_acnt,
            result_action=self.result_action,
            start_event_no=self.start_event_no,
            end_event_no=self.end_event_no,
        )


STRIKEOUT_ACTIONS = frozenset({
    "三振", "三振/妨礙", "三振/第三好球觸擊失敗", "三振/遭捕手傳一壘刺殺", "裁定三振",
})
# 不死三振（outcome_family=uncaught_third_strike）**刻意不列入**：9.15(a)(3) 雖記三振，
# 但擊球員成為跑壘員，屬 9.15(b)「其他結果」與否規則未明文；全母體目前**零實例**，
# 故採不套用第一句（歸完成者）並在此標記，待有實例時由規則層裁定，不以推測套用真實資料。


def charged_hitter(members: list[Event], result_action: str | None) -> tuple[str | None, str | None]:
    """依記錄規則 9.15(b) 回傳 ``(記錄歸屬打者, 完成打席者)``。

    規則原文（``docs/reference/棒球規則.txt`` 9.15(b)）：「擊球員於第 2 好球後退出，
    替代的擊球員以三振完成打擊，記為**最初擊球員**的三振與打數，若替代擊球員以其他結果
    完成打擊（包括四壞球），皆視為**該替代擊球員**之行為。」
    【註】「同一打席中分別由 3 位球員替換出場打擊，最後被三振時，其中**被判第 2 好球**之
    擊球員，應被記為三振及打數。」——故三振時取「球數首次達 2 好球那一列」的打者，
    不是無條件取最初擊球員（本語料目前無 3 人以上的實例，仍照規則實作）。

    無代打接替（島內只有一位打者）時兩者相同。
    """
    hitters = [h for h in (_clean(e.get("hitter_acnt")) for e in members) if h]
    if not hitters:
        return None, None
    completing = hitters[-1]
    if result_action not in STRIKEOUT_ACTIONS or len(set(hitters)) < 2:
        return completing, completing
    for ev in members:
        sc = ev.get("strike_cnt")
        if sc not in (None, "") and int(sc) >= 2:
            return (_clean(ev.get("hitter_acnt")) or completing), completing
    return completing, completing


def _is_real_pitch(event: Event) -> bool:
    """真實投球 member 列：pitch_cnt>0 且 (好球或壞球)。牽制/暫停列 is_strike=is_ball=false。"""
    if event.get("is_change_player"):
        return False
    pc = event.get("pitch_cnt")
    if pc in (None, "") or int(pc) <= 0:
        return False
    return bool(event.get("is_strike")) or bool(event.get("is_ball"))


def plate_appearances(
    year: int, kind_code: str, game_sno: int, events: list[Event], taxonomy: Taxonomy
) -> list[PlateAppearance]:
    """把單場逐事件物化為有序 PlateAppearance list（純函式）。"""
    islands = build_islands(events)
    outs_by_event = derive_half_inning_outs(events)
    pas: list[PlateAppearance] = []
    for pa_index, island in enumerate(islands):
        ordered = sorted(island, key=event_sort_key)
        non_change = [e for e in ordered if not e.get("is_change_player")]
        start_ev = non_change[0] if non_change else ordered[0]
        start_event_no = str(start_ev.get("main_event_no"))
        cls = classify_island(ordered, taxonomy)
        terminal = _terminal_event(ordered)

        members = [
            MemberEvent(
                event_no=str(ev.get("main_event_no")),
                event_position=pos,
                fingerprint=event_fingerprint(ev),
            )
            for pos, ev in enumerate(ordered)
        ]

        # 真實投球 slot（逐球映射用）：dedupe (pitcher, pitch_cnt)，保留最早 event_no
        slot_min: dict[tuple[str, int], tuple[str, str]] = {}
        for ev in ordered:
            if not _is_real_pitch(ev):
                continue
            pitcher = _clean(ev.get("pitcher_acnt"))
            hitter = _clean(ev.get("hitter_acnt"))
            if not pitcher or not hitter:
                continue
            key = (pitcher, int(ev["pitch_cnt"]))
            ev_no = str(ev.get("main_event_no"))
            prev = slot_min.get(key)
            if prev is None or event_sort_key({"main_event_no": ev_no}) < event_sort_key(
                {"main_event_no": prev[1]}
            ):
                slot_min[key] = (hitter, ev_no)
        pitch_slots = sorted(
            [(p, pc, h, ev_no) for (p, pc), (h, ev_no) in slot_min.items()],
            key=lambda s: event_sort_key({"main_event_no": s[3]}),
        )

        pitchers_in_order = [
            _clean(e.get("pitcher_acnt")) for e in non_change if _clean(e.get("pitcher_acnt"))
        ]
        # 打席可跨兩位打者（代打中途接替）：記錄歸屬依 9.15(b)，完成者另存。
        charged, completing = charged_hitter(non_change, cls.result_action)
        pas.append(
            PlateAppearance(
                pa_id=pa_id_for(year, kind_code, game_sno, start_event_no),
                pa_index=pa_index,
                year=year,
                kind_code=kind_code,
                game_sno=game_sno,
                start_event_no=start_event_no,
                end_event_no=str(terminal.get("main_event_no")) if terminal else None,
                hitter_acnt=charged, end_hitter_acnt=completing,
                start_pitcher_acnt=pitchers_in_order[0] if pitchers_in_order else None,
                end_pitcher_acnt=pitchers_in_order[-1] if pitchers_in_order else None,
                state=cls.state,
                island_class=cls.island_class,
                result_action=cls.result_action,
                outcome_family=cls.outcome_family,
                # pre＝起始事件「前」、post＝終結事件「後」的半局累計出局數
                pre_state=_state_snapshot(
                    start_ev, outs_by_event.get(start_event_no, (None, None))[0]
                ),
                post_state=_state_snapshot(
                    terminal,
                    outs_by_event.get(str(terminal.get("main_event_no")), (None, None))[1],
                ) if terminal else {},
                members=members,
                pitch_slots=pitch_slots,
            )
        )
    return pas


# ===========================================================================
# 純核心：逐球映射
# ===========================================================================
@dataclass
class PitchMapping:
    pa_index: int  # 綁定的 PA（pas list 索引）
    pitcher_acnt: str
    pitch_cnt: int
    pitch_position: int
    mapping_state: str  # mapped / failed
    mapping_reason: str | None


@dataclass
class PitchPlan:
    mappings: list[PitchMapping]
    mapped: int
    failed: int
    orphan: int  # 無任何 PA 成員擁有的逐球（fail closed，不虛構歸屬）
    orphan_samples: list[dict[str, Any]] = field(default_factory=list)


def plan_pitch_mappings(pas: list[PlateAppearance], pitches: list[Pitch]) -> PitchPlan:
    """把 pitch_tracking 逐球對應到 PA（純函式）。

    ownership：pitch (pitcher, pitch_cnt, hitter) 對齊 PA 的 ``pitch_slots``。
    * 恰好一個相異 PA 擁有 → 該 PA ready 則 ``mapped``；PA 非 ready 則 ``failed``。
    * >1 相異 PA → ``failed`` (ambiguous_candidate)，綁定最早的 PA（每球仍至多一個 PA）。
    * 0 PA 擁有 → orphan（不產生 mapping 列；FK 需 pa_row_id）。
    """
    # 建 (pitcher, pitch_cnt, hitter) -> set(pa_index) 索引
    owner_index: dict[tuple[str, int, str], list[int]] = defaultdict(list)
    for idx, pa in enumerate(pas):
        for pitcher, pc, hitter, _ev_no in pa.pitch_slots:
            owner_index[(pitcher, pc, hitter)].append(idx)

    # 每 PA 的映射（先收集，最後按 pitch order 指派 pitch_position）
    per_pa: dict[int, list[tuple[str, int, str | None]]] = defaultdict(list)
    orphan = 0
    orphan_samples: list[dict[str, Any]] = []
    for pitch in pitches:
        pitcher = _clean(pitch.get("pitcher_acnt"))
        hitter = _clean(pitch.get("hitter_acnt"))
        pc_raw = pitch.get("pitch_cnt")
        if not pitcher or pc_raw in (None, ""):
            orphan += 1
            if len(orphan_samples) < 20:
                orphan_samples.append({"pitcher_acnt": pitcher, "pitch_cnt": pc_raw,
                                       "reason": "missing_key"})
            continue
        pc = int(pc_raw)
        owners = owner_index.get((pitcher, pc, hitter), [])
        distinct_owners = sorted(set(owners))
        if not distinct_owners:
            orphan += 1
            if len(orphan_samples) < 20:
                orphan_samples.append({"pitcher_acnt": pitcher, "pitch_cnt": pc,
                                       "hitter_acnt": hitter, "reason": "no_pa_member"})
            continue
        if len(distinct_owners) > 1:
            per_pa[distinct_owners[0]].append((pitcher, pc, "ambiguous_candidate"))
            continue
        pa_idx = distinct_owners[0]
        pa = pas[pa_idx]
        if pa.state == STATE_READY:
            per_pa[pa_idx].append((pitcher, pc, None))  # mapped（reason 稍後補）
        else:
            per_pa[pa_idx].append((pitcher, pc, f"pa_not_ready:{pa.state}"))

    mappings: list[PitchMapping] = []
    mapped = failed = 0
    for pa_idx, pitch_list in per_pa.items():
        pa = pas[pa_idx]
        # pitch order 依 PA pitch_slots 的事件序（跨換投正確）；未在 slot 者退回 pitch_cnt
        slot_order = {(p, pc): i for i, (p, pc, _h, _e) in enumerate(pa.pitch_slots)}
        ordered = sorted(
            pitch_list, key=lambda t: (slot_order.get((t[0], t[1]), 10**9), t[0], t[1])
        )
        # 順序倒退偵測：同投手 pitch_cnt 應隨 position 遞增
        last_pc_by_pitcher: dict[str, int] = {}
        for position, (pitcher, pc, reason) in enumerate(ordered):
            state = "failed" if reason else "mapped"
            eff_reason = reason
            if state == "mapped":
                prev = last_pc_by_pitcher.get(pitcher)
                if prev is not None and pc <= prev:
                    state, eff_reason = "failed", "order_regression"
                else:
                    last_pc_by_pitcher[pitcher] = pc
            if state == "mapped":
                mapped += 1
            else:
                failed += 1
            mappings.append(
                PitchMapping(pa_index=pa_idx, pitcher_acnt=pitcher, pitch_cnt=pc,
                             pitch_position=position, mapping_state=state,
                             mapping_reason=eff_reason)
            )
    return PitchPlan(mappings=mappings, mapped=mapped, failed=failed,
                     orphan=orphan, orphan_samples=orphan_samples)


def assign_tracking_availability(
    pas: list[PlateAppearance], plan: PitchPlan, game_has_tracking: bool
) -> None:
    """設定每個 PA 的 tracking_availability（in-place）。

    * 無逐球來源 → source_missing (reason=source_not_collected)。
    * 有逐球來源：全部期望投球 mapped 且無 failed → available；否則 mapping_failed。
    * 無設備 (no_equipment) 需 STATUS1 正證據，本 builder 不由「未觀測到」推論。
    """
    per_pa_mapped: Counter = Counter()
    per_pa_failed: Counter = Counter()
    per_pa_reason: dict[int, str] = {}
    for m in plan.mappings:
        if m.mapping_state == "mapped":
            per_pa_mapped[m.pa_index] += 1
        else:
            per_pa_failed[m.pa_index] += 1
            per_pa_reason.setdefault(m.pa_index, m.mapping_reason or "mapping_failed")

    for idx, pa in enumerate(pas):
        if pa.state == STATE_NON_PA:
            continue  # 非 PA：不設 availability
        if not game_has_tracking:
            pa.tracking_availability = AVAIL_SOURCE_MISSING
            if not pa.reconciliation_reason:
                pa.reconciliation_reason = "source_not_collected"
            continue
        expected = len(pa.pitch_slots)
        mapped = per_pa_mapped.get(idx, 0)
        failed = per_pa_failed.get(idx, 0)
        if failed == 0 and mapped >= expected:
            pa.tracking_availability = AVAIL_AVAILABLE
        else:
            pa.tracking_availability = AVAIL_MAPPING_FAILED
            if not pa.reconciliation_reason:
                pa.reconciliation_reason = per_pa_reason.get(idx, "partial_pitch_coverage")


# ===========================================================================
# 純核心：不變式（fail closed）
# ===========================================================================
MAX_OUT_PA_PER_HALF_INNING = 3
INVARIANT_OUT_OVERFLOW = "half_inning_out_overflow"
# 打者出局的 outcome_family。fielders_choice／uncaught_third_strike 打者上壘、
# 出局記在跑者身上，不計入——本不變式刻意寬鬆（雙殺打只算 1 筆 out-PA 卻製造 2 個
# 出局），只在**物理上不可能**時觸發，不會因邊界口徑誤殺。
BATTER_OUT_FAMILIES = frozenset({"out", "sacrifice"})


def half_inning_out_violations(pas: list[PlateAppearance]) -> list[dict[str, Any]]:
    """不變式：任一半局的「打者出局 PA」不得超過 3 筆（一個半局最多 3 個出局）。

    違反代表打席切分或結果分類有誤——不是可容忍的雜訊，故 :func:`build_game`
    以此**逐場 fail closed**（該場不 publish、保留舊 published 供稽核），不只記 log。

    已知會違反的真實案例只有 ``2019/A/173``：來源列 ``0110002000`` 的 ``inning_seq``
    誤標成 7（應為 1）且 ``0110001000`` 帶 ``action_name=三振``（該打席實際是四壞球），
    屬**來源資料損壞**。正確處置是隔離該場，**不得加白名單繞過**。
    """
    counts: Counter = Counter()
    for pa in pas:
        if pa.state != STATE_READY or pa.outcome_family not in BATTER_OUT_FAMILIES:
            continue
        inning, half = pa.pre_state.get("inning"), pa.pre_state.get("half")
        if inning is None or half is None:
            continue
        counts[(inning, str(half))] += 1
    return [
        {"inning": inning, "half": half, "out_pa": n}
        for (inning, half), n in sorted(counts.items(), key=lambda kv: str(kv[0]))
        if n > MAX_OUT_PA_PER_HALF_INNING
    ]


def apply_invariant_states(
    pas: list[PlateAppearance], violations: list[dict[str, Any]]
) -> None:
    """把違反半局的 PA 標為 ``unreliable``（in-place）。呼叫端負責整場不 publish。"""
    if not violations:
        return
    bad = {(v["inning"], str(v["half"])) for v in violations}
    for pa in pas:
        key = (pa.pre_state.get("inning"), str(pa.pre_state.get("half")))
        if key in bad and pa.state in (STATE_READY, STATE_TRUNCATED):
            pa.state = STATE_UNRELIABLE
            pa.reconciliation_reason = INVARIANT_OUT_OVERFLOW


# ===========================================================================
# 純核心：reconciliation
# ===========================================================================
@dataclass
class ReconcileResult:
    action: str  # publish | reconcile | noop
    changed_pa_ids: list[str] = field(default_factory=list)
    added_pa_ids: list[str] = field(default_factory=list)
    removed_pa_ids: list[str] = field(default_factory=list)
    builder_upgrade: bool = False  # 差異歸因於 builder/taxonomy 進版而非來源漂移


def reconcile(
    new_pas: list[PlateAppearance],
    published: dict[str, str] | None,
    *,
    builder_upgrade_same_source: bool = False,
) -> ReconcileResult:
    """比對新 PA 與既有 published build（``pa_id -> pa_fingerprint``）。

    * 無 published → ``publish``（首次 canonical）。
    * 完全等價（相同 pa_id 集合 + 相同 fingerprint） → ``publish``（乾淨重建，atomic swap）。
    * 任一 PA 成員／投打／終點變更、或有新增／消失 pa_id → ``reconcile``：
      產出 reconciliation_required build，**不** publish、**不** 動舊 published（契約不變量 #3）。

    ``builder_upgrade_same_source`` 是唯一例外，且**不削弱 fail closed**：
    reconciliation 的用途是攔截**來源漂移**，不是攔截 builder 升級。呼叫端只有在
    新舊 build 的 ``livelog_revision_id``／``tracking_revision_id`` **完全相同**
    （來源 manifest 由 sha256 決定，相同即來源逐列未變）而 ``builder_version``／
    ``taxonomy_version`` 不同時才可傳 ``True``——此時 fingerprint 變更**只可能**
    來自我們對來源的解讀改變。來源一旦有任何變動，此旗標即為 ``False``，
    行為與過去完全一致（fail closed）。差異仍逐筆記入 ``validation_summary`` 供稽核。
    """
    if not published:
        return ReconcileResult(action="publish")

    new_map = {str(pa.pa_id): pa.pa_fingerprint() for pa in new_pas}
    new_ids = set(new_map)
    old_ids = set(published)

    changed = [pid for pid in (new_ids & old_ids) if new_map[pid] != published[pid]]
    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)

    if not changed and not added and not removed:
        return ReconcileResult(action="publish")
    return ReconcileResult(
        action="publish" if builder_upgrade_same_source else "reconcile",
        changed_pa_ids=sorted(changed), added_pa_ids=added, removed_pa_ids=removed,
        builder_upgrade=builder_upgrade_same_source,
    )


def apply_reconciliation_states(new_pas: list[PlateAppearance], result: ReconcileResult) -> None:
    """reconcile 時把變更／新增的 PA 標為 reconciliation_required（in-place，fail closed）。

    不變式違反（``half_inning_out_overflow``）優先：那是「資料本身錯了」的判定，
    強於「與既有發布不一致」的簿記，不得被覆寫。
    """
    if result.action != "reconcile":
        return
    flagged = set(result.changed_pa_ids) | set(result.added_pa_ids)
    for pa in new_pas:
        if pa.reconciliation_reason == INVARIANT_OUT_OVERFLOW:
            continue
        if str(pa.pa_id) in flagged and pa.state in (STATE_READY, STATE_UNRELIABLE,
                                                      STATE_TRUNCATED):
            pa.state = STATE_RECONCILIATION
            pa.reconciliation_reason = (
                "membership_changed" if str(pa.pa_id) in set(result.changed_pa_ids)
                else "late_added_pa"
            )


# ===========================================================================
# DB 層：fetch / source manifest / atomic publish / build_game / backfill
# ===========================================================================
PARSER_VERSION = "pa-build-read-1.0"  # builder 讀取/物化契約版本（非重新解析原始 HTML）

_EVENT_COLS = (
    "year, kind_code, game_sno, main_event_no, inning_seq, visiting_home_type, "
    "batting_order, out_cnt, ball_cnt, strike_cnt, pitch_cnt, content, action_name, "
    "batting_action_name, hitter_acnt, pitcher_acnt, first_base, second_base, third_base, "
    "is_strike, is_ball, is_score, is_change_player, is_special_event, visiting_score, home_score"
)

_PITCH_COLS = (
    "year, kind_code, game_sno, pitcher_acnt, pitch_cnt, hitter_acnt, inning_seq, "
    "ball_cnt, strike_cnt, out_cnt, batting_order, pitch_call, content"
)


def _fetch_events(cur: Any, year: int, kind: str, game: int) -> list[Event]:
    cur.execute(
        f"SELECT {_EVENT_COLS} FROM cpbl.game_livelog "  # noqa: S608 (固定欄位常數，非使用者輸入)
        "WHERE year=%s AND kind_code=%s AND game_sno=%s",
        (year, kind, game),
    )
    return [dict(r) for r in cur.fetchall()]


def _fetch_pitches(cur: Any, year: int, kind: str, game: int) -> list[Pitch]:
    cur.execute(
        f"SELECT {_PITCH_COLS} FROM cpbl.pitch_tracking "  # noqa: S608
        "WHERE year=%s AND kind_code=%s AND game_sno=%s",
        (year, kind, game),
    )
    return [dict(r) for r in cur.fetchall()]


def _livelog_manifest(events: list[Event]) -> tuple[str, int, str | None]:
    """(sha256, row_count, max_source_key=max main_event_no)。"""
    ordered = sorted(events, key=event_sort_key)
    sha = canonical_source_version([event_fingerprint(e) for e in ordered])
    max_key = str(ordered[-1].get("main_event_no")) if ordered else None
    return sha, len(ordered), max_key


def _pitch_identity(pitch: Pitch) -> dict[str, Any]:
    return {
        "pitcher_acnt": _clean(pitch.get("pitcher_acnt")),
        "pitch_cnt": _clean(pitch.get("pitch_cnt")),
        "hitter_acnt": _clean(pitch.get("hitter_acnt")),
        "inning_seq": _clean(pitch.get("inning_seq")),
        "ball_cnt": _clean(pitch.get("ball_cnt")),
        "strike_cnt": _clean(pitch.get("strike_cnt")),
        "out_cnt": _clean(pitch.get("out_cnt")),
        "pitch_call": _clean(pitch.get("pitch_call")),
        "content": _clean(pitch.get("content")),
    }


def _tracking_manifest(pitches: list[Pitch]) -> tuple[str, int, str | None]:
    ordered = sorted(
        pitches,
        key=lambda p: (str(p.get("pitcher_acnt") or ""), int(p.get("pitch_cnt") or 0)),
    )
    sha = canonical_source_version([_pitch_identity(p) for p in ordered])
    if ordered:
        last = ordered[-1]
        max_key = f"{last.get('pitcher_acnt')}:{last.get('pitch_cnt')}"
    else:
        max_key = None
    return sha, len(ordered), max_key


def upsert_source_revision(
    cur: Any, *, year: int, kind: str, game: int, source_kind: str,
    sha256: str, row_count: int, max_source_key: str | None,
) -> int:
    """冪等寫入 immutable source manifest；同 (game, kind, hash) 回既有 id。"""
    cur.execute(
        """
        INSERT INTO cpbl.game_recap_source_revisions
            (year, kind_code, game_sno, source_kind, source_sha256, parser_version,
             row_count, max_source_key)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (year, kind_code, game_sno, source_kind, source_sha256)
        DO UPDATE SET row_count = EXCLUDED.row_count
        RETURNING id
        """,
        (year, kind, game, source_kind, sha256, PARSER_VERSION, row_count, max_source_key),
    )
    return int(cur.fetchone()["id"])


def _published_build_meta(cur: Any, year: int, kind: str, game: int) -> dict[str, Any] | None:
    """既有 published build 的身分欄位（判定 fingerprint 差異可否歸因於 builder 升級）。"""
    cur.execute(
        """
        SELECT build_id, builder_version, taxonomy_version,
               livelog_revision_id, tracking_revision_id
        FROM cpbl.game_recap_builds
        WHERE year=%s AND kind_code=%s AND game_sno=%s AND state='published'
        """,
        (year, kind, game),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _published_pa_fingerprints(cur: Any, year: int, kind: str, game: int) -> dict[str, str]:
    """讀既有 published build 的 PA → {pa_id: pa_fingerprint}（自儲存欄位無損重建）。"""
    cur.execute(
        """
        SELECT pa.pa_id, pa.hitter_acnt, pa.end_hitter_acnt,
               pa.start_pitcher_acnt, pa.end_pitcher_acnt,
               pa.result_action, pa.start_event_no, pa.end_event_no,
               COALESCE(array_agg(e.event_fingerprint ORDER BY e.event_position)
                        FILTER (WHERE e.event_fingerprint IS NOT NULL), '{}') AS member_fps
        FROM cpbl.game_plate_appearances pa
        JOIN cpbl.game_recap_builds b
          ON b.build_id = pa.build_id AND b.state = 'published'
        LEFT JOIN cpbl.game_pa_events e ON e.pa_row_id = pa.pa_row_id
        WHERE pa.year=%s AND pa.kind_code=%s AND pa.game_sno=%s
        GROUP BY pa.pa_row_id, pa.pa_id, pa.hitter_acnt, pa.end_hitter_acnt,
                 pa.start_pitcher_acnt,
                 pa.end_pitcher_acnt, pa.result_action, pa.start_event_no, pa.end_event_no
        """,
        (year, kind, game),
    )
    out: dict[str, str] = {}
    for r in cur.fetchall():
        out[str(r["pa_id"])] = compute_pa_fingerprint(
            members=list(r["member_fps"]),
            hitter=r["hitter_acnt"],
            end_hitter=r["end_hitter_acnt"],
            start_pitcher=r["start_pitcher_acnt"],
            end_pitcher=r["end_pitcher_acnt"],
            result_action=r["result_action"],
            start_event_no=r["start_event_no"],
            end_event_no=r["end_event_no"],
        )
    return out


def _existing_equivalent_build(
    cur: Any, *, year: int, kind: str, game: int,
    livelog_rev: int, tracking_rev: int | None,
) -> dict[str, Any] | None:
    """同 (game, livelog_rev, tracking_rev, builder, taxonomy) 的既有 build（冪等重跑用）。"""
    cur.execute(
        """
        SELECT build_id, state FROM cpbl.game_recap_builds
        WHERE year=%s AND kind_code=%s AND game_sno=%s
          AND livelog_revision_id=%s
          AND tracking_revision_id IS NOT DISTINCT FROM %s
          AND builder_version=%s AND taxonomy_version=%s
        ORDER BY built_at DESC LIMIT 1
        """,
        (year, kind, game, livelog_rev, tracking_rev, BUILDER_VERSION, load_taxonomy().version),
    )
    row = cur.fetchone()
    return dict(row) if row else None


@dataclass
class GameBuildResult:
    year: int
    kind_code: str
    game_sno: int
    build_id: str | None
    action: str  # publish | reconcile | noop | skip_no_events
    build_state: str | None
    summary: dict[str, Any] = field(default_factory=dict)


def _pa_summary(pas: list[PlateAppearance], plan: PitchPlan, taxonomy: Taxonomy) -> dict[str, Any]:
    state_counts: Counter = Counter(pa.state for pa in pas)
    completed = sum(1 for pa in pas if pa.island_class == "completed_pa")
    unknown_samples = [
        {"start_event_no": pa.start_event_no, "result_action": pa.result_action}
        for pa in pas if pa.island_class == "unknown_action"
    ][:20]
    return {
        "taxonomy_version": taxonomy.version,
        "builder_version": BUILDER_VERSION,
        "island_total": len(pas),
        "box_pa": completed,  # 完成 PA（ready + reconciliation 中曾 ready）以 island_class 計
        "candidate_pa": len(pas),
        "ready": state_counts.get(STATE_READY, 0),
        "unreliable": state_counts.get(STATE_UNRELIABLE, 0),
        "truncated": state_counts.get(STATE_TRUNCATED, 0),
        "non_pa": state_counts.get(STATE_NON_PA, 0),
        "reconciliation_required": state_counts.get(STATE_RECONCILIATION, 0),
        "mapped_pitches": plan.mapped,
        "failed_pitches": plan.failed,
        "orphan_pitches": plan.orphan,
        "orphan_samples": plan.orphan_samples,
        "unknown_action_samples": unknown_samples,
    }


def build_game(cur: Any, year: int, kind: str, game: int, *, taxonomy: Taxonomy | None = None) -> GameBuildResult:
    """物化單場 canonical PA build（冪等；atomic publish / reconciliation）。

    呼叫者提供 cursor（row_factory=dict_row）並負責交易邊界；本函式在單一交易內
    完成 revision upsert、PA/event/mapping 寫入與 publish/reconcile 決策。
    """
    taxonomy = taxonomy or load_taxonomy()
    events = _fetch_events(cur, year, kind, game)
    if not events:
        return GameBuildResult(year, kind, game, None, "skip_no_events", None)
    pitches = _fetch_pitches(cur, year, kind, game)
    game_has_tracking = len(pitches) > 0

    ll_sha, ll_rows, ll_max = _livelog_manifest(events)
    livelog_rev = upsert_source_revision(
        cur, year=year, kind=kind, game=game, source_kind="livelog",
        sha256=ll_sha, row_count=ll_rows, max_source_key=ll_max,
    )
    tracking_rev: int | None = None
    if game_has_tracking:
        tk_sha, tk_rows, tk_max = _tracking_manifest(pitches)
        tracking_rev = upsert_source_revision(
            cur, year=year, kind=kind, game=game, source_kind="tracking",
            sha256=tk_sha, row_count=tk_rows, max_source_key=tk_max,
        )

    existing = _existing_equivalent_build(
        cur, year=year, kind=kind, game=game, livelog_rev=livelog_rev, tracking_rev=tracking_rev
    )
    if existing:  # 同一來源重跑 → 完全相同，冪等 no-op
        return GameBuildResult(year, kind, game, str(existing["build_id"]), "noop",
                               existing["state"])

    pas = plate_appearances(year, kind, game, events, taxonomy)
    plan = plan_pitch_mappings(pas, pitches)
    assign_tracking_availability(pas, plan, game_has_tracking)

    published_meta = _published_build_meta(cur, year, kind, game)
    published = _published_pa_fingerprints(cur, year, kind, game)
    # 來源 manifest（sha256 決定）完全相同、只有 builder/taxonomy 進版 → fingerprint
    # 差異只可能來自解讀改變，非來源漂移；來源有任何變動則此旗標為 False（fail closed）。
    builder_upgrade = bool(
        published_meta
        and published_meta["livelog_revision_id"] == livelog_rev
        and published_meta["tracking_revision_id"] == tracking_rev
        and (published_meta["builder_version"] != BUILDER_VERSION
             or published_meta["taxonomy_version"] != taxonomy.version)
    )
    rec = reconcile(pas, published, builder_upgrade_same_source=builder_upgrade)

    # 不變式 fail closed：任一半局出局 PA > 3 → 整場不 publish、保留舊 published 供稽核。
    # **必須在 reconciliation 標記之前評估**：不變式看的是分類結果本身，若先套用
    # reconciliation 會把 ready 改成 reconciliation_required，使不變式看不到違反而靜默放行。
    violations = half_inning_out_violations(pas)
    apply_invariant_states(pas, violations)
    if violations:
        rec = ReconcileResult(
            action="reconcile", changed_pa_ids=rec.changed_pa_ids,
            added_pa_ids=rec.added_pa_ids, removed_pa_ids=rec.removed_pa_ids,
        )
        log.error(
            "invariant violated (half-inning out PA > %d), not publishing %s/%s/%s: %s",
            MAX_OUT_PA_PER_HALF_INNING, year, kind, game, violations,
        )
    apply_reconciliation_states(pas, rec)

    build_id = str(uuid.uuid4())
    summary = _pa_summary(pas, plan, taxonomy)
    summary["reconcile"] = {
        "action": rec.action, "changed": rec.changed_pa_ids,
        "added": rec.added_pa_ids, "removed": rec.removed_pa_ids,
        "builder_upgrade": rec.builder_upgrade,
    }
    summary["invariant_violations"] = violations
    cur.execute(
        """
        INSERT INTO cpbl.game_recap_builds
            (build_id, year, kind_code, game_sno, livelog_revision_id, tracking_revision_id,
             builder_version, taxonomy_version, state, validation_summary)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'building',%s::jsonb)
        """,
        (build_id, year, kind, game, livelog_rev, tracking_rev, BUILDER_VERSION,
         taxonomy.version, json.dumps(summary, ensure_ascii=False)),
    )

    _write_pas(cur, build_id, pas, plan, tracking_rev)

    if rec.action == "publish":
        # atomic swap：同交易 demote 舊 published → 發布新 build（partial unique index 保證唯一）
        cur.execute(
            "UPDATE cpbl.game_recap_builds SET state='superseded' "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s AND state='published'",
            (year, kind, game),
        )
        cur.execute("UPDATE cpbl.game_recap_builds SET state='published' WHERE build_id=%s",
                    (build_id,))
        build_state = "published"
    else:
        cur.execute(
            "UPDATE cpbl.game_recap_builds SET state='reconciliation_required' WHERE build_id=%s",
            (build_id,),
        )
        build_state = "reconciliation_required"

    return GameBuildResult(year, kind, game, build_id, rec.action, build_state, summary)


def _write_pas(
    cur: Any, build_id: str, pas: list[PlateAppearance], plan: PitchPlan, tracking_rev: int | None
) -> None:
    """寫入 PA、成員事件與逐球映射（每 PA 一 INSERT RETURNING 取代理鍵）。"""
    pa_row_ids: list[int] = []
    for pa in pas:
        cur.execute(
            """
            INSERT INTO cpbl.game_plate_appearances
                (pa_id, build_id, year, kind_code, game_sno, pa_index, start_event_no,
                 end_event_no, event_order_version, hitter_acnt, end_hitter_acnt,
                 start_pitcher_acnt,
                 end_pitcher_acnt, pre_state, post_state, result_action, outcome_family,
                 state, tracking_availability, reconciliation_reason)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s)
            RETURNING pa_row_id
            """,
            (str(pa.pa_id), build_id, pa.year, pa.kind_code, pa.game_sno, pa.pa_index,
             pa.start_event_no, pa.end_event_no, EVENT_ORDER_VERSION, pa.hitter_acnt,
             pa.end_hitter_acnt, pa.start_pitcher_acnt, pa.end_pitcher_acnt,
             json.dumps(pa.pre_state, ensure_ascii=False),
             json.dumps(pa.post_state, ensure_ascii=False),
             pa.result_action, pa.outcome_family, pa.state, pa.tracking_availability,
             pa.reconciliation_reason),
        )
        pa_row_ids.append(int(cur.fetchone()["pa_row_id"]))

    # 成員事件
    event_rows = [
        (pa_row_ids[i], str(pa.pa_id), pa.year, pa.kind_code, pa.game_sno,
         m.event_no, m.event_position, m.fingerprint)
        for i, pa in enumerate(pas) for m in pa.members
    ]
    if event_rows:
        cur.executemany(
            """
            INSERT INTO cpbl.game_pa_events
                (pa_row_id, pa_id, year, kind_code, game_sno, event_no, event_position,
                 event_fingerprint)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            event_rows,
        )

    # 逐球映射（需 tracking_rev；plan 的 pa_index 對齊 pas list 索引）
    if plan.mappings and tracking_rev is not None:
        map_rows = [
            (pa_row_ids[m.pa_index], str(pas[m.pa_index].pa_id), tracking_rev,
             pas[m.pa_index].year, pas[m.pa_index].kind_code, pas[m.pa_index].game_sno,
             m.pitcher_acnt, m.pitch_cnt, m.pitch_position, m.mapping_state, m.mapping_reason)
            for m in plan.mappings
        ]
        cur.executemany(
            """
            INSERT INTO cpbl.game_pa_pitch_mappings
                (pa_row_id, pa_id, source_revision_id, year, kind_code, game_sno,
                 pitcher_acnt, pitch_cnt, pitch_position, mapping_state, mapping_reason)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            map_rows,
        )


# ===========================================================================
# backfill 編排（可續跑：逐場 commit + 冪等 no-op skip）＋ QA 聚合
# ===========================================================================
def _list_games(
    cur: Any, from_year: int, to_year: int, kinds: list[str],
    only_games: list[tuple[int, str, int]] | None,
) -> list[tuple[int, str, int]]:
    if only_games:
        return list(only_games)
    cur.execute(
        """
        SELECT DISTINCT year, kind_code, game_sno
        FROM cpbl.game_livelog
        WHERE year BETWEEN %s AND %s AND kind_code = ANY(%s)
        ORDER BY year, kind_code, game_sno
        """,
        (from_year, to_year, kinds),
    )
    return [(r["year"], r["kind_code"], r["game_sno"]) for r in cur.fetchall()]


def build_scope(
    from_year: int, to_year: int, kinds: list[str], *,
    only_games: list[tuple[int, str, int]] | None = None, log_every: int = 200,
) -> dict[str, Any]:
    """回填/重建整個範圍。逐場 commit → 可續跑（crash 後重跑冪等 skip 已完成場）。"""
    from psycopg.rows import dict_row

    from cpbl.db import conn

    taxonomy = load_taxonomy()
    action_counts: Counter = Counter()
    state_counts: Counter = Counter()
    errors: list[dict[str, Any]] = []
    with conn() as c:
        cur = c.cursor(row_factory=dict_row)
        games = _list_games(cur, from_year, to_year, kinds, only_games)
        total = len(games)
        log.info("build_scope: %d games in %s..%s kinds=%s", total, from_year, to_year, kinds)
        for i, (year, kind, game) in enumerate(games):
            try:
                res = build_game(cur, year, kind, game, taxonomy=taxonomy)
                c.commit()
                action_counts[res.action] += 1
                if res.build_state:
                    state_counts[res.build_state] += 1
            except Exception as exc:  # noqa: BLE001 — 單場失敗不阻斷回填；記錄後續跑
                c.rollback()
                errors.append({"game": f"{year}/{kind}/{game}", "error": str(exc)[:300]})
                log.exception("build_game failed for %s/%s/%s", year, kind, game)
            if (i + 1) % log_every == 0:
                log.info("… %d/%d games processed", i + 1, total)
    return {
        "games": total,
        "actions": dict(action_counts),
        "build_states": dict(state_counts),
        "errors": errors,
    }


def collect_qa(from_year: int, to_year: int, kinds: list[str]) -> list[dict[str, Any]]:
    """由 published build 的 validation_summary 聚合每 年/賽制/球場 QA 對帳。"""
    from psycopg.rows import dict_row

    from cpbl.db import conn

    with conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        cur = c.cursor(row_factory=dict_row)
        cur.execute(
            """
            SELECT b.year, b.kind_code, g.venue,
                   count(*) AS games,
                   sum((b.validation_summary->>'box_pa')::int) AS box_pa,
                   sum((b.validation_summary->>'candidate_pa')::int) AS candidate_pa,
                   sum((b.validation_summary->>'ready')::int) AS ready,
                   sum((b.validation_summary->>'unreliable')::int) AS unreliable,
                   sum((b.validation_summary->>'truncated')::int) AS truncated,
                   sum((b.validation_summary->>'non_pa')::int) AS non_pa,
                   sum((b.validation_summary->>'mapped_pitches')::int) AS mapped_pitch,
                   sum((b.validation_summary->>'failed_pitches')::int) AS failed_pitch,
                   sum((b.validation_summary->>'orphan_pitches')::int) AS orphan_pitch
            FROM cpbl.game_recap_builds b
            LEFT JOIN (SELECT year, kind_code, game_sno, max(venue) AS venue
                       FROM cpbl.games GROUP BY 1, 2, 3) g USING (year, kind_code, game_sno)
            WHERE b.state = 'published'
              AND b.year BETWEEN %s AND %s AND b.kind_code = ANY(%s)
            GROUP BY b.year, b.kind_code, g.venue
            ORDER BY b.year, b.kind_code, g.venue
            """,
            (from_year, to_year, kinds),
        )
        return [dict(r) for r in cur.fetchall()]
