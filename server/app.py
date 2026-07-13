from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import groups, overview, persons


def create_app(db_path: Path) -> FastAPI:
    app = FastAPI(title="relationships")
    app.state.db_path = db_path
    app.include_router(persons.router, prefix="/api")
    app.include_router(overview.router, prefix="/api")
    app.include_router(groups.router, prefix="/api")
    dist = Path(__file__).resolve().parent.parent / "web" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app
