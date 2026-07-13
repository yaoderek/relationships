import argparse
from pathlib import Path

import uvicorn

from .app import create_app


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m server")
    p.add_argument("--db", type=Path, default=Path("data/analytics.duckdb"))
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    if not args.db.exists():
        raise SystemExit(f"{args.db} not found — run `python -m ingest` first "
                         "(or `python scripts/make_demo.py` for demo data)")
    uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
