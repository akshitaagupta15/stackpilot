from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .catalog import load_catalog
from .cost import estimate_cost
from .gateway_api import admin_router, gateway_router
from .measured_api import router as measured_router
from .monitor_api import router as monitor_router
from .recommend import recommend
from .schemas import CostEstimate, ModelSpec, Recommendation, Weights, Workload

app = FastAPI(title="StackPilot", version="0.3.0")
app.include_router(measured_router)
app.include_router(gateway_router)
app.include_router(monitor_router)
app.include_router(admin_router)


class RecommendRequest(BaseModel):
    workload: Workload
    weights: Weights | None = None


@app.get("/")
def root():
    return {"name": "StackPilot", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    return {"status": "ok"}


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
