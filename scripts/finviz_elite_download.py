"""Finviz Elite eksportini `state/finviz_export.csv` ga saqlash."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.bootstrap_env import ensure_env_file, load_project_env  # noqa: E402
from agents.finviz_elite_export import fetch_export_csv_bytes  # noqa: E402


def main() -> int:
    ensure_env_file(_PROJECT_ROOT)
    load_project_env(_PROJECT_ROOT)
    out_dir = _PROJECT_ROOT / "state"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "finviz_export.csv"
    try:
        blob, _meta = fetch_export_csv_bytes()
    except Exception as exc:  # pragma: no cover
        print(str(exc), flush=True)
        return 1
    target.write_bytes(blob)
    print(f"Saved {target} ({len(blob)} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
