import {
  isApiError,
  type ApiError,
  type MeResponse,
  type MeProfileResponse,
  type HomeResponse,
  type InterviewListResponse,
  type DocumentPreviewResponse,
  type DocumentKind,
  type CreateAnalysisRunRequest,
  type CreateAnalysisRunResponse,
  type AnalysisRunResponse,
  type AnalysisResultResponse,
  type CreateInterviewRequest,
  type CreateInterviewResponse,
  type InterviewDetailResponse,
  type ReportResponse,
  type FeedbackDisagreementRequest,
} from '@/types/api';

// MSW 핸들러가 같은 prefix를 참조한다. 값이 바뀌면 mock도 함께 따라간다.
export const BASE = '/api';

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
  getProfile: () => request<MeProfileResponse>('/me/profile'),
  getHome: () => request<HomeResponse>('/me/home'),
  getInterviews: (params?: { page?: number; size?: number }) => {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.size) query.set('size', String(params.size));
    const qs = query.toString();
    return request<InterviewListResponse>(`/me/interviews${qs ? `?${qs}` : ''}`);
  },
  // Content-Type을 직접 지정하지 않는다. multipart boundary는 브라우저가 생성해야 한다.
  // kind: user_documents.kind 가 NOT NULL 이라 보낸다. 계약 반영은 BE 확인 대기 중.
  previewDocument: (kind: DocumentKind, file: File, postingUrl?: string) => {
    const form = new FormData();
    form.append('kind', kind);
    form.append('file', file);
    if (postingUrl) form.append('postingUrl', postingUrl);
    return request<DocumentPreviewResponse>('/documents/preview', {
      method: 'POST',
      body: form,
    });
  },
  createAnalysisRun: (body: CreateAnalysisRunRequest) =>
    requestJson<CreateAnalysisRunResponse>('/analysis-runs', 'POST', body),
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
  analysisRunEventsUrl: (runId: string) => `${BASE}/analysis-runs/${runId}/events`,
};
