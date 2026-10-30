from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .catalog import load_catalog
from .cost import estimate_cost
from .recommend import recommend
from .schemas import CostEstimate, ModelSpec, Recommendation, Weights, Workload
from .measured_api import router as measured_router
app = FastAPI(title="StackPilot", version="0.1.0")
app.include_router(measured_router)


class RecommendRequest(BaseModel):
    workload: Workload
    weights: Weights | None = None


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
