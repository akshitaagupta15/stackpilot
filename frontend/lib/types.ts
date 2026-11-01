export type Workload = {
  name: string; monthly_requests: number; avg_input_tokens: number; avg_output_tokens: number;
  languages: string[]; requires_structured_output: boolean; data_sensitivity: "low" | "high";
  regions: string[]; quality_target?: number; p95_latency_ms?: number; monthly_budget_usd?: number;
};
export type Weights = { quality: number; cost: number; latency: number; reliability: number };
export type Candidate = {
  model_id: string; score: number; breakdown: Record<string, number>;
  expected_monthly_cost_usd: number; explanation: string;
};
export type Recommendation = {
  ranked: Candidate[]; rejected: { model_id: string; reasons: string[] }[];
  picks: Record<string, string | null>; weights_used: Weights;
  confidence: "low" | "medium" | "high"; caveats: string[];
};
export type CostEstimate = {
  model_id: string; pricing_verified_on: string;
  scenarios: { name: string; monthly_requests: number; cost_per_request_usd: number; monthly_cost_usd: number }[];
};
export type MeasuredModel = {
  id: string; provider: string; name: string; free_tier: boolean; source_run: string | null;
  metrics: { quality: number; quality_lenient: number | null; quality_by_language: Record<string, number>;
             latency_p95_ms: number; reliability: number; n_samples: number };
};
export type Attempt = { model: string; status: "ok" | "failed" | "skipped"; detail?: string; latency_ms?: number | null };
export type GatewayResult = {
  request_id: string; text: string; model_used: string; fallback_used: boolean; simulated: boolean;
  latency_ms: number | null; usage: { input_tokens: number | null; output_tokens: number | null };
  cost_usd: number | null; routing: { reason: string; attempts: Attempt[] };
};
export type Pcts = { p50: number | null; p95: number | null; p99: number | null };
export type Summary = {
  requests: number; success_rate: number | null; error_rate: number | null; fallback_rate: number | null;
  simulated_share: number | null; latency_ms: Pcts & { n: number };
  cost_usd: { total: number; avg_per_request: number | null; projected_30_day: number | null };
};
export type ModelHealth = {
  model: string; requests_served: number; latency_ms: Pcts; cost_usd: number; attempts: number;
  failed_attempts: number; attempt_failure_rate: number | null; status: string;
};
export type Point = { bucket: string; requests: number; failures: number; fallbacks: number; cost_usd: number };
export type RecentRequest = {
  request_id: string; time: string; served_model: string | null; success: boolean;
  fallback_used: boolean; latency_ms: number | null; cost_usd: number | null; reason: string;
};
