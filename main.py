from fastapi import FastAPI

from app.db import init_db
from app.routes.leads import router as leads_router


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title="GordoveCode Lead Assistant")
    app.include_router(leads_router)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
