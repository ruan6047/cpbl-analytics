"""#392 開季切回賽季中的手動工具：需求方開季時下**一條指令**，把網站與排程從「球季結束」切回「賽季中」。

⛔ 不自動切回（需求方裁定 #9／#12）：何時執行由需求方決定（建議熱身賽開始前）。

一條指令（從**主 checkout 的 repo 根目錄**執行；它寫正式站、恢復爬 www）::

    uv run python -m cpbl.season_reopen            # 只印計畫（純推導，零寫入）
    uv run python -m cpbl.season_reopen apply      # 執行切回
    uv run python -m cpbl.season_reopen revoke     # 撤銷（誤跑時把本季切回紀錄作廢，正式站＋本機）

``apply`` 依序（任一步非零即停、印出已完成到哪一步；整條冪等，可整條重跑）：

1. **計畫**：純推導（忽略切回紀錄與 ``CPBL_SEASON_CLOSE``）各軍收官狀態；只對「已收官」的軍寫紀錄
   （季中誤跑 ⇒ 不寫任何東西、印原因）。二軍未收官（如和局）時只切一軍並印出。
2. **正式站**：``scripts/refresh-cpbl-prod.sh`` 的 ``SEASON_REOPEN_ONLY`` 單表模式——已驗證備份（獨立目錄）→
   ``prod_cpbl_api`` 內 ``migrate()`` → 單交易寫 ``cpbl.season_reopen`` → 讀回比對。首頁下一次請求即切回。
3. **本機**：``migrate()`` ＋ 寫 ``cpbl.season_reopen``（每日鏈、週跑、晚間鏈因此對該軍恢復爬取）。
4. **兩個先發 flag**：``starter-watch``／``postseason-starter-checkpoints``——已啟用不動；否則把最新的
   ``*.enabled.paused-*`` 改名回 ``*.enabled``；兩者都沒有就建空檔（存在即開，下次喚醒生效）。
5. **驗證**：本機 :func:`cpbl.season_close.league_closure` 該軍 ``closed=false``、``override=reopened``；
   正式站 ``GET /api/v1/daily/summary`` 的 ``season_close.major.closed``。

``revoke``：正式站與本機把「各軍當下最新球季」的紀錄填 ``revoked_at``（列保留成歷史）→ 驗證回到純推導。
先發 flag ⛔ 不動（印出人工撤回方式）。

失效規則：新球季例行賽第一場完賽 ⇒ 該軍最新球季前進 ⇒ 舊紀錄自然失效，下一季收官照常觸發；⛔ 不需清除。
⛔ 不刪 ``cpbl.games``、⛔ 不改 #391 收官判準：本模組只寫 ``cpbl.season_reopen``。

內部步驟（由 ``refresh-cpbl-prod.sh`` 的單表模式呼叫；目標＝「讀 stdin 腳本的 psql 指令」，shlex 切分、不經 shell）::

    python -m cpbl.season_reopen remote --action apply --rows major:2026,farm:2026 --target-psql "<psql 指令>"

退出碼：0 成功 · 64 參數錯／不在 repo 根目錄 · 69 目標尚無 ``cpbl.season_reopen`` 表 · 70 本機寫入失敗
        71 讀回不符 · 72 目標指令失敗（psql／ssh） · 73 寫入後驗證不符或讀不到（寫入已完成，可整條重跑）
        其餘非零＝``refresh-cpbl-prod.sh`` 原碼（如 64 參數守衛、78 Mac 已切換）。
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

from cpbl import season_close as sc

EXIT_USAGE = 64
EXIT_NO_TABLE = 69
EXIT_LOCAL = 70
EXIT_READBACK = 71
EXIT_TARGET = 72
EXIT_VERIFY = 73

ACTIONS = ("apply", "revoke")
REFRESH_SCRIPT = "scripts/refresh-cpbl-prod.sh"
DEFAULT_PROD_URL = "https://cpbl.ruan-ruan.com"
# 獨立於每日鏈備份輪替目錄（refresh-cpbl-prod.sh 會拒絕與每日鏈同一目錄）。
DEFAULT_BACKUP_DIR = Path.home() / "Library" / "Application Support" / "cpbl-analytics" / "backups-season-reopen"
# 交給 refresh-cpbl-prod.sh 時一律清掉的其他模式／每日鏈變數：單表模式不得被它們接走或改變。
_FOREIGN_MODE_ENV = (
    "WITH_DETAIL", "LINEUP_ONLY", "ROSTER_ONLY", "ROSTER_SCOPES", "POSTSEASON_RESULTS_ONLY",
    "POSTSEASON_BOXPA_ONLY", "TEAM_COMPARISON_ONLY", "DAILY_DAY_TYPE", "DAILY_FORCE_FULL",
    "DAILY_SENTINEL_MARKER", "PA_FULL_RESYNC",
)

Row = tuple[str, int]
_ROW_RE = re.compile(r"^(major|farm):((?:19|20)\d{2})$")


# =========================================================================== 列（軍, 球季）


def _norm(rows: Iterable[Row]) -> tuple[Row, ...]:
    out = []
    for league, season in rows:
        if league not in sc.LEAGUES or not isinstance(season, int) or not 1990 <= season <= 2100:
            raise ValueError(f"切回列只接受 (major|farm, 1990–2100)：{(league, season)!r}")
        out.append((league, season))
    if len(set(out)) != len(out):
        raise ValueError(f"切回列重複：{out!r}")
    return tuple(sorted(out))


def parse_rows(text: str) -> tuple[Row, ...]:
    """``"major:2026,farm:2026"`` → 排序後的列。空字串、格式錯、重複 ⇒ ``ValueError``（fail loud）。"""
    parts = (text or "").split(",")
    rows = []
    for part in parts:
        m = _ROW_RE.match(part)
        if not m:
            raise ValueError(f"切回列格式須為 major|farm:YYYY，以逗號分隔：{text!r}")
        rows.append((m.group(1), int(m.group(2))))
    return _norm(rows)


def format_rows(rows: Iterable[Row]) -> str:
    return ",".join(f"{league}:{season}" for league, season in _norm(rows))


def apply_rows(pure: Mapping[str, sc.LeagueClosure]) -> tuple[Row, ...]:
    """純推導為「已收官」的軍才寫紀錄（防永久關閉：紀錄必然指向某個已收官的季）。"""
    return _norm((lg, c.season) for lg, c in pure.items() if c.closed and c.season is not None)


def revoke_rows(latest: Mapping[str, int | None]) -> tuple[Row, ...]:
    """撤銷對象＝各軍當下最新球季（不依賴本機是否有紀錄：部分完成時正式站可能有、本機沒有）。"""
    return _norm((lg, season) for lg, season in latest.items() if season is not None)


# =========================================================================== SQL（只碰 cpbl.season_reopen）

_NOTE = "cpbl.season_reopen"
_APPLY = f"""INSERT INTO {sc.REOPEN_TABLE} AS t (league, season, reopened_at, revoked_at, note)
SELECT r.league, r.season, now(), NULL, '{_NOTE}'
FROM {{src}}
ON CONFLICT (league, season) DO UPDATE
SET reopened_at = EXCLUDED.reopened_at, revoked_at = NULL, note = EXCLUDED.note
WHERE t.revoked_at IS NOT NULL"""
# 已有效的紀錄不動（保留第一次執行的 reopened_at）；作廢過的才重記。
_REVOKE = f"""UPDATE {sc.REOPEN_TABLE} AS t SET revoked_at = now()
FROM {{src}}
WHERE t.league = r.league AND t.season = r.season AND t.revoked_at IS NULL"""
_STATUS = f"""SELECT r.league, r.season,
       CASE WHEN t.league IS NULL THEN 'absent' WHEN t.revoked_at IS NULL THEN 'active' ELSE 'revoked' END AS status
FROM {{src}}
LEFT JOIN {sc.REOPEN_TABLE} t ON t.league = r.league AND t.season = r.season
ORDER BY r.league, r.season"""
_STATEMENTS = {"apply": _APPLY, "revoke": _REVOKE, "status": _STATUS}


def _source(n: int, cell: Callable[[int], str]) -> str:
    return "(VALUES " + ", ".join(cell(i) for i in range(n)) + ") AS r(league, season)"


def _statement(action: str) -> str:
    if action not in _STATEMENTS:
        raise ValueError(f"未知動作：{action!r}")
    return _STATEMENTS[action]


def write_sql(action: str, rows: Iterable[Row]) -> tuple[str, list]:
    """psycopg 版本（本機）：``%s`` 參數化。"""
    rows = _norm(rows)
    sql = _statement(action).format(src=_source(len(rows), lambda _i: "(%s::text, %s::int)"))
    return sql, [v for row in rows for v in row]


def _literal_source(rows: tuple[Row, ...]) -> str:
    # 值已經 _norm 白名單（league ∈ LEAGUES、season 為 1990–2100 的 int），才轉成 psql 腳本的字面值。
    return _source(len(rows), lambda i: f"('{rows[i][0]}'::text, {int(rows[i][1])}::int)")


def _read_script(sql: str) -> str:
    return ("\\set QUIET on\n\\set ON_ERROR_STOP on\n\\pset tuples_only on\n\\pset format unaligned\n"
            f"BEGIN TRANSACTION READ ONLY;\n{sql};\nCOMMIT;\n")


def remote_exists_script() -> str:
    return _read_script(f"SELECT to_regclass('{sc.REOPEN_TABLE}') IS NOT NULL")


def remote_write_script(action: str, rows: Iterable[Row]) -> str:
    """psql 版本（正式站）：單一交易、statement／lock timeout 同既有單表模式先例。"""
    if action not in ACTIONS:
        raise ValueError(f"未知動作：{action!r}")
    rows = _norm(rows)
    sql = _statement(action).format(src=_literal_source(rows))
    return ("\\set QUIET on\n\\set ON_ERROR_STOP on\nBEGIN;\nSET LOCAL statement_timeout = '5s';\n"
            f"SET LOCAL lock_timeout = '1s';\n{sql};\nCOMMIT;\n")


def remote_status_script(rows: Iterable[Row]) -> str:
    return _read_script(_statement("status").format(src=_literal_source(_norm(rows))))


def write_local(connection, action: str, rows: Iterable[Row]) -> None:
    """本機寫入（呼叫端負責交易；``cpbl.db.conn()`` 會 commit／rollback）。"""
    sql, params = write_sql(action, rows)
    connection.execute(sql, params)


# =========================================================================== 正式站單表步驟（psql 目標）


class RemoteError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


class PsqlTarget:
    """以 psql 讀 stdin 腳本的目標（docker exec／ssh 皆可）；不經 shell 解讀。"""

    def __init__(self, command: str):
        self.argv = shlex.split(command)

    def run(self, script: str) -> str:
        proc = subprocess.run(self.argv, input=script, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RemoteError(EXIT_TARGET, f"目標指令失敗 rc={proc.returncode}：{proc.stderr.strip()}")
        return proc.stdout


def _parse_status(text: str) -> dict[Row, str]:
    out: dict[Row, str] = {}
    for line in text.strip().splitlines():
        league, season, state = line.split("|")
        out[(league, int(season))] = state
    return out


def remote(target, action: str, rows: Iterable[Row], *, out: IO[str] | None = None) -> int:
    """存在檢查（唯讀）→ 單交易寫入 → 讀回比對。表不存在 ⇒ 69、⛔ 不寫。"""
    out = out or sys.stdout
    rows = _norm(rows)
    exists = target.run(remote_exists_script()).strip()
    if exists != "t":
        raise RemoteError(EXIT_NO_TABLE, f"目標尚無 {sc.REOPEN_TABLE}（migrate 未生效？回傳 {exists!r}）；未寫入")
    target.run(remote_write_script(action, rows))
    try:
        status = _parse_status(target.run(remote_status_script(rows)))
    except ValueError as error:
        raise RemoteError(EXIT_READBACK, f"讀回格式無法辨識：{error}") from error
    bad = {r: s for r, s in status.items() if (s != "active") == (action == "apply")}
    if set(status) != set(rows) or bad:
        raise RemoteError(EXIT_READBACK, f"讀回不符（{action}）：{status!r}")
    states = ",".join(f"{lg}:{season}={state}" for (lg, season), state in sorted(status.items()))
    print(f"SEASON_REOPEN_REMOTE={action} rows={format_rows(rows)} status={states}", file=out)
    return 0


# =========================================================================== 兩個先發 flag


@dataclass(frozen=True)
class FlagResult:
    name: str
    action: str      # unchanged／renamed／created
    before: str
    after: str


def _flag_paths() -> list[Path]:
    # 一律用讀取端模組既有的路徑解析（⛔ 不重打路徑字串，避免漂移；env 覆寫照樣生效）。
    from cpbl.ingest import starter_checkpoints, starter_watch

    return [starter_watch.flag_path(), starter_checkpoints.flag_path()]


def restore_flag(path: Path) -> FlagResult:
    if path.exists():
        return FlagResult(path.name, "unchanged", str(path), str(path))
    paused = sorted(path.parent.glob(path.name + ".paused-*"), key=lambda p: p.name)
    if paused:
        src = paused[-1]
        src.rename(path)  # 同目錄原子改名
        return FlagResult(path.name, "renamed", str(src), str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=False)
    return FlagResult(path.name, "created", "(無)", str(path))


def restore_flags() -> list[FlagResult]:
    return [restore_flag(p) for p in _flag_paths()]


# =========================================================================== 一條指令


@dataclass
class Deps:
    """外部步驟（可替身）。``closure(reopen=...)`` 一律忽略 ``CPBL_SEASON_CLOSE``。"""
    closure: Callable[..., Mapping[str, sc.LeagueClosure]]
    latest: Callable[[], Mapping[str, int | None]]
    prod: Callable[[str, tuple[Row, ...]], int]
    local: Callable[[str, tuple[Row, ...]], None]
    flags: Callable[[], list[FlagResult]]
    fetch: Callable[[], Mapping]
    out: IO[str] = field(default_factory=lambda: sys.stdout)


def plan_report(pure: Mapping[str, sc.LeagueClosure], rows: tuple[Row, ...]) -> dict:
    return {"derived": {lg: {"season": c.season, "closed": c.closed, "status": c.status} for lg, c in pure.items()},
            "rows": format_rows(rows) if rows else ""}


def _say(deps: Deps, text: str) -> None:
    print(text, file=deps.out, flush=True)


def _stopped(deps: Deps, done: list[str], what: str, rc: int) -> int:
    _say(deps, f"✗ {what}（rc={rc}）；已完成：{'、'.join(done) or '無'}；之後的步驟未執行。整條指令冪等，排除原因後可整條重跑。")
    return rc


def _plan(deps: Deps) -> tuple[Mapping[str, sc.LeagueClosure], tuple[Row, ...]]:
    pure = deps.closure(reopen=False)
    rows = apply_rows(pure)
    for lg, c in pure.items():
        _say(deps, f"    {lg}: season={c.season} closed={c.closed} status={c.status}")
    for lg, c in pure.items():
        if not c.closed:
            _say(deps, f"    ⓘ {lg} 未收官（{c.status}）：不寫該軍紀錄；之後收官若需切回，再執行一次本工具")
    return pure, rows


def run_plan(deps: Deps) -> int:
    _say(deps, "==> 計畫（純推導，零寫入）")
    pure, rows = _plan(deps)
    _say(deps, json.dumps(plan_report(pure, rows), ensure_ascii=False))
    _say(deps, f"SEASON_REOPEN_ROWS={format_rows(rows) if rows else ''}")
    _say(deps, "執行切回：uv run python -m cpbl.season_reopen apply" if rows else "沒有已收官的軍：apply 不會寫任何紀錄")
    return 0


def _prod_major_closed(summary: Mapping) -> bool | None:
    major = ((summary or {}).get("season_close") or {}).get("major") or {}
    value = major.get("closed")
    return value if isinstance(value, bool) else None


def run_apply(deps: Deps) -> int:
    done: list[str] = []
    _say(deps, "==> 1/5 計畫（純推導）")
    pure, rows = _plan(deps)
    if not rows:
        _say(deps, "沒有已收官的軍（季中誤跑？）：未寫入任何紀錄，先發 flag 也未動。")
        return 0
    text = format_rows(rows)
    _say(deps, f"    SEASON_REOPEN_ROWS={text}")
    done.append("計畫")

    _say(deps, f"==> 2/5 正式站：備份 → migrate → 寫入 {text} → 讀回")
    rc = deps.prod("apply", rows)
    if rc != 0:
        return _stopped(deps, done, "正式站步驟失敗", rc)
    done.append("正式站")

    _say(deps, "==> 3/5 本機：migrate → 寫入")
    try:
        deps.local("apply", rows)
    except Exception as error:  # noqa: BLE001 — 印原因並停；整條可重跑
        _say(deps, f"    {type(error).__name__}: {error}")
        return _stopped(deps, done, "本機寫入失敗", EXIT_LOCAL)
    done.append("本機")

    _say(deps, "==> 4/5 兩個先發 flag")
    try:
        for r in deps.flags():
            _say(deps, f"    {r.name}: {r.action}（{r.before} → {r.after}）")
    except OSError as error:
        _say(deps, f"    {type(error).__name__}: {error}")
        return _stopped(deps, done, "先發 flag 恢復失敗", EXIT_LOCAL)
    done.append("先發 flag")

    _say(deps, "==> 5/5 驗證")
    leagues = {lg for lg, _ in rows}
    after = deps.closure(reopen=True)
    local_ok = all(not after[lg].closed and after[lg].override == sc.OVERRIDE_REOPENED for lg in leagues)
    _say(deps, "    本機：" + "、".join(f"{lg} closed={after[lg].closed} override={after[lg].override}" for lg in sorted(leagues)))
    expected_major = bool(pure.get("major") and pure["major"].closed and "major" not in leagues)
    try:
        prod_major = _prod_major_closed(deps.fetch())
    except Exception as error:  # noqa: BLE001 — 讀不到正式站 ⇒ 驗證失敗，寫入保留
        _say(deps, f"    正式站讀不到：{type(error).__name__}: {error}")
        prod_major = None
    _say(deps, f"    正式站：season_close.major.closed={prod_major}（預期 {expected_major}）")
    if not local_ok or prod_major is not expected_major:
        return _stopped(deps, done, "寫入後驗證不符或讀不到", EXIT_VERIFY)
    _say(deps, "==> 切回完成：首頁與排程回到賽季中。新球季首場完賽後紀錄自然失效，不需清除。")
    return 0


def run_revoke(deps: Deps) -> int:
    done: list[str] = []
    rows = revoke_rows(deps.latest())
    if not rows:
        _say(deps, "兩軍都讀不到最新球季：沒有可撤銷的紀錄。")
        return 0
    text = format_rows(rows)
    _say(deps, f"==> 1/3 正式站：備份 → migrate → 作廢 {text} → 讀回")
    rc = deps.prod("revoke", rows)
    if rc != 0:
        return _stopped(deps, done, "正式站步驟失敗", rc)
    done.append("正式站")

    _say(deps, "==> 2/3 本機：migrate → 作廢")
    try:
        deps.local("revoke", rows)
    except Exception as error:  # noqa: BLE001
        _say(deps, f"    {type(error).__name__}: {error}")
        return _stopped(deps, done, "本機作廢失敗", EXIT_LOCAL)
    done.append("本機")

    _say(deps, "==> 3/3 驗證（回到純推導）")
    after, pure = deps.closure(reopen=True), deps.closure(reopen=False)
    local_ok = all(after[lg].closed == pure[lg].closed for lg in pure)
    expected_major = bool(pure.get("major") and pure["major"].closed)
    try:
        prod_major = _prod_major_closed(deps.fetch())
    except Exception as error:  # noqa: BLE001
        _say(deps, f"    正式站讀不到：{type(error).__name__}: {error}")
        prod_major = None
    _say(deps, f"    本機 closed：{ {lg: after[lg].closed for lg in sorted(after)} }；"
               f"正式站 major.closed={prod_major}（預期 {expected_major}）")
    _say(deps, "    ⓘ 先發 flag 未動。要一併停用：mv logs/starter-watch.enabled logs/starter-watch.enabled.paused-$(date +%Y%m%d)；"
               "mv logs/postseason-starter-checkpoints.enabled logs/postseason-starter-checkpoints.enabled.paused-$(date +%Y%m%d)")
    if not local_ok or prod_major is not expected_major:
        return _stopped(deps, done, "作廢後驗證不符或讀不到", EXIT_VERIFY)
    _say(deps, "==> 撤銷完成：回到 #391 收官推導。")
    return 0


def prod_step(repo_root: Path, backup_dir: str, action: str, rows: tuple[Row, ...]) -> int:
    env = {k: v for k, v in os.environ.items() if k not in _FOREIGN_MODE_ENV}
    env.update({"SEASON_REOPEN_ONLY": "1", "SKIP_SCRAPE": "1", "SEASON_REOPEN_ACTION": action,
                "SEASON_REOPEN_ROWS": format_rows(rows), "BACKUP_DIR": backup_dir})
    proc = subprocess.run(["bash", str(repo_root / REFRESH_SCRIPT)], env=env, check=False)
    return proc.returncode


def _local_write(action: str, rows: tuple[Row, ...]) -> None:
    from cpbl.db import conn, migrate

    migrate()
    with conn() as c:
        write_local(c, action, rows)


def _fetch_summary(prod_url: str) -> Mapping:
    from urllib.request import urlopen

    with urlopen(f"{prod_url.rstrip('/')}/api/v1/daily/summary", timeout=20) as resp:  # noqa: S310 — 固定 https 端點
        return json.loads(resp.read().decode("utf-8"))


def default_deps(repo_root: Path, *, backup_dir: str, prod_url: str) -> Deps:
    def closure(*, reopen: bool):
        return sc.league_closure(env={}, reopen=reopen)

    def latest():
        return {lg: c.season for lg, c in sc.league_closure(env={}, reopen=False).items()}

    return Deps(closure=closure, latest=latest,
                prod=lambda action, rows: prod_step(repo_root, backup_dir, action, rows),
                local=_local_write, flags=restore_flags, fetch=lambda: _fetch_summary(prod_url))


def _repo_root() -> Path | None:
    cwd = Path.cwd()
    return cwd if (cwd / REFRESH_SCRIPT).is_file() and (cwd / "pyproject.toml").is_file() else None


def main(argv: list[str] | None = None) -> int:
    from cpbl.ingest._cli import cli_parser

    parser = cli_parser("python -m cpbl.season_reopen", __doc__)
    parser.add_argument("command", nargs="?", choices=("plan", "apply", "revoke", "remote"), default="plan")
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR),
                        help="正式站寫入前的備份目錄（絕對路徑；不得是每日鏈備份目錄）")
    parser.add_argument("--prod-url", default=DEFAULT_PROD_URL, help="驗證用正式站網址")
    parser.add_argument("--action", choices=ACTIONS, help="remote：apply／revoke")
    parser.add_argument("--rows", help="remote：major|farm:YYYY，以逗號分隔")
    parser.add_argument("--target-psql", help="remote：讀 stdin 腳本的 psql 指令（shlex 切分，不經 shell）")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.command == "remote":
        try:
            if not args.action or not args.target_psql:
                raise ValueError("remote 需要 --action 與 --target-psql")
            rows = parse_rows(args.rows or "")
        except ValueError as error:
            print(f"✗ {error}", file=sys.stderr)
            return EXIT_USAGE
        try:
            return remote(PsqlTarget(args.target_psql), args.action, rows)
        except RemoteError as error:
            print(f"✗ {error}", file=sys.stderr)
            return error.code

    root = _repo_root()
    if root is None:
        print(f"✗ 請在 repo 根目錄（主 checkout）執行：找不到 ./{REFRESH_SCRIPT} 或 ./pyproject.toml。"
              "先發 flag 的相對路徑也以 repo 根目錄解析。", file=sys.stderr)
        return EXIT_USAGE
    if args.command != "plan" and not os.path.isabs(args.backup_dir):
        print("✗ --backup-dir 必須是絕對路徑", file=sys.stderr)
        return EXIT_USAGE
    deps = default_deps(root, backup_dir=args.backup_dir, prod_url=args.prod_url)
    return {"plan": run_plan, "apply": run_apply, "revoke": run_revoke}[args.command](deps)


if __name__ == "__main__":
    raise SystemExit(main())
