"""DATA-RE24-GHOST-RUNNER1：``sabr.build_re24`` 的幽靈跑者紅燈與「未歸類 = 0」回歸。

病灶（`docs/research/INIT-GAME-RECAP/spike-report.md` §2.3／§7 O-1）：延長賽「突破僵局
上壘」把跑者**直接放上二壘**，沒有打席、沒有投球，但 naive 的「連續同 hitter」切界會把
那一列當成該跑者的一個打席，記給他 ``+RE(_2_,0) − RE(___,0) = +0.6356``——2026/A 全季
49 筆、2024–2026/A 合計 202 筆，直接汙染球員頁 SABR 區線上可見的 RE24。

本檔釘兩件事：

1. **紅燈**：幽靈跑者列永遠不記給打者／投手，其 ΔRE 必須落到跑者桶（不是丟掉——丟掉會
   破壞望遠鏡求和恆等式，看起來像修好了其實是把帳做平）。判準必須來自 taxonomy，
   不是在 sabr.py 裡比中文字串。
2. **未歸類 = 0**：每個 naive 打席的處置屬於 ``RE24_DISPOSITIONS`` 這個封閉集合，且
   計數恰好分割全部打席，沒有第五種狀態。這是 spike 建議的釘法在季彙總路徑上的形式。
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg_pool import PoolClosed, PoolTimeout

from cpbl.ingest.pa_build import Taxonomy, classify_island, is_non_pa_action, load_taxonomy
from cpbl.models.sabr import (
    RE24_CHARGED,
    RE24_DISPOSITIONS,
    RE24_NON_PA,
    RE24_TRUNCATED,
    re24_disposition,
    re24_plays,
)

TIEBREAK = "突破僵局上壘"     # taxonomy v1.1.0 唯一的 role=non_pa 成員
GHOST = "0000009001"          # 被放上二壘的跑者
BATTER1 = "0000009002"
BATTER2 = "0000009003"
PITCHER = "0000009900"

# 0 出局的 RE 取生產矩陣（2018-2025/A）實值，好讓 +0.6356 這個具體數字有意義；
# 1／2 出局用固定衰減造出來（本檔的斷言不依賴它們的絕對值）。
_RE_BASE = {"___": 0.5269, "1__": 0.9012, "_2_": 1.1625, "__3": 1.3576,
            "12_": 1.4785, "1_3": 1.7241, "_23": 1.9663, "123": 2.2802}
RE_MAP = {(bases, outs): round(value * (1 - 0.4 * outs), 4)
          for bases, value in _RE_BASE.items() for outs in (0, 1, 2)}
GHOST_DELTA = round(RE_MAP[("_2_", 0)] - RE_MAP[("___", 0)], 4)   # +0.6356


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy()


def _event(no: str, *, inning: int, half: str, hitter: str, action: str | None,
           content: str = "", outs: int = 0, bases: tuple[str | None, str | None, str | None] = (None, None, None),
           away: int = 0, home: int = 0, change: bool = False) -> dict:
    first, second, third = bases
    return {
        "main_event_no": no, "inning_seq": inning, "visiting_home_type": half,
        "hitter_acnt": hitter, "pitcher_acnt": PITCHER, "action_name": action,
        "content": content, "out_cnt": outs, "is_change_player": change,
        "first_base": first, "second_base": second, "third_base": third,
        "visiting_score": away, "home_score": home,
    }


def _tiebreak_half() -> list[dict]:
    """延長 10 局下：幽靈跑者上二壘 → 打者 1 飛球出局 → 打者 2 再見安打。"""
    return [
        # 佈局列：無投球、壘上空（livelog 壘位是「事件前」快照）
        _event("1020001000", inning=10, half="2", hitter=GHOST, action=TIEBREAK,
               content="突破僵局上二壘。"),
        _event("1020002000", inning=10, half="2", hitter=BATTER1, action="飛球接殺",
               content="擊出右外野高飛球， 打者-右外野手 飛球接殺出局。 1人出局。",
               bases=(None, "7", None)),
        _event("1020003000", inning=10, half="2", hitter=BATTER2, action="一壘安打",
               content="擊出中外野方向一壘安打。 二壘跑者回本壘得分。",
               outs=1, bases=(None, "7", None), home=1),
    ]


# ===========================================================================
# 紅燈：幽靈跑者不進打者桶
# ===========================================================================
def test_tiebreak_runner_is_never_charged_to_a_batter(taxonomy):
    plays, _totals = re24_plays(_tiebreak_half(), RE_MAP, taxonomy)
    ghost = [p for p in plays if p["hitter_acnt"] == GHOST]
    assert len(ghost) == 1, "幽靈跑者列仍應被列舉（要能稽核），只是不得記給打者"
    assert ghost[0]["disposition"] == RE24_NON_PA
    charged = [p for p in plays if p["disposition"] == RE24_CHARGED]
    assert GHOST not in {p["hitter_acnt"] for p in charged}


def test_tiebreak_delta_is_the_known_plus_zero_point_six_three_five_six(taxonomy):
    """病灶的具體數值：這一列在舊碼下每筆給跑者 +0.6356。"""
    plays, _totals = re24_plays(_tiebreak_half(), RE_MAP, taxonomy)
    ghost = next(p for p in plays if p["hitter_acnt"] == GHOST)
    assert round(ghost["delta"], 4) == GHOST_DELTA == 0.6356


def test_tiebreak_delta_goes_to_the_runner_bucket_not_the_bin(taxonomy):
    """排除 ≠ 丟掉：ΔRE 必須落到跑者桶，否則望遠鏡求和恆等式會破。

    恆等式（build_re24 docstring）：Σ打者 + Σ跑者 = Σ得分 − 半局數 × RE(空壘,0)。
    """
    plays, totals = re24_plays(_tiebreak_half(), RE_MAP, taxonomy)
    batter_sum = sum(p["delta"] for p in plays if p["disposition"] == RE24_CHARGED)
    expected = totals["runs"] - totals["halves"] * RE_MAP[("___", 0)]
    assert round(batter_sum + totals["runner_delta"], 6) == round(expected, 6)


def test_real_batters_in_the_same_half_are_still_charged(taxonomy):
    """避免修過頭：同半局的真實打者照記，且幽靈列不會吃掉他們的打席。"""
    plays, _totals = re24_plays(_tiebreak_half(), RE_MAP, taxonomy)
    charged = {p["hitter_acnt"] for p in plays if p["disposition"] == RE24_CHARGED}
    assert charged == {BATTER1, BATTER2}


def test_tiebreak_pitcher_is_not_charged_either(taxonomy):
    """投手桶同病同治：沒有打席就沒有被面對的打者。"""
    plays, _totals = re24_plays(_tiebreak_half(), RE_MAP, taxonomy)
    ghost = next(p for p in plays if p["hitter_acnt"] == GHOST)
    assert ghost["disposition"] != RE24_CHARGED
    assert ghost["pitcher_acnt"] == PITCHER, "仍要留著投手欄供稽核，只是不記帳"


# ===========================================================================
# 判準的單一擁有者：taxonomy，不是字串字面值
# ===========================================================================
def test_criterion_comes_from_the_taxonomy(taxonomy):
    assert is_non_pa_action(TIEBREAK, taxonomy) is True
    assert is_non_pa_action("一壘安打", taxonomy) is False
    assert is_non_pa_action("", taxonomy) is False
    assert is_non_pa_action(None, taxonomy) is False
    # 未登錄的 action 不是「已知的非打席」；未知的 fail-closed 由呼叫端各自處理
    assert is_non_pa_action("這個動作不存在", taxonomy) is False


def test_re24_and_canonical_builder_agree_on_every_taxonomy_action(taxonomy):
    """同一份 taxonomy 下，RE24 路徑與 canonical PA builder 對「非打席」判定必須一致。

    兩邊各自比中文字串正是這張卡的病因；這條測試讓判準漂移直接紅燈。
    """
    for action in taxonomy.actions:
        island = [_event("1010001000", inning=1, half="1", hitter=BATTER1, action=action)]
        builder_says_non_pa = classify_island(island, taxonomy).state == "non_pa"
        re24_says_non_pa = re24_disposition(
            action, outs_before_terminal=0, runs_on_play=0, taxonomy=taxonomy) == RE24_NON_PA
        assert builder_says_non_pa == re24_says_non_pa, action


# ===========================================================================
# 未歸類 = 0：處置是封閉集合上的全函式
# ===========================================================================
def test_disposition_is_total_over_a_grid_of_inputs(taxonomy):
    actions = [TIEBREAK, "一壘安打", "三振", "", None, "這個動作不存在"]
    for action in actions:
        for outs in (0, 1, 2, 3, 4):
            for runs in (-1, 0, 1, 4):
                got = re24_disposition(action, outs_before_terminal=outs,
                                       runs_on_play=runs, taxonomy=taxonomy)
                assert got in RE24_DISPOSITIONS, (action, outs, runs, got)


def test_tiebreak_outranks_truncation_so_the_counter_stays_meaningful(taxonomy):
    """幽靈列即使同時符合截斷條件也要記成 non_pa（否則延長賽會稀釋截斷碎片指標）。"""
    assert re24_disposition(TIEBREAK, outs_before_terminal=3, runs_on_play=0,
                            taxonomy=taxonomy) == RE24_NON_PA
    assert re24_disposition("", outs_before_terminal=3, runs_on_play=0,
                            taxonomy=taxonomy) == RE24_TRUNCATED


def test_every_play_has_exactly_one_disposition(taxonomy):
    plays, _totals = re24_plays(_tiebreak_half(), RE_MAP, taxonomy)
    assert plays
    assert all(p["disposition"] in RE24_DISPOSITIONS for p in plays)


# ===========================================================================
# 真實資料窮舉（需要 DB；無 DB 時 skip）
# ===========================================================================
def _real_games(year: int | None = 2026, kind: str = "A") -> list[tuple[int, str, int]]:
    """``year=None`` ＝ build_re24 實際跑得動的**全部** scope。

    跑得動的只有 kind A：RE 矩陣只有 ``2018-2025/A``，其餘 kind 一律 RuntimeError
    （已實測 C／D／E 皆然），所以「全庫 scope」＝ 2018–2026 × A 九個。
    """
    from cpbl.db import conn
    with conn() as connection:
        cur = connection.cursor()
        if year is None:
            cur.execute("SELECT year, kind_code, game_sno FROM cpbl.game_livelog "
                        "WHERE kind_code=%s GROUP BY 1,2,3 ORDER BY 1,3", (kind,))
            return [(r[0], r[1], r[2]) for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT game_sno FROM cpbl.game_livelog "
                    "WHERE year=%s AND kind_code=%s ORDER BY game_sno", (year, kind))
        return [(year, kind, r[0]) for r in cur.fetchall()]


@pytest.fixture(scope="module")
def db_games() -> list[tuple[int, str, int]]:
    try:
        games = _real_games()
    except (psycopg.Error, PoolClosed, PoolTimeout, OSError) as exc:
        pytest.skip(f"無 DB：{type(exc).__name__}")
    if not games:
        pytest.skip("DB 無該季 livelog")
    return games


@pytest.fixture(scope="module")
def db_games_all_scopes() -> list[tuple[int, str, int]]:
    """全 scope（2018–2026/A）：中性重放要覆蓋整張表的母體，不只當季。

    R1 指名的捨入邊緣落在 2019／2021／2024，只驗當季會漏掉。
    """
    try:
        games = _real_games(year=None)
    except (psycopg.Error, PoolClosed, PoolTimeout, OSError) as exc:
        pytest.skip(f"無 DB：{type(exc).__name__}")
    if not games:
        pytest.skip("DB 無 livelog")
    return games


@pytest.fixture(scope="module")
def real_plays(db_games, taxonomy) -> list[dict]:
    from cpbl.db import conn
    from cpbl.models.sabr import _load_game, _load_re_matrix
    out: list[dict] = []
    with conn() as connection:
        cur = connection.cursor()
        re_map = _load_re_matrix(cur, "2018-2025", "A")
        if not re_map:
            pytest.skip("DB 無 run_expectancy 矩陣")
        for year, kind, sno in db_games:
            events = _load_game(cur, year, kind, sno)
            if not events:
                continue
            plays, _totals = re24_plays(events, re_map, taxonomy)
            for play in plays:
                play["game_sno"] = sno
            out.extend(plays)
    return out


# ===========================================================================
# golden replay：抽出的 re24_plays() 相對舊 inline 路徑必須是**中性重構**
#
# R1 查核提出「抽取改變累加順序，在 ±0.01 捨入邊緣翻位」。捨入邊緣翻位的前提是
# 累加後的浮點值不同，所以這裡不比 rounded 值（那只能證明「這批資料剛好沒翻」），
# 直接比**未捨入的累加浮點值是否逐位元相同**——bit 相同則捨入邊緣翻位在數學上
# 不可能發生，對任何資料集都成立，而不只是對現在這份。
# ===========================================================================
def _golden_inline_game(events: list[dict], re_map: dict, bat: dict, pit: dict,
                        totals: dict) -> None:
    """`7db485d` 抽取前 inline 演算法的逐行轉錄（去掉 DB 與幽靈跑者判斷）。

    刻意**不呼叫**任何被測程式碼的輔助函式以外的東西，累加器由呼叫端跨場共用，
    以完整重現原本「一路累加到底」的浮點順序。
    """
    from cpbl.models.sabr import _OUTS_ANN, _bases_of
    pv, ph = 0, 0
    for e in events:
        e["_pre_vs"], e["_pre_hs"] = pv, ph
        pv = e["visiting_score"] if e.get("visiting_score") is not None else pv
        ph = e["home_score"] if e.get("home_score") is not None else ph
        e["_post_vs"], e["_post_hs"] = pv, ph
    halves: dict[tuple, list[dict]] = {}
    order: list[tuple] = []
    for e in events:
        k = (e["inning_seq"], str(e["visiting_home_type"]))
        if k not in halves:
            halves[k] = []
            order.append(k)
        halves[k].append(e)
    for hk in order:
        vht = hk[1]
        pre_k = "_pre_vs" if vht == "1" else "_pre_hs"
        post_k = "_post_vs" if vht == "1" else "_post_hs"
        evs = [e for e in halves[hk] if not e.get("is_change_player") and e.get("hitter_acnt")]
        if not evs:
            continue
        totals["halves"] += 1
        totals["runs"] += halves[hk][-1][post_k] - halves[hk][0][pre_k]
        pas: list[list[dict]] = []
        for e in evs:
            if pas and pas[-1][-1]["hitter_acnt"] == e["hitter_acnt"]:
                pas[-1].append(e)
            else:
                pas.append([e])
        for pi, pa in enumerate(pas):
            first, final = pa[0], pa[-1]
            s_state = (_bases_of(first), min(int(first.get("out_cnt") or 0), 2))
            outs_f = int(first.get("out_cnt") or 0)
            for e in pa[:-1]:
                for m in _OUTS_ANN.findall(e.get("content") or ""):
                    outs_f = max(outs_f, int(m))
            runs_play = final[post_k] - final[pre_k]
            mid_runs = final[pre_k] - first[pre_k]
            if pi + 1 < len(pas):
                nxt = pas[pi + 1][0]
                re_after = re_map[(_bases_of(nxt), min(int(nxt.get("out_cnt") or 0), 2))]
            else:
                re_after = 0.0
            truncated = outs_f >= 3 or not (final.get("action_name") or "").strip()
            re_f = re_map[(_bases_of(final), min(outs_f, 2))]
            totals["runner"] += re_f + mid_runs - re_map[s_state]
            delta = re_after + runs_play - re_f
            if truncated or runs_play < 0:
                totals["runner"] += delta
                continue
            entry = bat.setdefault(final["hitter_acnt"], [0, 0.0])
            entry[0] += 1
            entry[1] += delta
            if final.get("pitcher_acnt"):
                p = pit.setdefault(final["pitcher_acnt"], [0, 0.0])
                p[0] += 1
                p[1] += delta


def _neutralised(taxonomy: Taxonomy) -> Taxonomy:
    """把 taxonomy 的 non_pa 角色全部拿掉——中性重放用（不 monkeypatch 生產模組）。"""
    return Taxonomy(version=taxonomy.version,
                    actions={name: {**entry, "role": "pa_terminal"}
                             for name, entry in taxonomy.actions.items()})


def _accumulate(plays: list[dict]) -> tuple[dict, dict]:
    """完全照 build_re24 的累加方式吃 plays（打者桶／投手桶）。"""
    bat: dict[str, list] = {}
    pit: dict[str, list] = {}
    for play in plays:
        if play["disposition"] != RE24_CHARGED:
            continue
        entry = bat.setdefault(play["hitter_acnt"], [0, 0.0])
        entry[0] += 1
        entry[1] += play["delta"]
        if play.get("pitcher_acnt"):
            p = pit.setdefault(play["pitcher_acnt"], [0, 0.0])
            p[0] += 1
            p[1] += play["delta"]
    return bat, pit


def test_extraction_is_bit_identical_to_the_inline_path_on_synthetic_streams(taxonomy):
    """合成事件流上的中性重放：逐位元相同（不必起 DB，永遠會跑）。"""
    events = _tiebreak_half()
    gold_bat, gold_pit, totals = {}, {}, {"halves": 0, "runs": 0, "runner": 0.0}
    _golden_inline_game([dict(e) for e in events], RE_MAP, gold_bat, gold_pit, totals)
    plays, new_totals = re24_plays(events, RE_MAP, _neutralised(taxonomy))
    new_bat, new_pit = _accumulate(plays)
    assert new_bat == gold_bat
    assert new_pit == gold_pit
    assert new_totals["halves"] == totals["halves"]
    assert new_totals["runs"] == totals["runs"]
    assert new_totals["runner_delta"] == totals["runner"]


def test_extraction_is_bit_identical_to_the_inline_path_on_real_games(db_games_all_scopes, taxonomy):
    """真實全季中性重放：**未捨入**的逐球員累加值必須逐位元相同。

    比 rounded 輸出更強——bit 相同表示任何捨入邊緣都不可能翻位。
    """
    from cpbl.db import conn
    from cpbl.models.sabr import _load_game, _load_re_matrix
    neutral = _neutralised(taxonomy)
    gold_bat, gold_pit, totals = {}, {}, {"halves": 0, "runs": 0, "runner": 0.0}
    new_bat, new_pit = {}, {}
    with conn() as connection:
        cur = connection.cursor()
        re_map = _load_re_matrix(cur, "2018-2025", "A")
        if not re_map:
            pytest.skip("DB 無 run_expectancy 矩陣")
        for year, kind, sno in db_games_all_scopes:
            events = _load_game(cur, year, kind, sno)
            if not events:
                continue
            _golden_inline_game([dict(e) for e in events], re_map, gold_bat, gold_pit, totals)
            plays, _t = re24_plays(events, re_map, neutral)
            for play in plays:
                if play["disposition"] != RE24_CHARGED:
                    continue
                entry = new_bat.setdefault(play["hitter_acnt"], [0, 0.0])
                entry[0] += 1
                entry[1] += play["delta"]
                if play.get("pitcher_acnt"):
                    p = new_pit.setdefault(play["pitcher_acnt"], [0, 0.0])
                    p[0] += 1
                    p[1] += play["delta"]
    assert gold_bat, "golden 沒吃到任何打席，測試本身失效"
    drift = {k: (gold_bat[k], new_bat.get(k)) for k in gold_bat if new_bat.get(k) != gold_bat[k]}
    assert not drift, f"打者桶浮點漂移：{list(drift.items())[:5]}"
    drift_p = {k: (gold_pit[k], new_pit.get(k)) for k in gold_pit if new_pit.get(k) != gold_pit[k]}
    assert not drift_p, f"投手桶浮點漂移：{list(drift_p.items())[:5]}"
    # 捨入後也必須相同（R1 指名的是 rounded 輸出，這裡把那一層也一併釘住）
    assert {k: round(v[1], 2) for k, v in new_bat.items()} == \
           {k: round(v[1], 2) for k, v in gold_bat.items()}


def test_ghost_fix_is_the_only_difference_from_the_golden_path(db_games_all_scopes, taxonomy):
    """可解釋性的測試化：golden 與**修好後**的差額，逐球員恰等於該球員的幽靈列總和。

    這是 verify artifact 的「零未解釋差異」搬進回歸測試——不再只是報告裡的一句話。
    """
    from cpbl.db import conn
    from cpbl.models.sabr import _load_game, _load_re_matrix
    gold_bat, gold_pit, totals = {}, {}, {"halves": 0, "runs": 0, "runner": 0.0}
    fixed_bat, fixed_pit = {}, {}
    ghost_bat: dict[str, list] = {}
    ghost_pit: dict[str, list] = {}
    with conn() as connection:
        cur = connection.cursor()
        re_map = _load_re_matrix(cur, "2018-2025", "A")
        if not re_map:
            pytest.skip("DB 無 run_expectancy 矩陣")
        for year, kind, sno in db_games_all_scopes:
            events = _load_game(cur, year, kind, sno)
            if not events:
                continue
            _golden_inline_game([dict(e) for e in events], re_map, gold_bat, gold_pit, totals)
            plays, _t = re24_plays(events, re_map, taxonomy)     # 真 taxonomy＝修好後
            for play in plays:
                if play["disposition"] == RE24_NON_PA:
                    g = ghost_bat.setdefault(play["hitter_acnt"], [0, 0.0])
                    g[0] += 1
                    g[1] += play["delta"]
                    if play.get("pitcher_acnt"):
                        gp = ghost_pit.setdefault(play["pitcher_acnt"], [0, 0.0])
                        gp[0] += 1
                        gp[1] += play["delta"]
                    continue
                if play["disposition"] != RE24_CHARGED:
                    continue
                entry = fixed_bat.setdefault(play["hitter_acnt"], [0, 0.0])
                entry[0] += 1
                entry[1] += play["delta"]
                if play.get("pitcher_acnt"):
                    p = fixed_pit.setdefault(play["pitcher_acnt"], [0, 0.0])
                    p[0] += 1
                    p[1] += play["delta"]
    if not ghost_bat:
        pytest.skip("該季無延長賽突破僵局列")
    unexplained = []
    for player, (pa, re24) in gold_bat.items():
        got = fixed_bat.get(player, [0, 0.0])
        ghost = ghost_bat.get(player, [0, 0.0])
        if got[0] != pa - ghost[0] or round(got[1] - (re24 - ghost[1]), 6) != 0:
            unexplained.append((player, pa, re24, got, ghost))
    assert not unexplained, f"打者差異無法以幽靈列解釋：{unexplained[:5]}"


def test_no_naive_pa_is_unclassified_on_real_games(real_plays):
    """全季窮舉：每個打席的處置都在封閉集合內，沒有第五種狀態。"""
    unknown = [(p["game_sno"], p["end_event_no"], p["disposition"])
               for p in real_plays if p["disposition"] not in RE24_DISPOSITIONS]
    assert not unknown, f"未歸類打席：{unknown[:10]}"


def test_every_tiebreak_row_in_the_database_is_excluded(db_games, real_plays):
    """紅燈的真實資料版：DB 裡每一筆幽靈跑者列都必須被排除在打者桶之外。

    以 SQL 獨立列舉母體（不靠被驗證的那條路徑自報家門），再逐筆比對。
    """
    from cpbl.db import conn
    year, kind, _ = db_games[0]
    with conn() as connection:
        cur = connection.cursor()
        cur.execute(
            "SELECT game_sno, main_event_no FROM cpbl.game_livelog "
            "WHERE year=%s AND kind_code=%s AND action_name=%s "
            "AND NOT COALESCE(is_change_player, false) AND hitter_acnt IS NOT NULL",
            (year, kind, TIEBREAK))
        expected = {(r[0], str(r[1])) for r in cur.fetchall()}
    if not expected:
        pytest.skip("該季無延長賽突破僵局列")
    seen = {(p["game_sno"], p["end_event_no"]) for p in real_plays
            if p["disposition"] == RE24_NON_PA}
    assert expected <= seen, f"漏抓的幽靈列：{sorted(expected - seen)[:10]}"
    charged = {(p["game_sno"], p["end_event_no"]) for p in real_plays
               if p["disposition"] == RE24_CHARGED}
    assert not (expected & charged), f"仍被記給打者的幽靈列：{sorted(expected & charged)[:10]}"
