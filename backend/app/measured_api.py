from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .measured import load_measured_catalog
from .recommend import recommend
from .schemas import Recommendation, Weights, Workload

router = APIRouter(prefix="/measured", tags=["measured"])


class MeasuredRequest(BaseModel):
    workload: Workload
    weights: Weights | None = None


@router.get("/catalog")
def measured_catalog(min_items: int = 20):
    models, ignored = load_measured_catalog(min_items=min_items)
    return {"models": models, "ignored_runs": ignored}


@router.post("/recommend", response_model=Recommendation)
def measured_recommend(req: MeasuredRequest, min_items: int = 20):
    models, ignored = load_measured_catalog(min_items=min_items)
    if not models:
        raise HTTPException(422, detail={"message": "No usable benchmark runs. See ignored_runs for why.",
                                         "ignored_runs": ignored})
    try:
        return recommend(req.workload, models, req.weights)
    except ValueError as e:
        raise HTTPException(422, detail=str(e))
