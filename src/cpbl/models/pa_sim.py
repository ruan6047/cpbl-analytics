"""單一打席情境模擬的資料快照與結果分類。"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

import joblib

from cpbl.db import conn
from cpbl.ingest.splits_calc import PA_OUTCOME

OUTCOMES = ("K", "BB_HBP", "1B", "XBH", "HR", "BIP_OUT", "OTHER_REACH")
_REACH_ACTIONS = {
    "一失", "二失", "三失", "游失", "投失", "捕失", "中失", "左失", "右失",
    "失", "雙誤", "野選", "礙打", "犧短誤", "犧飛誤",
}


@dataclass(frozen=True)
class PAEvent:
    event_no: int
    inning: int
    half: str
    hitter: str
    pitcher: str
    bases: str
    outs: int | None
    away_score: int
    home_score: int
    action: str | None
    year: int = 0
    game_sno: int = 0
    game_date: date | None = None


@dataclass(frozen=True)
class GameState:
    inning: int
    half: str
    bases: str
    outs: int
    away_score: int
    home_score: int


@dataclass(frozen=True)
class PASnapshot:
    event_no: int
    hitter: str
    pitcher: str
    result: str
    before: GameState
    after: GameState
    runs_delta: int
    inning_ended: bool
    game_ended: bool
    year: int = 0
    game_sno: int = 0
    game_date: date | None = None
    end_event_no: int = 0
    game_outcome: float = 0.5


@dataclass(frozen=True)
class PAAudit:
    total_pa: int
    classified_pa: int
    rebuilt_pa: int
    unknown_actions: dict[str, int]
    missing_action_pa: int = 0
    state_errors: dict[str, int] = field(default_factory=dict)
    box_pa: int | None = None
    games: int = 1

    @property
    def classification_rate(self) -> float:
        return self.classified_pa / self.total_pa if self.total_pa else 0.0

    @property
    def rebuild_rate(self) -> float:
        return self.rebuilt_pa / self.total_pa if self.total_pa else 0.0

    @property
    def box_delta_rate(self) -> float | None:
        if not self.box_pa:
            return None
        return abs(self.total_pa - self.box_pa) / self.box_pa


@dataclass(frozen=True)
class PADataset:
    snapshots: list[PASnapshot]
    audits: dict[int, PAAudit]


@dataclass(frozen=True)
class EmpiricalBayesModel:
    league: dict[str, float]
    hitters: dict[str, Counter]
    pitchers: dict[str, Counter]
    direct: dict[tuple[str, str], Counter]
    hitter_strength: float
    pitcher_strength: float
    direct_strength: float


@dataclass(frozen=True)
class Transition:
    runs_delta: int
    bases: str
    outs: int
    inning_ended: bool


@dataclass(frozen=True)
class TransitionKernel:
    exact: dict[tuple[str, str, int], Counter]
    by_outs: dict[tuple[str, int], Counter]
    by_result: dict[str, Counter]

    def distribution(
        self, result: str, bases: str, outs: int,
    ) -> tuple[list[tuple[Transition, float]], str, int]:
        candidates = (
            (self.exact.get((result, bases, outs)), "result+bases+outs"),
            (self.by_outs.get((result, outs)), "result+outs"),
            (self.by_result.get(result), "result"),
        )
        for counts, level in candidates:
            if counts:
                total = sum(counts.values())
                rows = sorted(counts.items(), key=lambda item: repr(item[0]))
                return [(transition, count / total) for transition, count in rows], level, total
        raise RuntimeError(f"無 {result} 的狀態轉移樣本")


def classify_action(action: str | None) -> str | None:
    """將官方打席結果詞彙映射成互斥結果；未知詞彙一律不猜。"""
    if not action or action not in PA_OUTCOME:
        return None
    delta = PA_OUTCOME[action]
    if delta.get("so"):
        return "K"
    if delta.get("bb") or delta.get("hbp"):
        return "BB_HBP"
    if delta.get("home_runs"):
        return "HR"
    if delta.get("singles"):
        return "1B"
    if delta.get("doubles") or delta.get("triples"):
        return "XBH"
    if action in _REACH_ACTIONS:
        return "OTHER_REACH"
    return "BIP_OUT"


def events_from_rows(rows: Iterable[Mapping]) -> list[PAEvent]:
    """將 livelog 的事件後比分轉成打席模型需要的事件前比分。"""
    away_score = home_score = 0
    events: list[PAEvent] = []
    for row in rows:
        has_state = all(row.get(key) is not None for key in ("inning", "half"))
        if (has_state and row.get("hitter") and row.get("pitcher")
                and not row.get("is_change_player")):
            bases = (
                ("1" if row.get("first_base") else "_")
                + ("2" if row.get("second_base") else "_")
                + ("3" if row.get("third_base") else "_")
            )
            events.append(
                PAEvent(
                    event_no=int(row["event_no"]),
                    inning=int(row["inning"]),
                    half=str(row["half"]),
                    hitter=str(row["hitter"]),
                    pitcher=str(row["pitcher"]),
                    bases=bases,
                    outs=(int(row["outs"]) if row.get("outs") is not None else None),
                    away_score=away_score,
                    home_score=home_score,
                    action=row.get("action"),
                    year=int(row.get("year") or 0),
                    game_sno=int(row.get("game_sno") or 0),
                    game_date=row.get("game_date"),
                )
            )
        if row.get("post_away") is not None:
            away_score = int(row["post_away"])
        if row.get("post_home") is not None:
            home_score = int(row["post_home"])
    return events


def resolve_pa_event_no(rows: list[Mapping], event_no: int) -> int | None:
    """將換人宣告事件確定性映射到同半局下一個真實打席事件。"""
    index = next(
        (i for i, row in enumerate(rows) if int(row["event_no"]) == event_no), None,
    )
    if index is None:
        return None
    target = rows[index]
    half_key = (target.get("inning"), str(target.get("half")))
    for row in rows[index:]:
        if (row.get("inning"), str(row.get("half"))) != half_key:
            return None
        if (not row.get("is_change_player") and row.get("hitter")
                and row.get("pitcher")):
            return int(row["event_no"])
    return None


def _state(event: PAEvent) -> GameState:
    if event.outs is None:
        raise ValueError("建立 GameState 前必須解析出局數")
    return GameState(
        inning=event.inning,
        half=event.half,
        bases=event.bases,
        outs=min(max(event.outs, 0), 2),
        away_score=event.away_score,
        home_score=event.home_score,
    )


def _group_events(events: list[PAEvent]) -> list[list[PAEvent]]:
    groups: list[list[PAEvent]] = []
    for event in sorted(events, key=lambda row: row.event_no):
        key = (event.inning, event.half, event.hitter)
        current_key = None
        if groups:
            current = groups[-1][0]
            current_key = (current.inning, current.half, current.hitter)
        if key != current_key:
            groups.append([])
        groups[-1].append(event)
    return groups


def _first_state_event(group: list[PAEvent]) -> PAEvent | None:
    """牽制等 control event 可能無 out_cnt；採同 PA 首個有完整局面者。"""
    return next((event for event in group if event.outs is not None), None)


def build_pa_snapshots(
    events: list[PAEvent], final_score: tuple[int, int] | None = None,
) -> list[PASnapshot]:
    """由依事件序排列的資料，以「下一打席首事件」取得實際 post-state。

    最後一個打席沒有下一狀態時不猜測，由資料稽核列入未重建樣本。
    """
    return _build_pa_snapshots(events, final_score)[0]


def _build_pa_snapshots(
    events: list[PAEvent], final_score: tuple[int, int] | None = None,
) -> tuple[list[PASnapshot], Counter]:
    if not events:
        return [], Counter()
    groups = _group_events(events)

    snapshots: list[PASnapshot] = []
    state_errors: Counter = Counter()
    game_outcome = 0.5
    if final_score is not None:
        game_outcome = (1.0 if final_score[1] > final_score[0]
                        else (0.0 if final_score[1] < final_score[0] else 0.5))
    for index, group in enumerate(groups):
        action = next((row.action for row in reversed(group) if row.action), None)
        result = classify_action(action)
        if result is None:
            continue
        first = group[0]
        before_event = _first_state_event(group)
        if before_event is None:
            state_errors["missing_outs"] += 1
            continue
        before = _state(before_event)
        game_ended = index == len(groups) - 1
        if game_ended:
            if final_score is None:
                continue
            away_score, home_score = final_score
            after = GameState(
                inning=before.inning,
                half=before.half,
                bases="___",
                outs=0,
                away_score=away_score,
                home_score=home_score,
            )
        else:
            next_event = _first_state_event(groups[index + 1])
            if next_event is None:
                state_errors["missing_next_outs"] += 1
                continue
            error = _state_transition_error(before_event, next_event)
            if error:
                state_errors[error] += 1
                continue
            after = _state(next_event)
        batting_before = before.away_score if before.half == "1" else before.home_score
        batting_after = after.away_score if before.half == "1" else after.home_score
        if batting_after < batting_before:
            state_errors["batting_score_regressed"] += 1
            continue
        runs_delta = batting_after - batting_before
        same_half = (before.inning, before.half) == (after.inning, after.half)
        if (result == "BB_HBP" and before.bases == "123" and same_half
                and after.outs == before.outs and runs_delta == 0):
            state_errors["forced_advance_missing"] += 1
            continue
        snapshots.append(
            PASnapshot(
                event_no=first.event_no,
                hitter=first.hitter,
                pitcher=first.pitcher,
                result=result,
                before=before,
                after=after,
                runs_delta=runs_delta,
                inning_ended=game_ended or (
                    (before.inning, before.half) != (after.inning, after.half)
                ),
                game_ended=game_ended,
                year=first.year,
                game_sno=first.game_sno,
                game_date=first.game_date,
                end_event_no=group[-1].event_no,
                game_outcome=game_outcome,
            )
        )
    return snapshots, state_errors


def _state_transition_error(before: PAEvent, after: PAEvent) -> str | None:
    """驗證下一打席首事件確實是可達的 post-state，不以 clamp 隱藏資料污染。"""
    if before.outs is None or after.outs is None:
        return "missing_outs"
    if before.outs not in range(3) or after.outs not in range(3):
        return "outs_out_of_range"
    if after.away_score < before.away_score or after.home_score < before.home_score:
        return "score_regressed"
    current = (before.inning, before.half)
    following = (after.inning, after.half)
    if following == current:
        return "outs_regressed" if after.outs < before.outs else None
    expected = ((before.inning, "2") if before.half == "1"
                else (before.inning + 1, "1"))
    return None if following == expected else "inning_sequence_invalid"


def audit_pa_events(
    events: list[PAEvent], final_score: tuple[int, int] | None = None,
) -> PAAudit:
    """統計可分類與可重建率；未知官方詞彙完整回報，不以其他類別吸收。"""
    groups = _group_events(events)
    actions = [
        next((row.action for row in reversed(group) if row.action), None)
        for group in groups
    ]
    terminal_actions = [action for action in actions if action]
    unknown = Counter(action for action in terminal_actions if classify_action(action) is None)
    classified = sum(classify_action(action) is not None for action in actions)
    rebuilt, state_errors = _build_pa_snapshots(events, final_score)
    return PAAudit(
        total_pa=len(groups),
        classified_pa=classified,
        rebuilt_pa=len(rebuilt),
        unknown_actions=dict(sorted(unknown.items())),
        missing_action_pa=sum(not action for action in actions),
        state_errors=dict(sorted(state_errors.items())),
    )


def assert_audit_coverage(audits: Mapping[int, PAAudit], minimum: float = 0.99) -> None:
    """逐年分類與狀態重建率都須達標；任一年不足即停止訓練。"""
    failures = []
    for year, audit in sorted(audits.items()):
        box_delta = audit.box_delta_rate
        if (audit.classification_rate < minimum or audit.rebuild_rate < minimum
                or (box_delta is not None and box_delta > 1 - minimum)):
            detail = (f"{year}: classification={audit.classification_rate:.3%}, "
                      f"rebuild={audit.rebuild_rate:.3%}")
            if box_delta is not None:
                detail += f", box_delta={box_delta:.3%}"
            failures.append(detail)
    if failures:
        raise RuntimeError("PA coverage 未達門檻：" + "; ".join(failures))


def _merge_audit(current: PAAudit | None, added: PAAudit) -> PAAudit:
    if current is None:
        return added
    unknown = Counter(current.unknown_actions)
    unknown.update(added.unknown_actions)
    state_errors = Counter(current.state_errors)
    state_errors.update(added.state_errors)
    return PAAudit(
        total_pa=current.total_pa + added.total_pa,
        classified_pa=current.classified_pa + added.classified_pa,
        rebuilt_pa=current.rebuilt_pa + added.rebuilt_pa,
        unknown_actions=dict(sorted(unknown.items())),
        missing_action_pa=current.missing_action_pa + added.missing_action_pa,
        state_errors=dict(sorted(state_errors.items())),
        box_pa=(current.box_pa or 0) + (added.box_pa or 0) or None,
        games=current.games + added.games,
    )


def load_pa_dataset(from_year: int, to_year: int, kind: str = "A") -> PADataset:
    """串流讀取已完成賽事，重建可供走查的逐打席 snapshot 與逐年稽核。"""
    if from_year > to_year:
        raise ValueError("from_year 不可大於 to_year")
    sql = """
        SELECT l.year, l.game_sno, g.game_date,
               l.main_event_no::bigint AS event_no,
               l.inning_seq AS inning, l.visiting_home_type AS half,
               l.hitter_acnt AS hitter, l.pitcher_acnt AS pitcher,
               l.first_base, l.second_base, l.third_base, l.out_cnt AS outs,
               l.visiting_score AS post_away, l.home_score AS post_home,
               l.batting_action_name AS action, l.is_change_player,
               g.away_score AS final_away, g.home_score AS final_home
        FROM cpbl.game_livelog l
        JOIN cpbl.games g ON g.year=l.year AND g.kind_code=l.kind_code
                         AND g.game_sno=l.game_sno
        WHERE l.year BETWEEN %s AND %s AND l.kind_code=%s
          AND g.home_score + g.away_score > 0
        ORDER BY l.year, l.game_sno, l.main_event_no::bigint
    """
    snapshots: list[PASnapshot] = []
    audits: dict[int, PAAudit] = {}

    def consume(rows: list[dict]) -> None:
        if not rows:
            return
        events = events_from_rows(rows)
        final_score = (int(rows[-1]["final_away"]), int(rows[-1]["final_home"]))
        year = int(rows[0]["year"])
        audit = audit_pa_events(events, final_score)
        audits[year] = _merge_audit(audits.get(year), audit)
        snapshots.extend(build_pa_snapshots(events, final_score))

    with conn() as connection:
        box_by_year = dict(connection.execute(
            "SELECT year, COALESCE(SUM(plate_appearances), 0) "
            "FROM cpbl.batting_gamelog WHERE year BETWEEN %s AND %s AND kind_code=%s "
            "GROUP BY year",
            (from_year, to_year, kind),
        ).fetchall())
        cur = connection.cursor(name="pa_sim_dataset")
        cur.execute(sql, (from_year, to_year, kind))
        columns = [column.name for column in cur.description]
        game_key = None
        game_rows: list[dict] = []
        for values in cur:
            row = dict(zip(columns, values, strict=True))
            row_key = (row["year"], row["game_sno"])
            if game_key is not None and row_key != game_key:
                consume(game_rows)
                game_rows = []
            game_key = row_key
            game_rows.append(row)
        consume(game_rows)
    audits = {
        year: replace(audit, box_pa=int(box_by_year[year]) if year in box_by_year else None)
        for year, audit in audits.items()
    }
    return PADataset(snapshots=snapshots, audits=audits)


def load_game_pa_snapshot(
    year: int, kind: str, game_sno: int, event_no: int,
) -> PASnapshot | None:
    """解析指定事件所屬打席；無法唯一定位即回 None。"""
    with conn() as connection:
        cur = connection.cursor()
        cur.execute(
            """
            SELECT l.year, l.game_sno, g.game_date, l.main_event_no::bigint AS event_no,
                   l.inning_seq AS inning, l.visiting_home_type AS half,
                   l.hitter_acnt AS hitter, l.pitcher_acnt AS pitcher,
                   l.first_base, l.second_base, l.third_base, l.out_cnt AS outs,
                   l.visiting_score AS post_away, l.home_score AS post_home,
                   l.batting_action_name AS action, l.is_change_player,
                   g.away_score AS final_away, g.home_score AS final_home
            FROM cpbl.game_livelog l
            JOIN cpbl.games g ON g.year=l.year AND g.kind_code=l.kind_code
                             AND g.game_sno=l.game_sno
            WHERE l.year=%s AND l.kind_code=%s AND l.game_sno=%s
            ORDER BY l.main_event_no::bigint
            """,
            (year, kind, game_sno),
        )
        columns = [column.name for column in cur.description]
        rows = [dict(zip(columns, values, strict=True)) for values in cur.fetchall()]
    if not rows:
        return None
    resolved_event_no = resolve_pa_event_no(rows, event_no)
    if resolved_event_no is None:
        return None
    events = events_from_rows(rows)
    final_score = (int(rows[-1]["final_away"]), int(rows[-1]["final_home"]))
    matches = [snapshot for snapshot in build_pa_snapshots(events, final_score)
               if snapshot.event_no <= resolved_event_no <= snapshot.end_event_no]
    return matches[0] if len(matches) == 1 else None


def fit_empirical_bayes(
    snapshots: Iterable[PASnapshot],
    hitter_strength: float = 200.0,
    pitcher_strength: float = 300.0,
    direct_strength: float = 100.0,
) -> EmpiricalBayesModel:
    """建立分層計數；strength 由外層訓練資料的內層走查選定。"""
    if min(hitter_strength, pitcher_strength, direct_strength) <= 0:
        raise ValueError("prior strength 必須大於 0")
    league_counts = Counter({outcome: 0.5 for outcome in OUTCOMES})
    hitters: dict[str, Counter] = {}
    pitchers: dict[str, Counter] = {}
    direct: dict[tuple[str, str], Counter] = {}
    for snapshot in snapshots:
        league_counts[snapshot.result] += 1
        hitters.setdefault(snapshot.hitter, Counter())[snapshot.result] += 1
        pitchers.setdefault(snapshot.pitcher, Counter())[snapshot.result] += 1
        direct.setdefault((snapshot.hitter, snapshot.pitcher), Counter())[snapshot.result] += 1
    total = sum(league_counts.values())
    league = {outcome: league_counts[outcome] / total for outcome in OUTCOMES}
    return EmpiricalBayesModel(
        league=league,
        hitters=hitters,
        pitchers=pitchers,
        direct=direct,
        hitter_strength=hitter_strength,
        pitcher_strength=pitcher_strength,
        direct_strength=direct_strength,
    )


def _posterior(counts: Counter | None, league: Mapping[str, float], strength: float) -> dict:
    counts = counts or Counter()
    total = sum(counts.values())
    return {
        outcome: (counts[outcome] + strength * league[outcome]) / (total + strength)
        for outcome in OUTCOMES
    }


def _softmax(logits: Mapping[str, float]) -> dict[str, float]:
    peak = max(logits.values())
    weights = {key: math.exp(value - peak) for key, value in logits.items()}
    total = sum(weights.values())
    return {key: value / total for key, value in weights.items()}


def predict_outcomes(
    model: EmpiricalBayesModel, hitter: str, pitcher: str,
) -> dict[str, float]:
    """合成打者與投手 composition；直接對戰以 base 為先驗連續 shrink。"""
    hitter_p = _posterior(model.hitters.get(hitter), model.league, model.hitter_strength)
    pitcher_p = _posterior(model.pitchers.get(pitcher), model.league, model.pitcher_strength)
    base = _softmax({
        outcome: math.log(hitter_p[outcome]) + math.log(pitcher_p[outcome])
        - math.log(model.league[outcome])
        for outcome in OUTCOMES
    })
    direct = model.direct.get((hitter, pitcher))
    if not direct:
        return base
    total = sum(direct.values())
    return {
        outcome: (direct[outcome] + model.direct_strength * base[outcome])
        / (total + model.direct_strength)
        for outcome in OUTCOMES
    }


def fit_transition_kernel(snapshots: Iterable[PASnapshot]) -> TransitionKernel:
    """建立結果條件轉移核；終場列不混入一般跑者推進分布。"""
    exact: dict[tuple[str, str, int], Counter] = {}
    by_outs: dict[tuple[str, int], Counter] = {}
    by_result: dict[str, Counter] = {}
    for snapshot in snapshots:
        if snapshot.game_ended:
            continue
        transition = Transition(
            runs_delta=snapshot.runs_delta,
            bases=snapshot.after.bases,
            outs=snapshot.after.outs,
            inning_ended=snapshot.inning_ended,
        )
        exact.setdefault(
            (snapshot.result, snapshot.before.bases, snapshot.before.outs), Counter()
        )[transition] += 1
        by_outs.setdefault((snapshot.result, snapshot.before.outs), Counter())[transition] += 1
        by_result.setdefault(snapshot.result, Counter())[transition] += 1
    return TransitionKernel(exact=exact, by_outs=by_outs, by_result=by_result)


def _transition_wp(
    state: GameState, transition: Transition, wp: Callable[[GameState], float],
) -> float:
    away, home = state.away_score, state.home_score
    if state.half == "1":
        away += transition.runs_delta
    else:
        home += transition.runs_delta

    if state.half == "2" and state.inning >= 9 and home > away:
        return 1.0
    if transition.inning_ended:
        if state.half == "1":
            if state.inning >= 9 and home > away:
                return 1.0
            next_state = GameState(state.inning, "2", "___", 0, away, home)
        else:
            if state.inning >= 9 and home < away:
                return 0.0
            if state.inning >= 12 and home == away:
                return 0.5
            next_state = GameState(state.inning + 1, "1", "___", 0, away, home)
    else:
        next_state = GameState(
            state.inning, state.half, transition.bases, transition.outs, away, home,
        )
    return wp(next_state)


def simulate_plate_appearance(
    model: EmpiricalBayesModel,
    kernel: TransitionKernel,
    hitter: str,
    pitcher: str,
    state: GameState,
    wp: Callable[[GameState], float],
) -> dict:
    """計算各互斥結果及其經驗 next-state 加權後主隊勝率。"""
    probabilities = predict_outcomes(model, hitter, pitcher)
    current_wp = wp(state)
    outcomes: dict[str, dict] = {}
    weighted = 0.0
    for result, probability in probabilities.items():
        transitions, level, sample_count = kernel.distribution(result, state.bases, state.outs)
        result_wp = sum(
            transition_probability * _transition_wp(state, transition, wp)
            for transition, transition_probability in transitions
        )
        outcomes[result] = {
            "probability": probability,
            "win_probability": result_wp,
            "delta_wp": result_wp - current_wp,
            "transition_level": level,
            "transition_samples": sample_count,
        }
        weighted += probability * result_wp
    return {
        "current_win_probability": current_wp,
        "weighted_win_probability": weighted,
        "outcomes": outcomes,
    }


def train_pa_artifact(
    snapshots: list[PASnapshot],
    trained_through: int,
    strengths: tuple[float, float, float],
    wp_span: str | None = None,
) -> dict:
    training = [snapshot for snapshot in snapshots if snapshot.year <= trained_through]
    if not training:
        raise ValueError("無可訓練打席")
    return {
        "version": 1,
        "trained_through": trained_through,
        "wp_span": wp_span or f"2018-{trained_through}",
        "strengths": strengths,
        "model": fit_empirical_bayes(training, *strengths),
        "kernel": fit_transition_kernel(training),
    }


def save_pa_artifact(artifact: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)


def load_pa_artifact(path: Path) -> dict:
    return joblib.load(path)
