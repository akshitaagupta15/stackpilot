from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class Metrics(BaseModel):
    quality: float = Field(ge=0, le=1)
    latency_p95_ms: float = Field(gt=0)
    reliability: float = Field(ge=0, le=1)
    source: Literal["estimated", "benchmark"] = "estimated"
    n_samples: int = 0                                  # successful requests behind the numbers
    quality_lenient: Optional[float] = None             # counts JSON found inside extra text
    quality_by_language: dict[str, float] = {}
    truncated_rate: Optional[float] = None              # share of answers cut off by the max_tokens limit
    max_tokens: Optional[int] = None                    # the limit used in the benchmark run


class ModelSpec(BaseModel):
    id: str
    provider: str
    name: str
    context_window: int
    price_input_per_mtok: float = Field(ge=0)   # USD per 1M input tokens
    price_output_per_mtok: float = Field(ge=0)  # USD per 1M output tokens
    pricing_verified_on: str
    structured_output: bool
    regions: list[str]
    languages: list[str]
    data_policy: Literal["no_training", "may_train"]
    metrics: Metrics
    free_tier: bool = False
    source_run: Optional[str] = None


class Workload(BaseModel):
    name: str
    monthly_requests: int = Field(gt=0)
    avg_input_tokens: int = Field(gt=0)
    avg_output_tokens: int = Field(gt=0)
    languages: list[str] = ["en"]
    requires_structured_output: bool = False
    data_sensitivity: Literal["low", "high"] = "low"
    regions: list[str] = []                       # empty = any region
    quality_target: Optional[float] = Field(default=None, ge=0, le=1)
    p95_latency_ms: Optional[float] = Field(default=None, gt=0)
    monthly_budget_usd: Optional[float] = Field(default=None, gt=0)


class Weights(BaseModel):
    quality: float = Field(default=0.40, ge=0)
    cost: float = Field(default=0.25, ge=0)
    latency: float = Field(default=0.20, ge=0)
    reliability: float = Field(default=0.15, ge=0)


class CostScenario(BaseModel):
    name: str
    monthly_requests: int
    cost_per_request_usd: float
    monthly_cost_usd: float


class CostEstimate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_id: str
    pricing_verified_on: str
    scenarios: list[CostScenario]  # low, expected, high


class Candidate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_id: str
    score: float
    breakdown: dict[str, float]
    expected_monthly_cost_usd: float
    explanation: str


class Rejection(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_id: str
    reasons: list[str]


class Recommendation(BaseModel):
    ranked: list[Candidate]
    rejected: list[Rejection]
    picks: dict[str, Optional[str]]
    weights_used: Weights
    confidence: Literal["low", "medium", "high"]
    caveats: list[str]
