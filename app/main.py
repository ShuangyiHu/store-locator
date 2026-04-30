import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.core.cache import ping as cache_ping
from app.database import engine
from app.routers import admin_stores as admin_stores_router
from app.routers import admin_users as admin_users_router
from app.routers import auth as auth_router
from app.routers import search as search_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection OK")
    except Exception as exc:
        logger.warning("Database ping failed at startup: %s", exc)

    app.state.settings = settings
    yield
    engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])
    app.include_router(search_router.router, prefix="/api/stores", tags=["search"])
    app.include_router(
        admin_stores_router.router,
        prefix="/api/admin/stores",
        tags=["admin-stores"],
    )
    app.include_router(
        admin_users_router.router,
        prefix="/api/admin/users",
        tags=["admin-users"],
    )

    @app.get("/health", tags=["health"])
    def health_check():
        db_ok = True
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            db_ok = False
        cache_ok = cache_ping()
        return {
            "status": "ok" if (db_ok and cache_ok) else "degraded",
            "db": "connected" if db_ok else "disconnected",
            "cache": "connected" if cache_ok else "disconnected",
        }

    return app


app = create_app()
