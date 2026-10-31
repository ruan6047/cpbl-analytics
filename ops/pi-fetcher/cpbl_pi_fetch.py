"""Standalone WP3 entry: copy with the two stdlib/Playwright source files, no cpbl install."""

import importlib.util
from pathlib import Path

source = Path(__file__).resolve().parents[2] / "src/cpbl/ingest/www_fetch.py"
spec = importlib.util.spec_from_file_location("cpbl_www_fetch", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if __name__ == "__main__":
    raise SystemExit(module.main())
