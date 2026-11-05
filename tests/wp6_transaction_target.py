"""原故障5專用target fixture，僅stdlib/mock＋既有產品依賴；不是通用重播CLI。"""

import contextlib
import os
import socket
import sys
import time
from pathlib import Path
from unittest import mock


def main():
    if os.environ.get("CPBL_WP6_EXECUTE") != "1":
        return 78
    from wp6_393_support import (
        claim_case,
        json_bytes,
        load_plan,
        original_job,
        require,
        transaction_game_fingerprint,
    )

    plan = load_plan(); spec = plan["native"]["transaction-sigterm"]
    require(socket.gethostname() == spec["hostname"], "wp6_target_container_binding")
    from cpbl import db
    from cpbl.ingest import cpbl_site

    class Patches:
        def __init__(self, stack):
            self.stack = stack
        def setattr(self, obj, key, value):
            self.stack.enter_context(mock.patch.object(obj, key, value))
        def setenv(self, key, value):
            self.stack.enter_context(mock.patch.dict(os.environ, {key: value}))
        def delenv(self, key, raising=False):
            original = os.environ.copy(); os.environ.pop(key, None)
            self.stack.callback(lambda: (os.environ.clear(), os.environ.update(original)))

    original = db.conn
    relative = Path(spec["ready_file"])
    require(not relative.is_absolute() and ".." not in relative.parts, "wp6_ready_namespace")
    ready = Path(plan["private_root"]) / relative
    key = plan["cases"]["transaction-sigterm"]["transaction_key"]
    require(key in plan["cases"]["transaction-sigterm"]["sample_keys"], "wp6_transaction_true_game")

    @contextlib.contextmanager
    def before_commit():
        # cpbl_site.conn只服務此games寫入；原UPSERT先真執行，外層原conn尚未commit。
        with original() as connection:
            yield connection
            xid = connection.execute("SELECT txid_current_if_assigned()").fetchone()[0]
            require(xid is not None, "wp6_real_write_transaction_required")
            changed = transaction_game_fingerprint(connection, key)
            require(not ready.exists(), "wp6_no_signal_case_retry")
            with ready.open("xb") as stream:
                stream.write(json_bytes({"lease_id": plan["lease_id"], "input_sha256": plan["input_sha256"],
                                         "target_cid": spec["cid"], "pg_backend_pid": connection.info.backend_pid,
                                         "uncommitted_game_fingerprint": changed,
                                         "transaction_assigned": True, "ready_before_commit": True}))
            time.sleep(spec["signal_wait_seconds"])
            raise AssertionError("wp6_signal_not_delivered")

    with contextlib.ExitStack() as stack:
        patches = Patches(stack)
        patches.setattr(cpbl_site, "conn", before_commit)
        with original_job(plan, "transaction-sigterm", patches) as (jobs, case, output, intents, trace):
            claim_case(output)
            rc = jobs.main(case["argv"])
            (output / "target-result.json").write_bytes(json_bytes({"job_exit": rc, "native_target": True}))
            return rc


if __name__ == "__main__":
    sys.exit(main())
