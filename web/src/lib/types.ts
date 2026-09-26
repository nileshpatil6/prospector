export type RunStatus = "running" | "done" | "failed" | "max_steps";
export type Label = "good" | "bad";

export interface Step {
  n: number;
  thought: string;
  action: string;
  args: Record<string, unknown>;
  observation: string;
  ok: boolean;
  ms: number;
}

export interface BBox {
  south: number;
  west: number;
  north: number;
  east: number;
}

export interface Lead {
  id: string;
  name: string;
  niche: string;
  lat: number;
  lon: number;
  address: string;
  phone: string;
  website: string;
  opening_hours: string;
  source_url: string;
  emails: string[];
  has_booking: boolean | null;
  chat_widget: string;
  has_contact_form: boolean | null;
  site_ok: boolean | null;
  fetch_error: string;
  research: Record<string, unknown>;
  score: number;
  reasons: string[];
  hook: string;
  receptionist_prompt: string;
  messages: TakenMessageRecord[];
}

export interface TakenMessageRecord {
  caller_name: string;
  callback_number: string;
  reason: string;
  ts: number;
}

export interface LiveSessionResponse {
  token: string;
  model: string;
  config: Record<string, unknown>;
}

export interface RunState {
  run_id: string;
  goal: string;
  plan: string[];
  step_log: Step[];
  leads: Record<string, Lead>;
  notes: string[];
  status: RunStatus;
  final_answer: string;
  place: string;
  bbox: BBox | null;
  niches: string[];
  target_count: number;
  labels: Record<string, Label>;
}

export interface RunSummary {
  run_id: string;
  goal: string;
  status: RunStatus;
  n_leads: number;
  started_at: number;
}

export interface LabelsSummary {
  total: number;
  good: number;
  bad: number;
  ready: boolean;
  need: string;
}

export interface Rule {
  id: string;
  feature: string;
  op: string;
  value: boolean | number | string;
  weight: number;
  rationale: string;
  created_run: string;
  holdout_gain: number;
}

export interface RejectedCandidate {
  rule: Record<string, unknown>;
  reason: string;
}

export interface LearnReport {
  ok: boolean;
  message: string;
  n_labels: number;
  n_train: number;
  n_holdout: number;
  acc_before: number;
  acc_after: number;
  p_at_10_before: number | null;
  p_at_10_after: number | null;
  added: Rule[];
  removed: Rule[];
  rejected: RejectedCandidate[];
  final_rules: Rule[];
}

export interface HistoryRecord {
  run_id: string;
  n_labels: number;
  n_train: number;
  n_select: number;
  n_test: number;
  acc_before: number;
  acc_after: number;
  p_at_10_before: number | null;
  p_at_10_after: number | null;
  added: Rule[];
  removed: Rule[];
  rejected: RejectedCandidate[];
  note?: string;
  ts: number;
}

export interface MemoryResponse {
  rules: Rule[];
  history: HistoryRecord[];
}
