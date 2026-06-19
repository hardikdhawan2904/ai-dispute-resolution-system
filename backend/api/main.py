"""
FastAPI application entry point for the BFSI Dispute Resolution Platform.
"""
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from database.database import init_db
from api.routes import disputes, health, auth, customer, dispute_tracking
from api.routes import ops_cases, ops_analytics, queues, communications
from api.websocket_manager import ws_manager
from api.executor import analysis_executor
from utils.logger import api_logger

# ── Lifespan ───────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    api_logger.info("=== BFSI Dispute Resolution Platform — Starting ===")
    init_db()
    api_logger.info("Database initialised")
    yield
    analysis_executor.shutdown(wait=False)
    api_logger.info("=== BFSI Dispute Resolution Platform — Shutdown ===")


# ── Application ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="BFSI Dispute Resolution Platform",
    description="Enterprise-grade banking dispute investigation and resolution system. Powered by LangGraph + Groq.",
    version=os.getenv("APP_VERSION", "1.0.0"),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ── Middleware ─────────────────────────────────────────────────────────────────

cors_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:3003",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = (time.time() - start) * 1000
    api_logger.info(
        f"{request.method} {request.url.path} → {response.status_code} [{elapsed:.0f}ms]",
        extra={"method": request.method, "path": request.url.path, "status": response.status_code},
    )
    return response


# ── Exception handlers ─────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    api_logger.error(f"Unhandled exception: {exc}", exc_info=True)
    origin = request.headers.get("origin", "")
    headers = {}
    if origin in cors_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error — please contact support", "type": type(exc).__name__},
        headers=headers,
    )


# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(disputes.router)
app.include_router(dispute_tracking.router)
app.include_router(customer.router)
app.include_router(ops_cases.router)
app.include_router(ops_analytics.router)
app.include_router(queues.router)
app.include_router(communications.router)

# Serve uploaded evidence files
import pathlib as _pl
_uploads_dir = _pl.Path("uploads")
_uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_uploads_dir)), name="uploads")


@app.websocket("/ws/disputes")
async def disputes_websocket(websocket: WebSocket):
    """Real-time dispute event stream for the internal review dashboard."""
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep connection alive; client sends pings
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        ws_manager.disconnect(websocket)


@app.get("/", include_in_schema=False)
def root():
    return {"service": "BFSI Dispute Resolution Platform", "status": "operational", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 8000)),
        reload=os.getenv("API_RELOAD", "true").lower() == "true",
    )
