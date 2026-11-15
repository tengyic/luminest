// Types mirror the harness/backend FastAPI contract (app/schemas.py, app/main.py,
// app/receipts.py). Keep these in sync with the backend — they are the wire shapes.

export interface User {
  id: string;
  name: string;
  email: string;
  goal?: string | null;
  daily_minutes?: number | null;
  telemetry_consent?: boolean | null;
  training_consent?: boolean | null;
  course_id?: string | null;
  onboarding_complete?: boolean;
  email_verified?: boolean;
  role?: string;
  status?: string;
  cohort_id?: string | null;
}

export interface Session {
  token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export type CapabilityState = 'enabled' | 'withheld' | 'alpha_free' | string;

export interface Capability {
  id: string;
  tier: string;
  state: CapabilityState;
  reason?: string;
  [key: string]: unknown;
}

export interface CapabilitiesResponse {
  capabilities: Capability[];
  [key: string]: unknown;
}

export interface Concept {
  id: string;
  title: string;
  unit?: string;
  strand?: string;
  topic?: string;
  tier?: string;
  mastery?: number;
  recall?: number;
  due_at?: string | null;
  prerequisites?: string[];
  [key: string]: unknown;
}

export interface CurriculumResponse {
  concepts: Concept[];
  sources?: unknown[];
  graph_stats?: unknown;
}

export interface LessonMedia {
  kind?: string;
  type?: string;
  url?: string;
  embed?: string;
  caption?: string;
  status?: string;
  provider?: string;
  [key: string]: unknown;
}

export interface LessonBlock {
  kind?: string;
  type?: string;
  text?: string;
  html?: string;
  caption?: string;
  media?: LessonMedia;
  [key: string]: unknown;
}

export interface Lesson {
  id: string;
  title: string;
  unit?: string;
  strand?: string;
  topic?: string;
  tier?: string;
  difficulty?: number;
  blocks?: LessonBlock[];
  simulation?: unknown;
  project?: unknown;
  media?: LessonMedia[];
  hint?: string;
  prerequisites?: string[];
  summary?: string;
  generated?: boolean;
  course_id?: string;
}

export interface QuestionOption {
  id: string;
  text: string;
  [key: string]: unknown;
}

export interface Question {
  id: string;
  concept_id?: string;
  concept_title?: string;
  prompt: string;
  options: QuestionOption[];
  kind?: string;
  expected_seconds?: number;
  mode?: string;
  issued_at?: string;
  receipt: string;
  progress?: unknown;
  selection_reason?: string;
}

export interface AttemptResult {
  correct: boolean;
  [key: string]: unknown;
}

export interface CreateCourseResponse {
  course: { id: string; title?: string; [key: string]: unknown };
  enrolled: boolean;
  concepts?: number;
  questions?: number;
  next?: string;
  rights_note?: string;
  [key: string]: unknown;
}
