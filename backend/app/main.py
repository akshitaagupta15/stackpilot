import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from .account_api import account_router, auth_router
from .catalog import load_catalog
from .cost import estimate_cost
from .db import get_db, get_engine
from .gateway_api import admin_router, gateway_router
from .measured_api import router as measured_router
from .monitor_api import router as monitor_router
from .recommend import recommend
from .schemas import CostEstimate, ModelSpec, Recommendation, Weights, Workload
from .seed_demo import ensure_demo

log = logging.getLogger("stackpilot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("SEED_DEMO_ON_START") == "1":
        try:
            with Session(get_engine()) as s:
                info = ensure_demo(s, n=int(os.environ.get("DEMO_SEED_N", "4000")),
                                   viewer_key=os.environ.get("DEMO_VIEWER_KEY"))
            log.info("demo data ready: %s", info)
        except Exception:  # never block startup because of demo data
            log.exception("demo seeding failed; continuing without it")
    yield


app = FastAPI(title="StackPilot", version="0.5.0", lifespan=lifespan)
origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                   allow_headers=["Content-Type", "X-API-Key", "X-Admin-Token", "X-Requested-With"])
app.include_router(measured_router)
app.include_router(gateway_router)
app.include_router(monitor_router)
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(account_router)


class RecommendRequest(BaseModel):
    workload: Workload
    weights: Weights | None = None


@app.get("/")
def root():
    return {"name": "StackPilot", "docs": "/docs", "health": "/health", "ready": "/ready"}


@app.get("/health")
def health():
    """Liveness: the process is up. Does not touch the database."""
    return {"status": "ok"}


@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness: the database answers."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "database unavailable")
    return {"status": "ok", "database": "ok", "version": app.version,
            "simulated_provider": os.environ.get("DEMO_MODE") == "1" or not os.environ.get("OPENROUTER_API_KEY")}


@app.get("/catalog", response_model=list[ModelSpec])
def catalog():
    return load_catalog()


@app.post("/cost", response_model=list[CostEstimate])
def cost(w: Workload):
    return [estimate_cost(m, w) for m in load_catalog()]


@app.post("/recommend", response_model=Recommendation)
def recommend_endpoint(req: RecommendRequest):
    try:
        return recommend(req.workload, load_catalog(), req.weights)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
