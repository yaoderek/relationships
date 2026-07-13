from pathlib import Path

import duckdb
from fastapi import HTTPException

_BUCKETS = {"day", "week", "month"}


def run(db_path: Path, sql: str, params: list | None = None) -> list[tuple]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(sql, params or []).fetchall()
    finally:
        con.close()


def bucket_expr(bucket: str, col: str = "m.ts_local") -> str:
    if bucket not in _BUCKETS:
        raise HTTPException(status_code=422,
                            detail=f"bucket must be one of {sorted(_BUCKETS)}")
    return f"strftime(date_trunc('{bucket}', {col}), '%Y-%m-%d')"
