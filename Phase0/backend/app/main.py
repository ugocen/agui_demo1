"""FastAPI wiring for the Phase 0 local backend."""

from pathlib import Path

from dotenv import load_dotenv

# Load env with component-local precedence: a backend/.env (enterprise overlay,
# per-component config) wins over the repo-root Phase0/.env (personal/dev single
# file), and real process env vars win over both (override=False). Same code
# runs in either layout with no edits.
_APP_DIR = Path(__file__).resolve().parent
for _env_file in (_APP_DIR.parent / ".env", _APP_DIR.parent.parent / ".env"):
    if _env_file.exists():
        load_dotenv(_env_file)

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.admin import router as admin_router
from app.agents_catalog import router as agents_router
from app.agents_catalog import sync_catalog
from app.agui_proxy import router as proxy_router
from app.db import SessionLocal, init_db
from app.logging_setup import get_logger, setup_logging
from app.session import router as session_router

setup_logging()
log = get_logger("http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables, then warm the catalog from AgentCore (best-effort). Agents
    # come only from AgentCore — nothing is seeded from env. If AgentCore is
    # unreachable at boot (no creds/region/network), the catalog fills on the
    # first /api/agentcore/runtimes call or admin "Sync" instead.
    await init_db()
    try:
        async with SessionLocal() as db:
            runtimes = await sync_catalog(db)
        log.info("catalog synced from AgentCore: %d AG-UI runtime(s)", len(runtimes))
    except Exception as error:  # noqa: BLE001 — never block startup on discovery
        log.warning("startup AgentCore sync skipped: %s", error)
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
