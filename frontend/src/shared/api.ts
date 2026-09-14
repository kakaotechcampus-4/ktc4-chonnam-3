import {
  isApiError,
  type ApiError,
  type MeResponse,
  type HomeResponse,
  type InterviewListResponse,
  type CreateAnalysisRunResponse,
  type AnalysisRunResponse,
  type AnalysisResultResponse,
  type CreateInterviewRequest,
  type CreateInterviewResponse,
  type InterviewDetailResponse,
  type ReportResponse,
  type FeedbackDisagreementRequest,
} from '@/types/api';

const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    credentials: 'include',
  });

  if (!res.ok) {
    const text = await res.text();
    let parsed: unknown;
    try {
      parsed = text ? JSON.parse(text) : undefined;
    } catch {
      parsed = undefined;
    }

    const error: ApiError = isApiError(parsed)
      ? { ...parsed, status: res.status }
      : {
          status: res.status,
          error: {
            reason: 'unknown_error',
            message: text || res.statusText || `HTTP ${res.status}`,
          },
        };

    throw error;
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

function requestJson<T>(path: string, method: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export const api = {
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  getMe: () => request<MeResponse>('/me'),
  getHome: () => request<HomeResponse>('/me/home'),
  getInterviews: (params?: { page?: number; size?: number }) => {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.size) query.set('size', String(params.size));
    const qs = query.toString();
    return request<InterviewListResponse>(`/me/interviews${qs ? `?${qs}` : ''}`);
  },
  createAnalysisRun: (formData: FormData) =>
    request<CreateAnalysisRunResponse>('/analysis-runs', {
      method: 'POST',
      body: formData,
    }),
  getAnalysisRun: (runId: string) => request<AnalysisRunResponse>(`/analysis-runs/${runId}`),
  getAnalysisRunResult: (runId: string) =>
    request<AnalysisResultResponse>(`/analysis-runs/${runId}/result`),
  createInterview: (body: CreateInterviewRequest) =>
    requestJson<CreateInterviewResponse>('/interviews', 'POST', body),
  getInterview: (id: string) => request<InterviewDetailResponse>(`/interviews/${id}`),
  getInterviewReport: (id: string) => request<ReportResponse>(`/interviews/${id}/report`),
  retryInterview: (id: string) =>
    request<CreateInterviewResponse>(`/interviews/${id}/retry`, { method: 'POST' }),
  submitFeedbackDisagreement: (id: string, body: FeedbackDisagreementRequest) =>
    requestJson<void>(`/reports/${id}/feedback-disagreements`, 'POST', body),
};
