from fastapi import APIRouter, Request

from ..db import bucket_expr, run

router = APIRouter()


@router.get("/overview/timeseries")
def overview_timeseries(request: Request, bucket: str = "month"):
    sql = f"""
        SELECT {bucket_expr(bucket, col="ts_local")} AS bucket,
               count(*) FILTER (WHERE is_from_me) AS sent,
               count(*) FILTER (WHERE NOT is_from_me) AS received
        FROM messages GROUP BY 1 ORDER BY 1
    """
    return [{"bucket": r[0], "sent": r[1], "received": r[2]}
            for r in run(request.app.state.db_path, sql)]
