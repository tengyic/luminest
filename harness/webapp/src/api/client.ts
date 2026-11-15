import type {
  AttemptResult,
  CapabilitiesResponse,
  CreateCourseResponse,
  CurriculumResponse,
  Lesson,
  Question,
  Session,
  User,
} from './types';

// In dev, Vite proxies /api -> backend. For a built deploy, set VITE_API_BASE to the
// backend origin, e.g. https://api.luminest.example . The base already includes /api/v1.
const RAW_BASE = import.meta.env.VITE_API_BASE || '/api';
export const API_BASE = RAW_BASE.replace(/\/$/, '') + '/v1';

export class ApiError extends Error {
  status: number;
  detail?: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

const TOKEN_KEY = 'lh_access_token';
const REFRESH_KEY = 'lh_refresh_token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}
export function setRefreshToken(token: string | null): void {
  if (token) localStorage.setItem(REFRESH_KEY, token);
  else localStorage.removeItem(REFRESH_KEY);
}

// Single in-flight refresh so concurrent 401s reuse one call.
let refreshPromise: Promise<string> | null = null;

async function doRefresh(): Promise<string> {
  const refresh = getRefreshToken();
  if (!refresh) throw new ApiError(401, 'No refresh token');
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!res.ok) {
    setToken(null);
    setRefreshToken(null);
    throw new ApiError(res.status, 'Session expired');
  }
  const data = (await res.json()) as Session;
  setToken(data.token);
  setRefreshToken(data.refresh_token);
  return data.token;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  allowRetry = true,
): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const run = () => fetch(`${API_BASE}${path}`, { ...options, headers });

  let res = await run();
  if (res.status === 401 && allowRetry && getRefreshToken()) {
    try {
      if (!refreshPromise) refreshPromise = doRefresh();
      const newToken = await refreshPromise;
      headers.set('Authorization', `Bearer ${newToken}`);
      res = await run();
    } catch {
      throw new ApiError(401, 'Unauthorized');
    } finally {
      refreshPromise = null;
    }
  }

  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = await res.json();
    } catch {
      /* non-JSON error body */
    }
    const raw = detail && typeof detail === 'object' ? (detail as any).detail : null;
    const message =
      typeof raw === 'string'
        ? raw
        : detail && typeof detail === 'object' && (detail as any).message
          ? (detail as any).message
          : res.statusText;
    throw new ApiError(res.status, message || `Request failed (${res.status})`, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  register: (body: {
    email: string;
    password: string;
    name: string;
    age_confirmed?: boolean;
    accept_terms?: boolean;
    invite_code?: string;
  }) =>
    apiFetch<Session>('/auth/register', { method: 'POST', body: JSON.stringify(body) }, false),

  login: (body: { email: string; password: string }) =>
    apiFetch<Session>('/auth/login', { method: 'POST', body: JSON.stringify(body) }, false),

  refresh: () => apiFetch<Session>('/auth/refresh', { method: 'POST', body: JSON.stringify({ refresh_token: getRefreshToken() }) }, false),

  me: () => apiFetch<User>('/me'),
  capabilities: () => apiFetch<CapabilitiesResponse>('/capabilities', {}, false),
  curriculum: () => apiFetch<CurriculumResponse>('/curriculum'),

  createCourse: (body: { text?: string; url?: string; title?: string; subject?: string; level?: string }) =>
    apiFetch<CreateCourseResponse>('/create/course', { method: 'POST', body: JSON.stringify(body) }),

  enrol: (courseId: string) =>
    apiFetch<{ enrolled: boolean; [k: string]: unknown }>(`/my-courses/${encodeURIComponent(courseId)}/enrol`, {
      method: 'POST',
    }),

  lesson: (conceptId: string) => apiFetch<Lesson>(`/lessons/${encodeURIComponent(conceptId)}`),

  questionsNext: (params: { mode?: string; concept_id?: string }) => {
    const q = new URLSearchParams();
    if (params.mode) q.set('mode', params.mode);
    if (params.concept_id) q.set('concept_id', params.concept_id);
    const qs = q.toString();
    return apiFetch<Question>(`/questions/next${qs ? `?${qs}` : ''}`);
  },

  submitAttempt: (body: {
    question_id: string;
    option_id?: string | null;
    answer_text?: string | null;
    receipt: string;
    client_event_id: string;
    elapsed_seconds: number;
    confidence?: number | null;
    self_explanation?: string | null;
  }) => apiFetch<AttemptResult>('/attempts', { method: 'POST', body: JSON.stringify(body) }),

  setTrainingConsent: (enabled: boolean) =>
    apiFetch<{ enabled: boolean }>('/training/consent', { method: 'POST', body: JSON.stringify({ enabled }) }),

  sendEvents: (events: unknown[]) =>
    apiFetch<{ stored?: number }>('/events', { method: 'POST', body: JSON.stringify({ events }) }),
};
