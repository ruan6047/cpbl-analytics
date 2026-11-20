"""#457 一次性：REBAS `playerId` ↔ 中職十碼 `acnt` 對照（2023–2026 一軍例行賽）。

⛔ 一次性工具，不接排程、不進 `cpbl` schema、不加 migration、不寫 DB。
⛔ 不改 PitchMind 檔案、不改 `data/exports/pitchmind/` 既有匯出檔。

採用規則（需求方 2026-11-20 裁定，#457 issuecomment-7038538159）：
  名冊姓名 ∩ 同年同場同半局同角色實際出現的帳號，逐年逐角色雙向唯一才收。
官方逐場 box（同場、同側、同背號）**只出佐證報告與人工清單證據，不參與配對**
（核定規劃 #457 issuecomment-7038956489 方案 A）。

兩段：
  snapshot  單一 REPEATABLE READ／READ ONLY 交易把 DB 輸入凍結成 CSV 快照＋manifest
            （`players` 每日會被同步，先凍結才 build；快照 digest 記入 manifest）。
            ⚠️ 刻意不走 `cpbl.db.conn()`：該 context manager 結束時 commit，且無法宣告
            唯讀＋REPEATABLE READ 的單一交易；本段改直接用 psycopg 並核對
            `transaction_read_only=on`，結束時 rollback。
  review    純計算：輸入＝快照＋REBAS zip，輸出規則結果、人工裁清單（box 有唯一候選）、
            無候選清單、佐證報告。⛔ 本段不產生最終 `player_id_map_2023_2026.csv`
            ——最終匯出要等需求方裁完清單後另行實作（核定規劃 WP3）。

角色代碼：B＝打者、P＝投手、C＝捕手。
半局（livelog `visiting_home_type`）：1＝客隊進攻、2＝主隊進攻。
側別（gamelog `visiting_home_type`）：1＝客隊、2＝主隊。
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROLES = ("B", "P", "C")
ROLE_LABEL = {"B": "打者", "P": "投手", "C": "捕手"}
DEFAULT_ZIP_DIR = "/Users/ruanruan/Dev/Rebas/data/pitchmind-stage1"
ZIP_GLOB = "CPBL-*-OpenData.zip"
# 2023 zip 內檔名是「中職2023年-G4.json」、2024+ 是「CPBL-2024-G1.json」，只認 -G<n>.json 尾段。
GAME_FILE_RE = re.compile(r"-G\d+\.json$")
YEARS = (2023, 2024, 2025, 2026)

# ------------------------------------------------------------------ snapshot（唯讀 DB）

SNAPSHOT_QUERIES: dict[str, tuple[tuple[str, ...], str]] = {
    "players.csv": (
        ("id", "name"),
        "SELECT id, name FROM cpbl.players ORDER BY id",
    ),
    "games.csv": (
        ("year", "game_sno", "game_date"),
        "SELECT year, game_sno, game_date::text FROM cpbl.games "
        "WHERE kind_code = 'A' AND year BETWEEN 2023 AND 2026 ORDER BY 1, 2",
    ),
    "livelog_active.csv": (
        ("year", "game_sno", "half", "role", "acnt"),
        "SELECT DISTINCT l.year, l.game_sno, l.visiting_home_type, r.role, r.acnt "
        "FROM cpbl.game_livelog l "
        "CROSS JOIN LATERAL (VALUES ('B', l.hitter_acnt), ('P', l.pitcher_acnt), "
        "('C', l.catcher_acnt)) AS r(role, acnt) "
        "WHERE l.kind_code = 'A' AND l.year BETWEEN 2023 AND 2026 AND r.acnt IS NOT NULL "
        "AND r.acnt <> '' ORDER BY 1, 2, 3, 4, 5",
    ),
    "batting_box.csv": (
        ("year", "game_sno", "side", "acnt", "name", "uniform_no", "count_stat"),
        "SELECT year, game_sno, visiting_home_type, hitter_acnt, hitter_name, uniform_no, "
        "plate_appearances FROM cpbl.batting_gamelog "
        "WHERE kind_code = 'A' AND year BETWEEN 2023 AND 2026 ORDER BY 1, 2, 3, 4, 5, 6, 7",
    ),
    "pitching_box.csv": (
        ("year", "game_sno", "side", "acnt", "name", "uniform_no", "count_stat"),
        "SELECT year, game_sno, visiting_home_type, pitcher_acnt, pitcher_name, uniform_no, "
        "plate_appearances FROM cpbl.pitching_gamelog "
        "WHERE kind_code = 'A' AND year BETWEEN 2023 AND 2026 ORDER BY 1, 2, 3, 4, 5, 6, 7",
    ),
}


def _cell(v: object) -> str:
    return "" if v is None else str(v)


def _write_csv(path: Path, header: tuple[str, ...] | list[str], rows: list[list[str]]) -> str:
    """UTF-8、LF、無 BOM；回傳 SHA-256。內容完全由輸入決定（可重跑）。"""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    data = buf.getvalue().encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_digest(files: dict[str, str]) -> str:
    """快照身分＝各檔 SHA-256 的穩定組合（不含時間戳，同內容同 digest）。"""
    joined = "".join(f"{name} {sha}\n" for name, sha in sorted(files.items()))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _mask_url(url: str) -> str:
    return re.sub(r"://[^@/]*@", "://***@", url)


def cmd_snapshot(args: argparse.Namespace) -> int:
    import psycopg

    url = args.database_url or os.environ.get("DATABASE_URL")
    if not url:
        from cpbl.config import Settings

        url = Settings().database_url
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"[snapshot] DB 目標：{_mask_url(url)}（唯讀單交易）", file=sys.stderr)
    files: dict[str, str] = {}
    counts: dict[str, int] = {}
    with psycopg.connect(url, autocommit=False) as cx:
        cx.read_only = True
        cx.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        with cx.cursor() as cur:
            cur.execute("SHOW transaction_read_only")
            ro = cur.fetchone()
            if not ro or ro[0] != "on":
                raise SystemExit(f"[snapshot] 交易不是唯讀（transaction_read_only={ro}），停止")
            cur.execute("SHOW transaction_isolation")
            iso = cur.fetchone()
            if not iso or iso[0] != "repeatable read":
                raise SystemExit(f"[snapshot] 隔離等級不是 repeatable read（{iso}），停止")
            for name, (header, sql) in SNAPSHOT_QUERIES.items():
                cur.execute(sql)
                rows = [[_cell(v) for v in r] for r in cur.fetchall()]
                files[name] = _write_csv(out / name, header, rows)
                counts[name] = len(rows)
        cx.rollback()
    manifest = {
        "card": "#457",
        "taken_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "database": _mask_url(url),
        "transaction": "REPEATABLE READ, READ ONLY（單一交易，結束時 rollback）",
        "files": files,
        "row_counts": counts,
        "snapshot_digest": snapshot_digest(files),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"snapshot_digest": manifest["snapshot_digest"], "row_counts": counts},
                     ensure_ascii=False))
    return 0


# ------------------------------------------------------------------ 純計算（無 I/O）


@dataclass(frozen=True)
class Appearance:
    """REBAS 一位球員在一場一個半局一個角色的出現。"""

    sno: int
    half: str               # 1＝客隊進攻、2＝主隊進攻
    side: str               # 該球員所屬球隊：1＝客、2＝主
    name: str
    number: str             # 背號（REBAS playerNumber；捕手取自其所屬隊 batterBox）
    count_stat: int | None  # 打者 PA／投手 BF；捕手無


@dataclass
class Inputs:
    names: dict[str, set[str]]                          # 名冊姓名 → acnt 集合
    acnt_name: dict[str, str]                           # acnt → 名冊姓名
    active: dict[tuple[int, int, str, str], set[str]]   # (年, 場, 半局, 角色) → acnt
    game_dates: dict[tuple[int, int], str]              # (年, 場) → 日期
    box: dict[tuple[int, int, str, str], dict[str, tuple[str, str, str]]]
    # (年, 場, 側, 表 B|P) → acnt → (官方姓名, 背號, 計數)


@dataclass
class Collected:
    appearances: dict[tuple[int, str, str], list[Appearance]] = field(
        default_factory=lambda: collections.defaultdict(list))
    names_seen: dict[tuple[int, str, str], set[str]] = field(
        default_factory=lambda: collections.defaultdict(set))
    counters: collections.Counter = field(default_factory=collections.Counter)


def norm_number(v: object) -> str:
    return "" if v is None else str(v).strip()


def _opp(side: str) -> str:
    return "2" if side == "1" else "1"


def collect_appearances(games: list[dict]) -> Collected:
    """把 REBAS 逐場 JSON 展成 (年, 角色, playerId) → 出現列表。

    捕手：REBAS PA 只有 `catcherName`，id 只能從守備方 batterBox 同名取得；
    沒打擊（不在 batterBox）者無 id，只計數不進對照。
    同一 box 內同名多 id 者整組略過並計數（姓名無法區分，無從套規則）。
    """
    col = Collected()
    seen_games: set[tuple[int, int]] = set()
    for g in games:
        year = int(g["date"][:4])
        sno = int(g["seq"])
        if (year, sno) in seen_games:
            raise ValueError(f"REBAS 場次重複：{year} G{sno}")
        seen_games.add((year, sno))
        for bat, fld, half in (("away", "home", "1"), ("home", "away", "2")):
            bat_side, fld_side = half, _opp(half)
            fld_by_name: dict[str, dict[str, str]] = collections.defaultdict(dict)
            for p in g[fld + "BatterBox"]:
                if p.get("playerId"):
                    fld_by_name[p["playerName"]][p["playerId"]] = norm_number(p.get("playerNumber"))
            groups: dict[str, list[tuple[str, str | None, str, int | None, str]]] = {
                "B": [(p["playerName"], p.get("playerId"), norm_number(p.get("playerNumber")),
                       p.get("PA"), bat_side) for p in g[bat + "BatterBox"]],
                "P": [(p["playerName"], p.get("playerId"), norm_number(p.get("playerNumber")),
                       p.get("BF"), fld_side) for p in g[fld + "PitcherBox"]],
                "C": [],
            }
            catchers = sorted({pa["catcherName"] for pa in g[bat + "PAList"] if pa.get("catcherName")})
            for cn in catchers:
                ids = fld_by_name.get(cn, {})
                if not ids:
                    col.counters[(year, "C", "catcher_without_rebas_id")] += 1
                    continue
                for pid, num in sorted(ids.items()):
                    groups["C"].append((cn, pid, num, None, fld_side))
            for role, entries in groups.items():
                by_name: dict[str, set[str]] = collections.defaultdict(set)
                for nm, pid, *_ in entries:
                    if pid:
                        by_name[nm].add(pid)
                done: set[str] = set()
                for nm, pid, num, cnt, side in entries:
                    if not pid:
                        col.counters[(year, role, "box_entry_without_rebas_id")] += 1
                        continue
                    if len(by_name[nm]) > 1:
                        col.counters[(year, role, "same_name_multi_id_in_box")] += 1
                        continue
                    if pid in done:
                        continue
                    done.add(pid)
                    col.appearances[(year, role, pid)].append(
                        Appearance(sno, half, side, nm, num, cnt))
                    col.names_seen[(year, role, pid)].add(nm)
    return col


def rule_edges(col: Collected, inp: Inputs) -> dict[tuple[int, str, str], dict[str, int]]:
    """採用規則：名冊姓名 ∩ 同場同半局同角色實際帳號，恰一個才成為該場的證據邊。

    回傳 (年, 角色, playerId) → {acnt: 證據場數}。
    """
    edges: dict[tuple[int, str, str], dict[str, int]] = {}
    for (year, role, pid), apps in col.appearances.items():
        for a in apps:
            poss = inp.names.get(a.name, set()) & inp.active.get((year, a.sno, a.half, role), set())
            if len(poss) == 1:
                acs = edges.setdefault((year, role, pid), {})
                ac = next(iter(poss))
                acs[ac] = acs.get(ac, 0) + 1
    return edges


def classify_rule(col: Collected, edges: dict) -> dict[tuple[int, str, str], tuple[str, str]]:
    """逐年逐角色雙向唯一。回傳 key → (status, acnt)；非 unique 時 acnt 空。"""
    rev: dict[tuple[int, str, str], set[str]] = collections.defaultdict(set)
    for (year, role, pid), acs in edges.items():
        for a in acs:
            rev[(year, role, a)].add(pid)
    out: dict[tuple[int, str, str], tuple[str, str]] = {}
    for key in col.appearances:
        year, role, _pid = key
        acs = edges.get(key, {})
        if not acs:
            out[key] = ("unmatched", "")
        elif len(acs) > 1:
            out[key] = ("one_rebas_many_acnt", "")
        else:
            a = next(iter(acs))
            out[key] = ("many_rebas_one_acnt", "") if len(rev[(year, role, a)]) > 1 else ("unique", a)
    return out


def box_candidates(year: int, role: str, apps: list[Appearance], inp: Inputs) -> set[str]:
    """官方逐場 box 同場、同側、同背號的帳號，跨所有出現取交集（僅供人工清單證據）。

    捕手：用其所屬（守備）隊的打擊 box 背號，再交集該半局 livelog 實際捕手帳號。
    """
    table = "P" if role == "P" else "B"
    cand: set[str] | None = None
    for a in apps:
        rows = inp.box.get((year, a.sno, a.side, table), {})
        got = {ac for ac, (_nm, uni, _c) in rows.items() if a.number != "" and uni == a.number}
        if role == "C":
            got &= inp.active.get((year, a.sno, a.half, "C"), set())
        cand = got if cand is None else cand & got
        if not cand:
            return set()
    return cand or set()


def cross_conflicts(status: dict) -> dict[str, list]:
    """規則唯一的配對跨年、跨角色是否一致（同 id 多帳號／同帳號多 id）。"""
    by_pid: dict[str, set[str]] = collections.defaultdict(set)
    by_acnt: dict[str, set[str]] = collections.defaultdict(set)
    for (_y, _r, pid), (st, a) in status.items():
        if st == "unique":
            by_pid[pid].add(a)
            by_acnt[a].add(pid)
    return {
        "pid_to_many_acnt": sorted([p, sorted(s)] for p, s in by_pid.items() if len(s) > 1),
        "acnt_to_many_pid": sorted([a, sorted(s)] for a, s in by_acnt.items() if len(s) > 1),
    }


def corroborate(col: Collected, status: dict, inp: Inputs) -> dict:
    """規則唯一的配對逐場比對官方 box（背號、PA／BF）。捕手無對應 box 計數，略過。"""
    cnt: collections.Counter = collections.Counter()
    uni_ne: list[list] = []
    cnt_ne: list[list] = []
    for key in sorted(status):
        st, a = status[key]
        year, role, pid = key
        if st != "unique" or role == "C":
            continue
        for ap in sorted(col.appearances[key], key=lambda x: (x.sno, x.half)):
            row = inp.box.get((year, ap.sno, ap.side, role), {}).get(a)
            if row is None:
                cnt["no_official_box_row"] += 1
                continue
            _nm, uni, c = row
            u_ok = uni == ap.number
            c_ok = ap.count_stat is not None and c != "" and int(c) == int(ap.count_stat)
            cnt[f"uniform_{'eq' if u_ok else 'ne'}__count_{'eq' if c_ok else 'ne'}"] += 1
            rec = [year, role, pid, a, ap.sno, ap.number, uni, ap.count_stat, c]
            if not u_ok:
                uni_ne.append(rec)
            if not c_ok:
                cnt_ne.append(rec)
    return {
        "per_evidence_game": dict(sorted(cnt.items())),
        "uniform_mismatch": uni_ne,
        "count_stat_mismatch": cnt_ne,
        "row_layout": ["year", "role", "rebas_id", "acnt", "game_sno",
                       "rebas_number", "official_number", "rebas_PA_or_BF", "official_PA_or_BF"],
    }


REVIEW_HEADER = [
    "review_key", "rebas_player_id", "rebas_name", "year", "role", "role_label",
    "n_rebas_games", "candidate_acnt", "candidate_name_players", "candidate_names_official_box",
    "rebas_numbers", "n_games_uniform_match", "n_games_count_stat_match",
    "rule_match_same_acnt_elsewhere", "candidate_rule_mapped_same_year_role",
    "unmatched_reason", "需求方裁定", "裁定備註",
]
NO_CAND_HEADER = [
    "review_key", "rebas_player_id", "rebas_name", "year", "role", "role_label",
    "n_rebas_games", "rebas_numbers", "rebas_PA_or_BF_total", "unmatched_reason",
    "box_candidate_count",
]


def unmatched_reason(year: int, role: str, apps: list[Appearance], inp: Inputs) -> str:
    c: collections.Counter = collections.Counter()
    for a in apps:
        ids = inp.names.get(a.name, set())
        if not ids:
            c["name_not_in_players"] += 1
        else:
            poss = ids & inp.active.get((year, a.sno, a.half, role), set())
            c["name_not_active_in_half" if not poss else "name_multi_active_in_half"] += 1
    return ";".join(f"{k}={v}" for k, v in sorted(c.items()))


def build_review(col: Collected, status: dict, inp: Inputs) -> tuple[list[list[str]], list[list[str]], dict]:
    """對不上列 → (人工裁清單＝box 唯一候選, 無候選清單, 統計)。"""
    unique_by_acnt: dict[str, list[str]] = collections.defaultdict(list)
    used: dict[tuple[int, str, str], str] = {}
    for (y, r, pid), (st, a) in status.items():
        if st == "unique":
            unique_by_acnt[a].append(f"{y}{r}:{pid}")
            used[(y, r, a)] = pid
    review: list[list[str]] = []
    nocand: list[list[str]] = []
    stats: collections.Counter = collections.Counter()
    for key in sorted(status):
        if status[key][0] != "unmatched":
            continue
        year, role, pid = key
        apps = sorted(col.appearances[key], key=lambda a: (a.sno, a.half))
        rkey = f"{year}|{role}|{pid}"
        rname = "／".join(sorted(col.names_seen[key]))
        nums = "／".join(sorted({a.number for a in apps}))
        reason = unmatched_reason(year, role, apps, inp)
        cands = box_candidates(year, role, apps, inp)
        if len(cands) == 1:
            ac = next(iter(cands))
            table = "P" if role == "P" else "B"
            box_names: set[str] = set()
            n_uni = n_cnt = 0
            for a in apps:
                row = inp.box.get((year, a.sno, a.side, table), {}).get(ac)
                if row is None:
                    continue
                box_names.add(row[0])
                n_uni += row[1] == a.number
                if role != "C" and a.count_stat is not None and row[2] != "":
                    n_cnt += int(row[2]) == int(a.count_stat)
            review.append([
                rkey, pid, rname, str(year), role, ROLE_LABEL[role], str(len(apps)), ac,
                inp.acnt_name.get(ac, "（不在 players 名冊）"), "／".join(sorted(box_names)), nums,
                str(n_uni), "n/a" if role == "C" else str(n_cnt),
                "；".join(sorted(unique_by_acnt.get(ac, []))) or "（無）",
                used.get((year, role, ac), ""), reason, "", "",
            ])
            stats[f"box_unique_{role}"] += 1
        else:
            total = sum(a.count_stat or 0 for a in apps)
            nocand.append([
                rkey, pid, rname, str(year), role, ROLE_LABEL[role], str(len(apps)), nums,
                "n/a" if role == "C" else str(total), reason, str(len(cands)),
            ])
            stats[f"box_{'zero' if not cands else 'multi'}_{role}"] += 1
    return review, nocand, dict(sorted(stats.items()))


def stop_reasons(status: dict, conflicts: dict, cor: dict, n_review: int) -> list[str]:
    """核定規劃的停止條件：佐證背號衝突／跨年跨角色衝突／不唯一 > 0／清單 > 100 列。"""
    stops = []
    if cor["uniform_mismatch"]:
        stops.append(f"規則唯一配對有背號衝突 {len(cor['uniform_mismatch'])} 場")
    if conflicts["pid_to_many_acnt"] or conflicts["acnt_to_many_pid"]:
        stops.append("跨年／跨角色衝突 > 0")
    not_unique = sum(1 for st, _ in status.values() if st not in ("unique", "unmatched"))
    if not_unique:
        stops.append(f"不唯一 {not_unique} 列")
    if n_review > 100:
        stops.append(f"人工清單 {n_review} 列 > 100")
    return stops


# ------------------------------------------------------------------ review（讀檔 → 純計算 → 寫檔）


def load_inputs(snap: Path) -> Inputs:
    names: dict[str, set[str]] = collections.defaultdict(set)
    acnt_name: dict[str, str] = {}
    for r in _read_csv(snap / "players.csv"):
        names[r["name"]].add(r["id"])
        acnt_name[r["id"]] = r["name"]
    active: dict[tuple[int, int, str, str], set[str]] = collections.defaultdict(set)
    for r in _read_csv(snap / "livelog_active.csv"):
        active[(int(r["year"]), int(r["game_sno"]), r["half"], r["role"])].add(r["acnt"])
    game_dates = {(int(r["year"]), int(r["game_sno"])): r["game_date"]
                  for r in _read_csv(snap / "games.csv")}
    box: dict[tuple[int, int, str, str], dict[str, tuple[str, str, str]]] = collections.defaultdict(dict)
    for fname, table in (("batting_box.csv", "B"), ("pitching_box.csv", "P")):
        for r in _read_csv(snap / fname):
            k = (int(r["year"]), int(r["game_sno"]), r["side"], table)
            val = (r["name"], norm_number(r["uniform_no"]), r["count_stat"])
            prev = box[k].get(r["acnt"])
            if prev is not None and prev != val:
                raise ValueError(f"官方 box 同場同側同帳號有相異列：{fname} {k} {r['acnt']}")
            box[k][r["acnt"]] = val
    return Inputs(dict(names), acnt_name, dict(active), game_dates, dict(box))


def load_rebas_games(zip_dir: Path) -> tuple[list[dict], dict[str, str]]:
    zips = sorted(zip_dir.glob(ZIP_GLOB))
    if not zips:
        raise SystemExit(f"找不到 REBAS zip：{zip_dir}/{ZIP_GLOB}")
    games: list[dict] = []
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for n in sorted(zf.namelist()):
                if GAME_FILE_RE.search(n):
                    games.append(json.loads(zf.read(n)))
    return games, {z.name: _sha256_file(z) for z in zips}


def check_game_alignment(games: list[dict], inp: Inputs) -> dict:
    """REBAS (年, seq) 必須對上 DB kind A 同場且日期相同；不符即停（fail closed）。"""
    rebas = {(int(g["date"][:4]), int(g["seq"])): g["date"][:10] for g in games}
    missing = sorted(k for k in rebas if k not in inp.game_dates)
    date_ne = sorted(k for k, d in rebas.items() if k in inp.game_dates and inp.game_dates[k] != d)
    res = {"rebas_games_per_year": dict(sorted(collections.Counter(y for y, _ in rebas).items())),
           "db_kindA_games_per_year": dict(sorted(collections.Counter(y for y, _ in inp.game_dates).items())),
           "not_in_db": missing, "date_mismatch": date_ne}
    # 反向也要對：每年 REBAS 場數須等於 DB kind A 場數，否則整年漏讀會靜默變成「沒有資料」。
    if res["rebas_games_per_year"] != res["db_kindA_games_per_year"] or set(res["rebas_games_per_year"]) != set(YEARS):
        raise SystemExit(f"REBAS 與 DB 每年場數不一致：{json.dumps(res, ensure_ascii=False)}")
    if missing or date_ne:
        raise SystemExit(f"REBAS 場次對不上 DB：{json.dumps(res, ensure_ascii=False)}")
    return res


def cmd_review(args: argparse.Namespace) -> int:
    snap = Path(args.snapshot)
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    for name, sha in manifest["files"].items():
        if _sha256_file(snap / name) != sha:
            raise SystemExit(f"快照檔被改動：{name}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    inp = load_inputs(snap)
    games, zip_sha = load_rebas_games(Path(args.zips))
    align = check_game_alignment(games, inp)
    col = collect_appearances(games)
    edges = rule_edges(col, inp)
    status = classify_rule(col, edges)
    conflicts = cross_conflicts(status)
    cor = corroborate(col, status, inp)
    review, nocand, rstats = build_review(col, status, inp)

    rule_rows = []
    for key in sorted(status):
        year, role, pid = key
        st, a = status[key]
        rule_rows.append([pid, "／".join(sorted(col.names_seen[key])), str(year), role, a, st,
                          str(len(col.appearances[key])), str(edges.get(key, {}).get(a, 0) if a else 0)])
    shas = {
        "457_rule_results.csv": _write_csv(
            out / "457_rule_results.csv",
            ["rebas_player_id", "rebas_name", "year", "role", "acnt", "rule_status",
             "n_rebas_games", "n_evidence_games"], rule_rows),
        "457_manual_review.csv": _write_csv(out / "457_manual_review.csv", REVIEW_HEADER, review),
        "457_unmatched_no_candidate.csv": _write_csv(
            out / "457_unmatched_no_candidate.csv", NO_CAND_HEADER, nocand),
    }
    status_counts: dict[str, collections.Counter] = {}
    for (y, r, _p), (st, _a) in sorted(status.items()):
        status_counts.setdefault(f"{y}{r}", collections.Counter())[st] += 1
    distinct_unique = {r: len({p for (_y, rr, p), (st, _) in status.items() if rr == r and st == "unique"})
                       for r in ROLES}
    report = {
        "card": "#457",
        "inputs": {"snapshot_digest": manifest["snapshot_digest"], "snapshot_taken_at": manifest["taken_at"],
                   "rebas_zips_sha256": zip_sha},
        "game_alignment": align,
        "rule_status_per_year_role": {k: dict(sorted(v.items())) for k, v in status_counts.items()},
        "distinct_rebas_id_unique_by_role": distinct_unique,
        "cross_year_role_conflicts": conflicts,
        "collect_counters": {f"{y}{r}:{k}": v for (y, r, k), v in sorted(col.counters.items())},
        "review_stats": rstats,
        "review_rows": len(review),
        "no_candidate_rows": len(nocand),
        "corroboration": cor,
        "outputs_sha256": shas,
    }
    (out / "457_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {k: report[k] for k in ("rule_status_per_year_role", "distinct_rebas_id_unique_by_role",
                                       "cross_year_role_conflicts", "review_stats", "review_rows",
                                       "no_candidate_rows", "outputs_sha256")}
    summary["corroboration"] = cor["per_evidence_game"]
    print(json.dumps(summary, ensure_ascii=False, indent=1))

    stops = stop_reasons(status, conflicts, cor, len(review))
    if stops:
        print("[review] 觸及停止條件：" + "；".join(stops), file=sys.stderr)
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot", help="唯讀單交易凍結 DB 輸入")
    s.add_argument("--out", required=True, help="快照目錄")
    s.add_argument("--database-url", default=None, help="預設取環境變數 DATABASE_URL，再退回 cpbl.config")
    s.set_defaults(func=cmd_snapshot)
    r = sub.add_parser("review", help="純計算：規則結果＋人工裁清單＋佐證報告")
    r.add_argument("--snapshot", required=True, help="snapshot 產生的目錄")
    r.add_argument("--zips", default=DEFAULT_ZIP_DIR, help=f"REBAS zip 目錄（預設 {DEFAULT_ZIP_DIR}）")
    r.add_argument("--out", required=True, help="輸出目錄")
    r.set_defaults(func=cmd_review)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
