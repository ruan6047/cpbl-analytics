"""#393：完整私有包 → 單一賽程 scope → 原 writer，不 migration／取源。

單次 jobs 命令（DATABASE_URL 由受保護環境明確注入；工作目錄不得有 .env）：
    python -m cpbl.ingest.run_replay_games --year 2026 --kind A \
        --manifest /requests/original.json --bundle /inbox/fixed-run
兩個路徑均須私有唯讀掛載，原 manifest 由消費端獨立保存，不取包內副本。
此薄入口僅接受單字母 kind，且必須與原 manifest 的單一賽程 scope 相同。
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
from contextlib import redirect_stderr
from pathlib import Path

from cpbl.ingest._cli import cli_parser

VERSION = "393-wp4.1"


def _kind(value: str) -> str:
    # 只收可安全回報的單一賽別字母；是否為本次scope仍由原manifest綁定。
    if len(value) != 1 or not "A" <= value <= "Z":
        raise ValueError("single_kind_required")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = cli_parser("python -m cpbl.ingest.run_replay_games", __doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--kind", type=_kind, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    result = {"version": VERSION, "ok": False, "contract_passed": False, "stage": "arguments"}
    try:
        # argparse 的錯誤預設會回顯參數；只保留非零碼，避免不當輸入洩入 job log。
        with redirect_stderr(io.StringIO()):
            args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code:
            print(json.dumps(result))
        return int(exc.code or 0)

    result.update(year=args.year, kind=args.kind, input_count=None, written_count=None)
    previous = {key: os.environ.get(key) for key in ("CPBL_REPLAY_MANIFEST", "CPBL_REPLAY_BUNDLE")}
    session = db = None
    pool_log = logging.getLogger("psycopg.pool")
    log_disabled = pool_log.disabled
    try:
        result["stage"] = "environment"
        # config.settings 會讀 cwd/.env；先拒絕，之後才載入 DB／parser 模組。
        if os.path.lexists(".env") or not os.environ.get("DATABASE_URL"):
            raise ValueError("explicit_environment_required")
        manifest, bundle = args.manifest.absolute(), args.bundle.absolute()
        if manifest.resolve().is_relative_to(bundle.resolve()):
            raise ValueError("independent_manifest_required")
        from cpbl.ingest import _browser, www_fetch

        result["stage"] = "manifest"
        with manifest.open("rb") as stream:
            raw = stream.read(www_fetch.MAX_INDEX_BYTES + 1)
        m = www_fetch.parse_manifest(raw)
        result["manifest_sha256"] = www_fetch.digest(raw)
        result["stage"] = "scope"
        requests = m["requests"]
        if len(requests) != 2:
            raise ValueError("one_schedule_scope_required")
        page, post = requests
        if (page["op"] != "page" or page["path"] != "/schedule"
                or post["op"] != "post" or post["page"] != page["id"]
                or post["api"] != "/schedule/getgamedatas"
                or post.get("form") != {"calendar": f"{args.year}/01/01", "location": "", "kindCode": args.kind}):
            raise ValueError("scope_mismatch")
        os.environ["CPBL_REPLAY_MANIFEST"] = str(manifest)
        os.environ["CPBL_REPLAY_BUNDLE"] = str(bundle)
        result["stage"] = "bundle"
        session = _browser.session()
        if session.index["manifest_sha256"] != result["manifest_sha256"]:
            raise ValueError("manifest_changed")
        with (bundle / "index.json").open("rb") as stream:
            index_raw = stream.read(www_fetch.MAX_INDEX_BYTES + 1)
        if len(index_raw) > www_fetch.MAX_INDEX_BYTES:
            raise ValueError("index_size_limit")
        result["index_sha256"] = hashlib.sha256(index_raw).hexdigest()

        from cpbl import db
        from cpbl.ingest import cpbl_site
        from cpbl.ingest.game_source_revisions import canonical_source_version

        result["stage"] = "parse"
        rows = cpbl_site.fetch_year(args.year, args.kind)
        if not isinstance(rows, list) or any(
            not isinstance(row, dict)
            or cpbl_site._i(row.get("Year")) != args.year
            or row.get("KindCode") != args.kind
            or row.get("GameSeasonCode") is None
            or cpbl_site._i(row.get("GameSno")) is None
            for row in rows
        ):
            raise ValueError("payload_scope_mismatch")
        result.update(contract_passed=True, input_count=len(rows), parsed_sha256=canonical_source_version(rows))
        result["stage"] = "write"
        pool_log.disabled = True  # 連線錯誤只由下面的安全摘要回報，不回顯 DSN／參數。
        written = cpbl_site.upsert_games(rows)
        if type(written) is not int:
            raise ValueError("invalid_writer_result")
        result.update(ok=True, stage="complete", written_count=written)
    except Exception:
        # 第一失敗階段保留；原兩交易可能部分提交，不能以此摘要聲稱已整體 rollback。
        result["ok"] = False
    finally:
        try:
            if session is not None:
                session.close()
            if db is not None and db._pool is not None:
                db._pool.close()
        except Exception:
            if result["ok"]:
                result.update(ok=False, stage="close")
        pool_log.disabled = log_disabled
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
