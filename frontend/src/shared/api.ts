import {
  isApiError,
  type ApiError,
  type MeResponse,
  type HomeResponse,
  type InterviewListResponse,
  type DocumentPreviewResponse,
  type DocumentKind,
  type DocumentSource,
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
  // 파일 또는 링크 중 하나를 보낸다(포트폴리오는 링크 허용).
  // Content-Type을 직접 지정하지 않는다. multipart boundary는 브라우저가 생성해야 한다.
  previewDocument: (kind: DocumentKind, input: DocumentSource, postingUrl?: string) => {
    const form = new FormData();
    form.append('kind', kind);
    if ('file' in input) form.append('file', input.file);
    else form.append('sourceUrl', input.sourceUrl);
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
};
