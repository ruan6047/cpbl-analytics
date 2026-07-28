"""球隊頁「近日焦點」素材 3：即將挑戰的紀錄（UX-TEAM-RECORDS1；唯讀）。

三種素材（2026-07-28 需求方定案，記於 docs/tasks/UX-TEAM-RECORDS1.md，不得自行更動）：

1. **個人生涯里程碑**（計數型）——生涯口徑一律走 `cpbl.api.routers.players` 的
   canonical helper（`_career_batting_per_year`/`_career_pitching_per_year` +
   `_sum_batting_career`/`_sum_pitching_career`），與球員頁
   `/api/v1/players/{id}/career` 同一份邏輯（該端點本身也改走這兩個 helper）。
   **嚴禁另行拼裝 `batting_seasons` ∪ gamelog**——那是卡面紅線：自行拼裝會與
   球員頁生涯數字對不起來。

   判準＝「下一場真的有機會達成」，可操作化為單一規則：**取「單場達成 ≥N」
   發生率仍 ≥5% 的最大 N**（Coordinator 2026-07-28 以 2018+ 一軍逐場資料實測，
   5% 這條線每項都切得乾淨，見卡面數字，不可為了湊整數偏離）。門檻**逐項不同**
   （`BATTER_MILESTONES`/`PITCHER_MILESTONES`，卡面表格，執行者不得逕自改動）：
   安打 3、打點 2、得分 2、全壘打 1、盜壘 1、勝投／救援中繼 1（結構上單場上限）；
   三振／局數見下方角色分流。排序＝「差距／階梯」比值由小到大（越接近越前面）。

   **三振／局數投手角色分流**（2026-07-28 需求方追加）：只有這兩項的單場分布
   隨角色差一個數量級（先發 vs 後援），其餘計數型與角色無關。判定用本季一軍
   `pitching_gamelog.role_type='先發'` 場次佔比：≥0.5 → 先發門檻（三振 8／局數 7）；
   其餘（含混合型與本季出賽 <5 場者）→ 後援門檻（三振 2／局數 2）——樣本不足
   一律歸後援是刻意的保守方向：後援門檻低 ⇒ 上榜少 ⇒ 不會對「今晚可能達成」
   做出兌現不了的宣稱（見 `_pitcher_role`）。

2. **進行中連續安打**——直接呼叫 `cpbl.api.team_focus._current_hit_streak`
   （UX-TEAM-FOCUS2 已上線，kind_code='A' 一軍口徑），不重寫。`STREAK_MIN`/
   `STREAK_TOP_N` 是本卡新增（卡面只要求複用計算本身，未定義呈現門檻/上限）——
   執行者提案 5 場起算、至多列 5 位，理由：避免每隊塞滿 0~2 場的雜訊，5 場
   在中職語境已算「連續安打」值得關注的長度。

3. **隊史紀錄（僅計數型）**——2026-07-28 需求方修正初版：初版把 franchise 彙總
   限定 `*_seasons`（不含本季），用「非即時」但書揭露；**該做法作廢，因為它會
   產出錯誤數字，不是延遲數字**（實測案例：畫面顯示「曾子祐得分還差 2 破隊史
   紀錄」，但本季曾子祐 +49、魔鷹 +32 之後實際是 177 vs 162，曾子祐早已超前
   15 分——一個標題叫「即將挑戰的紀錄」的區塊放去年底的快照，但書救不了它）。
   現在 franchise 彙總**必須含本季，走與素材 1 同一套 canonical 口徑**（重用
   `_career_batting_per_year`/`_career_pitching_per_year` 等四個 helper，不另拼
   一套聚合）——`_franchise_batting_totals`/`_franchise_pitching_totals`
   （`*_seasons` only）現在只作為「上季結束時」的基準值，不再是顯示用的隊史
   紀錄；顯示值一律走 `_merge_current_season` 疊上現役名單的 canonical 生涯總和
   （對現役球員等於含本季，對非現役球員維持基準值不變——他們今年沒有新
   gamelog 可疊加，本來就該維持原樣）。**「本季貢獻非即時」但書已移除**
   （移除理由見上：修好之後它是假的，留著比拿掉更誤導）。

   兩種狀態（`_franchise_records`）：
   - **本季已刷新**：現役球員目前總計 >「上季結束時」的隊史該項最高（用*_seasons
     基準判斷「有被刷新的對象」）。呈現為成就，不用「還差 N」。
   - **逼近中**：低於「目前」隊史最高（已含本季）、差距 ≤ 該項門檻。門檻與判準
     沿用素材 1 同一組 `near`/`ladder`（不留兩套）；三振／局數沿用同一位球員的
     角色分流門檻。若目前紀錄持有人本身仍在現役名單（`active_ids`），逼近中的
     文案標注「現役中」——紀錄保持人還在打球時，這個數字本身會隨賽季推進而動，
     措辭不能讓讀者誤以為是固定目標（台鋼雄鷹是典型案例：2024 年才進一軍，
     隊史紀錄保持人全部仍在隊上出賽，逼近隊史紀錄實質是「追一個今天也在跑
     的人」，跟富邦這種紀錄多半在退役球員手上的老牌隊不是同一回事）。

   **連續型隊史紀錄（最長連續安打/無失分等）不做**——需求方 2026-07-28 裁定，
   逐場資料僅 2018+ 會讓口徑半殘，任何「近年最佳」變體措辭也不得出現，本模組
   完全不產生這類欄位。

範圍限定**一軍現役名單**（`batting_current`/`pitching_current`，`year=season`）：
`_current_hit_streak` 本身即 kind_code='A'（一軍）口徑，混入二軍名單會造成
同一區塊內標準不一致；且二軍球員的 `*_seasons`/`batting_gamelog` 覆蓋是否對齊
未經查證，故本模組全程只看一軍現役名單（執行者範圍決定，非隊史/生涯口徑本身
的紅線）。

`available`／退化語意：三個陣列（`milestones`/`streaks`/`franchise_records`）
分別可能為空；前端在三者皆空時顯示統一退化文案「目前無接近中的紀錄」，
不顯示空區塊或零值（見 `docs/tasks/UX-TEAM-RECORDS1.md` 驗收條件）。
"""

from __future__ import annotations

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.api.routers.players import (
    _career_batting_per_year,
    _career_pitching_per_year,
    _sum_batting_career,
    _sum_pitching_career,
)
from cpbl.api.team_focus import _current_hit_streak
from cpbl.db import conn
from cpbl.franchises import franchise_prefixes

# 里程碑階梯與門檻（卡面表格 2026-07-28 定版，勿逕自改動數值；label/stat 對齊
# canonical 生涯欄位）。near＝「取單場達成 ≥N 發生率仍 ≥5% 的最大 N」的實測結果
# （2018+ 一軍逐場資料），不是階梯比例、也不是「單場上限」的粗略估計——勝投／
# 救援中繼剛好兩者相符（結構上單場上限即 1），其餘各項不相符（如三振單場遠
# 不只 3 次，但「達到差 8」這件事仍要看發生率，不是看上限）。
BATTER_MILESTONES = [
    {"stat": "h", "label": "安打", "ladder": 100, "start": 200, "near": 3},
    {"stat": "rbi", "label": "打點", "ladder": 100, "start": 200, "near": 2},
    {"stat": "r", "label": "得分", "ladder": 100, "start": 200, "near": 2},
    {"stat": "hr", "label": "全壘打", "ladder": 25, "start": 25, "near": 1},
    {"stat": "sb", "label": "盜壘", "ladder": 25, "start": 25, "near": 1},
]
BATTER_STATS = [m["stat"] for m in BATTER_MILESTONES]

# 三振／局數的 near 隨投手本季角色（先發／後援）而異，見 PITCHER_ROLE_NEAR +
# _pitcher_role。這裡的 near 只是「後援」（保守方向）的預設值，供角色查詢失敗
# 或呼叫端未解析角色時的 fallback；實際判斷一律走 near_by_player 覆寫。
PITCHER_MILESTONES = [
    {"stat": "so", "label": "三振", "ladder": 100, "start": 200, "near": 2},
    {"stat": "ip", "label": "投球局數", "ladder": 100, "start": 200, "near": 2},
    {"stat": "w", "label": "勝投", "ladder": 10, "start": 20, "near": 1},
    {"stat": "sv_hld", "label": "救援／中繼", "ladder": 25, "start": 25, "near": 1},
]
PITCHER_STATS = [m["stat"] for m in PITCHER_MILESTONES]
PITCHER_ROLE_NEAR = {
    "so": {"starter": 8, "reliever": 2},
    "ip": {"starter": 7, "reliever": 2},
}
ROLE_SPLIT_STATS = frozenset(PITCHER_ROLE_NEAR)
# 角色判定：本季出賽 <5 場者樣本不足，一律歸後援（保守方向，見 `_pitcher_role`）。
ROLE_MIN_GAMES = 5
ROLE_STARTER_RATIO = 0.5

STREAK_MIN = 5
STREAK_TOP_N = 5


def _next_milestone(current: int, ladder: int, start: int) -> tuple[int, int]:
    """回傳（下一個里程碑, 差距）。里程碑＝大於現值、且 ≥ 起始門檻的最小階梯倍數。"""
    candidate = ((current // ladder) + 1) * ladder
    if candidate < start:
        candidate = start
    return candidate, candidate - current


def _classify_pitcher_role(starts: int, total: int) -> str:
    """本季一軍先發場次佔比 ≥0.5 → 'starter'；其餘（含混合型與出賽 <5 場者，
    樣本不足時保守歸類）→ 'reliever'。純函式（不含 DB 查詢），只影響三振／局數
    兩項門檻；`total>=ROLE_MIN_GAMES` 在 `and` 左側短路，`total=0` 不會除以零。"""
    if total >= ROLE_MIN_GAMES and starts / total >= ROLE_STARTER_RATIO:
        return "starter"
    return "reliever"


def _pitcher_role(cur, pitcher_id: str, season: int) -> str:
    cur.execute(
        "SELECT count(*) FILTER (WHERE role_type='先發'), count(*) "
        "FROM cpbl.pitching_gamelog WHERE pitcher_acnt=%s AND year=%s AND kind_code='A'",
        (pitcher_id, season))
    starts, total = cur.fetchone()
    return _classify_pitcher_role(starts or 0, total or 0)


def _roster(cur, code: str, season: int) -> tuple[list[dict], list[dict]]:
    """一軍現役名單（打者／投手），供三種素材共用。"""
    cur.execute(
        "SELECT player_id, name FROM cpbl.batting_current WHERE team_code=%s AND year=%s ORDER BY name",
        (code, season))
    batters = [{"player_id": p, "name": n} for p, n in cur.fetchall()]
    cur.execute(
        "SELECT player_id, name FROM cpbl.pitching_current WHERE team_code=%s AND year=%s ORDER BY name",
        (code, season))
    pitchers = [{"player_id": p, "name": n} for p, n in cur.fetchall()]
    return batters, pitchers


def _batter_milestones(cur, roster: list[dict]) -> list[dict]:
    out = []
    for pl in roster:
        per = _career_batting_per_year(cur, pl["player_id"])
        if not per:
            continue
        tot = _sum_batting_career(per)
        for m in BATTER_MILESTONES:
            current = int(tot.get(m["stat"], 0) or 0)
            milestone, gap = _next_milestone(current, m["ladder"], m["start"])
            if 0 < gap <= m["near"]:
                out.append({
                    "player_id": pl["player_id"], "name": pl["name"], "role": "batting",
                    "stat": m["stat"], "label": m["label"], "current": current,
                    "milestone": milestone, "remaining": gap, "ladder": m["ladder"],
                    "ratio": round(gap / m["ladder"], 4),
                })
    return out


def _pitcher_near_by_player(cur, roster: list[dict], season: int) -> dict[str, dict[str, int]]:
    """每位投手本季角色（先發／後援）解析後的三振／局數 near 覆寫表。"""
    out: dict[str, dict[str, int]] = {}
    for pl in roster:
        role = _pitcher_role(cur, pl["player_id"], season)
        out[pl["player_id"]] = {stat: PITCHER_ROLE_NEAR[stat][role] for stat in ROLE_SPLIT_STATS}
    return out


def _pitcher_milestones(
    cur, roster: list[dict], near_by_player: dict[str, dict[str, int]],
) -> list[dict]:
    out = []
    for pl in roster:
        pper = _career_pitching_per_year(cur, pl["player_id"])
        if not pper:
            continue
        pt = _sum_pitching_career(pper)
        outs = round(pt.get("rip", 0.0) * 3)
        values = {
            "so": int(pt.get("so", 0) or 0),
            "ip": outs // 3,
            "w": int(pt.get("w", 0) or 0),
            "sv_hld": int(pt.get("sv", 0) or 0) + int(pt.get("hld", 0) or 0),
        }
        near_override = near_by_player.get(pl["player_id"], {})
        for m in PITCHER_MILESTONES:
            current = values[m["stat"]]
            near = near_override.get(m["stat"], m["near"])
            milestone, gap = _next_milestone(current, m["ladder"], m["start"])
            if 0 < gap <= near:
                out.append({
                    "player_id": pl["player_id"], "name": pl["name"], "role": "pitching",
                    "stat": m["stat"], "label": m["label"], "current": current,
                    "milestone": milestone, "remaining": gap, "ladder": m["ladder"],
                    "ratio": round(gap / m["ladder"], 4),
                })
    return out


def _franchise_batting_totals(cur, prefixes: list[str]) -> dict[str, dict]:
    """franchise 歷來成員「上季結束時」的累計（僅 `*_seasons`，不含本季 gamelog）。

    2026-07-28 需求方修正：這個查詢**不再是顯示用的隊史紀錄**（原版把它當顯示值
    是錯誤數字，不是延遲數字，見模組 docstring）。現在只作為「本季已刷新」判準
    的基準——「刷新」需要一個被刷新的對象，這裡回傳的就是那個對象。顯示值走
    `_merge_current_season` 疊上現役名單的 canonical（含本季）生涯總和。
    """
    cur.execute(
        "SELECT bs.player_id, max(p.name), sum(bs.h), sum(bs.rbi), sum(bs.r), sum(bs.hr), sum(bs.sb) "
        "FROM cpbl.batting_seasons bs LEFT JOIN cpbl.players p ON p.id = bs.player_id "
        "WHERE substring(bs.team_id,1,3) = ANY(%s) GROUP BY bs.player_id",
        (prefixes,))
    return {
        pid: {"name": nm or pid, "h": h or 0, "rbi": rbi or 0, "r": r or 0, "hr": hr or 0, "sb": sb or 0}
        for pid, nm, h, rbi, r, hr, sb in cur.fetchall()
    }


def _franchise_pitching_totals(cur, prefixes: list[str]) -> dict[str, dict]:
    """franchise 歷來成員「上季結束時」的累計（僅 `*_seasons`）。同上，只是基準，非顯示值。"""
    cur.execute(
        "SELECT ps.player_id, max(p.name), sum(ps.so), "
        "sum(trunc(ps.ip)+(ps.ip-trunc(ps.ip))*10/3.0), sum(ps.w), sum(ps.sv), sum(ps.hld) "
        "FROM cpbl.pitching_seasons ps LEFT JOIN cpbl.players p ON p.id = ps.player_id "
        "WHERE substring(ps.team_id,1,3) = ANY(%s) GROUP BY ps.player_id",
        (prefixes,))
    out = {}
    for pid, nm, so, rip, w, sv, hld in cur.fetchall():
        outs = round(float(rip or 0.0) * 3)
        out[pid] = {"name": nm or pid, "so": so or 0, "ip": outs // 3, "w": w or 0,
                    "sv_hld": (sv or 0) + (hld or 0)}
    return out


# 本季 franchise-scoped 增量所需的「該場代表哪一隊」判定式，與
# `cpbl.api.team_focus._TEAM_CODE_EXPR` 同一邏輯（visiting_home_type='2' 為主隊），
# 只是這裡分別對齊 batting_gamelog/pitching_gamelog 各自的別名。
_BATTING_TEAM_EXPR = "CASE WHEN bg.visiting_home_type='2' THEN g.home_team_code ELSE g.away_team_code END"
_PITCHING_TEAM_EXPR = "CASE WHEN pg.visiting_home_type='2' THEN g.home_team_code ELSE g.away_team_code END"


def _franchise_current_season_batting(cur, prefixes: list[str], season: int) -> dict[str, dict]:
    """本季 franchise-scoped 打擊增量（`batting_gamelog`，依該場代表隊伍過濾）。

    **不能**改用 `_career_batting_per_year`（canonical 生涯 helper）疊加現役名單——
    該 helper 回傳球員「全生涯」總和，跨隊球員會把其他球團的產值誤記為這支隊伍的
    隊史貢獻（實測案例：王柏融 2026 加入台鋼雄鷹，`_career_batting_per_year` 回傳
    的生涯 836 安打含 2015–2018 Lamigo 時期 ~660 支，若直接拿來當台鋼隊史彙總會
    把樂天時期的安打算成台鋼紀錄）。本函式改為直接依比賽當場代表隊伍過濾
    `batting_gamelog`，只計入「該球員本季代表這支 franchise 出賽」的產值。
    """
    cur.execute(
        f"SELECT bg.hitter_acnt, sum(bg.hits), sum(bg.rbi), sum(bg.runs), sum(bg.home_runs), sum(bg.sb) "
        f"FROM cpbl.batting_gamelog bg JOIN cpbl.games g "
        f"ON g.year=bg.year AND g.kind_code=bg.kind_code AND g.game_sno=bg.game_sno "
        f"WHERE bg.year=%s AND bg.kind_code='A' "
        f"AND substring({_BATTING_TEAM_EXPR},1,3) = ANY(%s) "
        f"GROUP BY bg.hitter_acnt",
        (season, prefixes))
    return {
        pid: {"h": h or 0, "rbi": rbi or 0, "r": r or 0, "hr": hr or 0, "sb": sb or 0}
        for pid, h, rbi, r, hr, sb in cur.fetchall()
    }


def _franchise_current_season_pitching(cur, prefixes: list[str], season: int) -> dict[str, dict]:
    """本季 franchise-scoped 投球增量。理由同 `_franchise_current_season_batting`
    ——不可用 `_career_pitching_per_year`，那還有第二個問題：`pitching_seasons`
    目前只到 2025（無 2026 列），該 helper 完全沒有 gamelog 補本季的機制（跟打擊
    helper 不同），本季一律回 0，不只是跨隊誤記的問題。

    w／sv 用官方 `games.winning_pitcher_id`／`closer_id`（`splits_calc.py` 的
    `save_ok` 判定同一來源，是官網逐場直接寫入的欄位，不是規則 9.19 推算——
    `cpbl.models.pitcher_decisions` 那套推算是給沒有這兩欄的資料路徑用的，
    這裡不需要）；hld 用官方 `pitching_gamelog.relief_point`；三振／局數
    直接加總欄位，局數換算沿用全站慣例 `outs = cnt*3 + div3`。
    """
    cur.execute(
        f"SELECT pg.pitcher_acnt, sum(pg.so), "
        f"sum(pg.inning_pitched_cnt)*3 + sum(pg.inning_pitched_div3) AS outs, "
        f"count(*) FILTER (WHERE g.winning_pitcher_id = pg.pitcher_acnt) AS w, "
        f"count(*) FILTER (WHERE g.closer_id = pg.pitcher_acnt) AS sv, "
        f"count(*) FILTER (WHERE pg.relief_point > 0) AS hld "
        f"FROM cpbl.pitching_gamelog pg JOIN cpbl.games g "
        f"ON g.year=pg.year AND g.kind_code=pg.kind_code AND g.game_sno=pg.game_sno "
        f"WHERE pg.year=%s AND pg.kind_code='A' "
        f"AND substring({_PITCHING_TEAM_EXPR},1,3) = ANY(%s) "
        f"GROUP BY pg.pitcher_acnt",
        (season, prefixes))
    out = {}
    for pid, so, outs, w, sv, hld in cur.fetchall():
        out[pid] = {"so": so or 0, "ip": (outs or 0) // 3, "w": w or 0, "sv_hld": (sv or 0) + (hld or 0)}
    return out


def _merge_current_season(
    prior: dict[str, dict], roster: list[dict], delta: dict[str, dict], stats: list[str],
) -> dict[str, dict]:
    """把「上季結束時」的 franchise 基準（`prior`）**加上**現役名單本季的
    franchise-scoped 增量（`delta`，來自 `_franchise_current_season_batting`/
    `_franchise_current_season_pitching`），得到「目前」隊史彙總。

    刻意用 ADD 不是 OVERWRITE：`prior` 已是截至上季（含）為止的正確累計，這裡只
    需要補當季差量。非現役的歷代成員維持 `prior` 原值不動（他們今年沒有新
    franchise-scoped gamelog 可疊加，本來就該維持原樣）。
    """
    merged = {pid: dict(v) for pid, v in prior.items()}
    for pl in roster:
        pid = pl["player_id"]
        d = delta.get(pid)
        if d is None:
            continue
        entry = merged.setdefault(pid, {"name": pl["name"], **dict.fromkeys(stats, 0)})
        entry["name"] = pl["name"]
        for s in stats:
            entry[s] = int(entry.get(s, 0) or 0) + int(d.get(s, 0) or 0)
    return merged


def _franchise_records(
    roster: list[dict], prior: dict[str, dict], current: dict[str, dict],
    stat_defs: list[dict], role: str,
    near_by_player: dict[str, dict[str, int]] | None = None,
    active_ids: frozenset[str] = frozenset(),
) -> list[dict]:
    """隊史紀錄兩種狀態（2026-07-28 需求方裁定，見模組 docstring）：

    - **本季已刷新**（`state="refreshed"`）：現役球員目前總計（`current`，已含本季）
      是該項目「目前」的隊史最高，且超過「上季結束時」的基準（`prior`）——「刷新」
      需要一個被刷新的對象，`prior` 就是那個對象。只有目前真正並列/單獨持有該
      項目最高值的人才算刷新，避免同隊多人都超過舊紀錄時人人自稱刷新；
      `prior_record<=0`（franchise 在 `*_seasons` 完全沒有基準，理論上只會發生在
      一支隊伍的第一個有紀錄球季）時不判刷新——沒有基準就沒有「被刷新的對象」。
    - **逼近中**（`state="approaching"`）：低於「目前」隊史最高、差距 ≤ 該項門檻
      （沿用 `stat_defs` 的 near，投手三振／局數用 `near_by_player` 覆寫，跟里程碑
      同一組判準，不留第二套）。`holder_active`＝目前持有人是否仍在本隊現役名單
      （`active_ids`）——是的話前端須標注「現役中」，因為那個數字本身還會隨賽季
      推進而動，不是靜止的碑（台鋼雄鷹是典型案例：2024 年才進一軍，隊史紀錄保持
      人全部仍在隊上出賽）。

    `prior`／`current` 皆已是「已含正確 name」的 dict（`_merge_current_season`
    輸出或等價結構），無需另外查名字。
    """
    out = []
    for m in stat_defs:
        stat = m["stat"]
        prior_record = max((v.get(stat, 0) for v in prior.values()), default=0)
        leader_value = max((v.get(stat, 0) for v in current.values()), default=0)
        if leader_value <= 0:
            continue
        leader_pids = [pid for pid, v in current.items() if v.get(stat, 0) == leader_value]
        leader_names = sorted({current[pid]["name"] for pid in leader_pids})
        leader_active = any(pid in active_ids for pid in leader_pids)
        for pl in roster:
            pid = pl["player_id"]
            v = current.get(pid)
            if v is None:
                continue
            cur_val = v.get(stat, 0)
            if cur_val <= 0:
                continue
            if cur_val == leader_value and prior_record > 0 and cur_val > prior_record:
                out.append({
                    "player_id": pid, "name": pl["name"], "role": role,
                    "stat": stat, "label": m["label"], "state": "refreshed",
                    "current": cur_val, "prior_record": prior_record,
                    "prior_holder": "、".join(sorted({v2["name"] for v2 in prior.values() if v2.get(stat, 0) == prior_record})),
                    "ratio": 0.0,
                })
            elif cur_val < leader_value:
                gap = leader_value - cur_val
                near = m["near"]
                if near_by_player is not None:
                    near = near_by_player.get(pid, {}).get(stat, near)
                if 0 < gap <= near:
                    out.append({
                        "player_id": pid, "name": pl["name"], "role": role,
                        "stat": stat, "label": m["label"], "state": "approaching",
                        "current": cur_val, "record": leader_value, "remaining": gap,
                        "holder": "、".join(leader_names), "holder_active": leader_active,
                        "ratio": round(gap / m["ladder"], 4),
                    })
    return out


def upcoming_records(code: str, season: int = DEFAULT_SEASON) -> dict:
    """球隊頁「即將挑戰的紀錄」：生涯里程碑 + 進行中連續安打 + 隊史紀錄（計數型，含本季）。"""
    with conn() as c:
        cur = c.cursor()
        batters_roster, pitchers_roster = _roster(cur, code, season)
        pitcher_near = _pitcher_near_by_player(cur, pitchers_roster, season)

        milestones = (
            _batter_milestones(cur, batters_roster)
            + _pitcher_milestones(cur, pitchers_roster, pitcher_near)
        )
        milestones.sort(key=lambda x: x["ratio"])

        streaks = []
        for pl in batters_roster:
            s = _current_hit_streak(cur, code, season, pl["player_id"])
            if s >= STREAK_MIN:
                streaks.append({"player_id": pl["player_id"], "name": pl["name"], "streak": s})
        streaks.sort(key=lambda x: -x["streak"])
        streaks = streaks[:STREAK_TOP_N]

        # 隊史紀錄：prior＝上季結束時基準（*_seasons only）；current＝疊上現役名單
        # 本季 franchise-scoped 增量後的「目前」隊史彙總。兩者都要保留給
        # _franchise_records 分別當「被刷新的對象」與「目前隊史最高」用。
        prefixes = sorted(franchise_prefixes(code))
        prior_batters = _franchise_batting_totals(cur, prefixes)
        prior_pitchers = _franchise_pitching_totals(cur, prefixes)
        batter_delta = _franchise_current_season_batting(cur, prefixes, season)
        pitcher_delta = _franchise_current_season_pitching(cur, prefixes, season)
        current_batters = _merge_current_season(prior_batters, batters_roster, batter_delta, BATTER_STATS)
        current_pitchers = _merge_current_season(prior_pitchers, pitchers_roster, pitcher_delta, PITCHER_STATS)
        active_ids = frozenset(pl["player_id"] for pl in batters_roster + pitchers_roster)
        franchise_records = (
            _franchise_records(batters_roster, prior_batters, current_batters,
                               BATTER_MILESTONES, "batting", active_ids=active_ids)
            + _franchise_records(pitchers_roster, prior_pitchers, current_pitchers,
                                 PITCHER_MILESTONES, "pitching",
                                 near_by_player=pitcher_near, active_ids=active_ids)
        )
        franchise_records.sort(key=lambda x: x["ratio"])

    return {
        "season": season,
        "milestones": milestones,
        "streaks": streaks,
        "franchise_records": franchise_records,
    }
