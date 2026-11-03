export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Classification = "HOT" | "WARM" | "COLD";
export type Confidence = "HIGH" | "MEDIUM" | "LOW";

export interface FieldReport {
  field: string;
  label: string;
  status: "valid" | "missing" | "invalid";
  message: string;
  raw: string | null;
  normalized: string | null;
  check?: "format_only" | null; // email / phone / website are format-checked, never verified
  warning?: string | null; // e.g. reserved example domain
}
export interface ValidationReport {
  usable: boolean;
  fields: FieldReport[];
  missing: string[];
  invalid: string[];
  messages: string[];
  warnings?: string[];
}
export interface AssessmentSummary {
  id: number;
  score: number;
  classification: Classification;
  confidence_level: Confidence;
  assessed_at: string;
}
export interface Lead {
  id: number;
  name: string | null;
  company_name: string | null;
  website: string | null;
  job_title: string | null;
  industry: string | null;
  company_location: string | null;
  company_size: string | null;
  lead_source: string | null;
  requirement: string | null;
  email: string | null;
  phone: string | null;
  validation_report: ValidationReport | null;
  created_at: string;
  latest_assessment: AssessmentSummary | null;
}
export interface ScoreBreakdown {
  parameter: string;
  label: string;
  max_score: number;
  score: number;
  criteria: string;
  rule_applied: string;
  explanation: string;
}
export interface Assessment {
  id: number;
  lead_id: number;
  score: number;
  classification: Classification;
  confidence_level: Confidence;
  confidence_score: number;
  confidence_details: {
    components: Record<string, { score: number; max: number }>;
    notes: string[];
    contradictions: string[];
    disclaimer: string;
  };
  positive_factors: string[];
  negative_factors: string[];
  scoring_explanation: string;
  quality_assessment: string;
  ai_explanation: string;
  business_insights: string[];
  recommended_next_action: string;
  explanation_source: "gemini" | "rule_based";
  gemini_model: string | null;
  gemini_error: string | null;
  config_snapshot: {
    weights: Record<string, number>;
    hot_threshold: number;
    warm_threshold: number;
    negative_intent_max_classification?: Classification;
    score_band?: Classification;
    classification_safeguard?: { rule: string; score_band: Classification; applied_classification: Classification; message: string } | null;
  };
  assessed_at: string;
  breakdown: ScoreBreakdown[];
}
export interface HistoryItem {
  id: number;
  assessment_id: number;
  score: number;
  classification: Classification;
  confidence_level: Confidence;
  explanation_source: string;
  created_at: string;
}
export interface Overview {
  total_leads: number;
  assessed_leads: number;
  unassessed_leads: number;
  hot_leads: number;
  warm_leads: number;
  cold_leads: number;
  average_score: number | null;
  classification_distribution: { name: string; value: number }[];
  score_distribution: { range: string; count: number }[];
  confidence_distribution: { name: string; value: number }[];
  category_statistics: {
    classification: Classification;
    count: number;
    percentage: number;
    average_score: number | null;
    min_score: number | null;
    max_score: number | null;
  }[];
}
export interface LeadList {
  items: Lead[];
  total: number;
  limit: number;
  offset: number;
}
export type LeadInput = Partial<Record<
  | "name" | "company_name" | "website" | "job_title" | "industry" | "company_location"
  | "company_size" | "lead_source" | "requirement" | "email" | "phone",
  string
>>;

export class ApiError extends Error {
  status: number;
  validation?: ValidationReport;
  constructor(message: string, status: number, validation?: ValidationReport) {
    super(message);
    this.status = status;
    this.validation = validation;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      `Cannot reach the API at ${API_BASE}. Start the backend (uvicorn app.main:app --port 8000) and try again.`,
      0,
    );
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    let validation: ValidationReport | undefined;
    try {
      const body = await res.json();
      const d = body.detail;
      if (typeof d === "string") message = d;
      else if (d?.message) {
        message = d.message;
        validation = d.validation;
      } else if (Array.isArray(d)) message = d.map((e: { msg: string }) => e.msg).join("; ");
    } catch {}
    throw new ApiError(message, res.status, validation);
  }
  return res.json() as Promise<T>;
}

export const api = {
  overview: () => request<Overview>("/api/analytics/overview"),
  leads: (p: { search?: string; classification?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (p.search) q.set("search", p.search);
    if (p.classification) q.set("classification", p.classification);
    q.set("limit", String(p.limit ?? 20));
    q.set("offset", String(p.offset ?? 0));
    return request<LeadList>(`/api/leads?${q}`);
  },
  lead: (id: number | string) => request<Lead>(`/api/leads/${id}`),
  createLead: (body: LeadInput) =>
    request<{ lead: Lead; validation: ValidationReport }>("/api/leads", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  assess: (id: number | string) =>
    request<Assessment>(`/api/leads/${id}/assess`, { method: "POST" }),
  assessment: (id: number | string) => request<Assessment>(`/api/leads/${id}/assessment`),
  history: (id: number | string) => request<HistoryItem[]>(`/api/leads/${id}/history`),
};
