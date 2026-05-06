"""`.env`: izohlardan tiklash hamda aktiv takrorlarni tuzatish."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.restore_dotenv_active import restore_env_file


def main() -> int:
    parser = argparse.ArgumentParser(description=".env ni izoh va aktiv takrorlardan tiklash.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    ns = parser.parse_args()
    code, msg = restore_env_file(_PROJECT_ROOT, dry_run=ns.dry_run, backup=not ns.no_backup)
    print(msg, flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
