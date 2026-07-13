"""FastAPI wiring for the Phase 0 local backend."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.admin import router as admin_router
from app.agents_catalog import router as agents_router
from app.agui_proxy import router as proxy_router
from app.catalog_service import seed_defaults
from app.db import SessionLocal, init_db
from app.logging_setup import get_logger, setup_logging
from app.session import router as session_router

setup_logging()
log = get_logger("http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables and seed the built-in agents (idempotent) on startup.
    await init_db()
    async with SessionLocal() as db:
        await seed_defaults(db)
    log.info("database ready")
    yield


app = FastAPI(title="Phase 0 backend", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    log.debug("--> %s %s", request.method, request.url.path)
    response = await call_next(request)
    log.debug("<-- %s %s %s", request.method, request.url.path, response.status_code)
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents_router)
app.include_router(proxy_router)
app.include_router(session_router)
app.include_router(admin_router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
