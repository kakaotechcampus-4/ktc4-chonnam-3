import type {
  AnalysisResultResponse,
  AnalysisRunResponse,
  ApiError,
  CreateAnalysisRunRequest,
  CreateAnalysisRunResponse,
  CandidatesResponse,
  CandidatesAnalyzingResponse,
  DocumentPreviewResponse,
  CreateInterviewRequest,
  CreateInterviewResponse,
  FeedbackDisagreementRequest,
  HomeResponse,
  InterviewDetailResponse,
  InterviewListResponse,
  MeResponse,
  MeProfileResponse,
  ReportResponse,
  ReportGeneratingResponse,
} from '@/types/api';
import { isApiError } from '@/types/api';
import { AUTH_LOCK_NAME, getAuthEpoch, publishAuthChange } from '@/shared/authEvents';

// MSW 핸들러도 같은 API prefix를 사용한다.
export const BASE = '/api';
const REFRESHABLE_REASONS = new Set(['unauthenticated', 'access_token_expired']);
const BLOCKED_REASONS = new Set(['account_suspended', 'account_withdrawn']);
const GITHUB_AUTH_REASONS = new Set(['token_invalid', 'github_token_invalid']);

type RequestOptions = RequestInit & {
  anonymous?: boolean;
};

export class ApiRequestError extends Error implements ApiError {
  status: number;
  error: ApiError['error'];

  constructor(status: number, error: ApiError['error']) {
    super(error.message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.error = error;
  }
}

export class NetworkRequestError extends Error {
  readonly status = 0;
  readonly error = {
    reason: 'network_error',
    message: '네트워크 연결을 확인해주세요.',
    details: {},
  };

  constructor() {
    super('네트워크 연결을 확인해주세요.');
    this.name = 'NetworkRequestError';
  }
}

class StaleAuthRequestError extends Error {
  constructor() {
    super('Authentication changed while the request was pending.');
    this.name = 'StaleAuthRequestError';
  }
}

function assertAuthEpoch(epoch: number) {
  // 인증 상태가 바뀌기 전에 시작한 요청의 응답이 이전 세션의 캐시를 복원하지 못하게 한다.
  if (epoch !== getAuthEpoch()) throw new StaleAuthRequestError();
}

async function responseError(response: Response) {
  try {
    const body: unknown = await response.json();
    if (isApiError(body)) {
      return new ApiRequestError(response.status, {
        reason: body.error.reason,
        message: body.error.message,
        ...(typeof body.error.retryAfter === 'number' ? { retryAfter: body.error.retryAfter } : {}),
        details:
          body.error.details && typeof body.error.details === 'object' ? body.error.details : {},
      });
    }
  } catch {
    // 서버 응답 본문이 JSON이 아니어도 HTTP 상태 코드를 오류 판단 기준으로 유지한다.
  }
  return new ApiRequestError(response.status, {
    reason: 'http_error',
    message: '서버 응답에 문제가 있습니다.',
    details: {},
  });
}

async function rawRequest<T>(path: string, options: RequestInit = {}, epoch?: number): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...options, credentials: 'include' });
  } catch {
    throw new NetworkRequestError();
  }

  if (!response.ok) {
    const error = await responseError(response);
    if (epoch !== undefined) assertAuthEpoch(epoch);
    throw error;
  }
  if (epoch !== undefined) assertAuthEpoch(epoch);
  if (response.status === 204) return undefined as T;

  let body: T;
  try {
    body = (await response.json()) as T;
  } catch {
    throw new ApiRequestError(response.status, {
      reason: 'invalid_response',
      message: '서버 응답에 문제가 있습니다.',
      details: {},
    });
  }
  if (epoch !== undefined) assertAuthEpoch(epoch);
  return body;
}

function isTerminalAuthError(error: unknown) {
  // GitHub API용 토큰의 폐기는 DEVON 로그인 세션의 폐기와 다르다.
  return (
    error instanceof ApiRequestError &&
    !GITHUB_AUTH_REASONS.has(error.error.reason) &&
    (error.status === 401 || BLOCKED_REASONS.has(error.error.reason))
  );
}

function invalidate(error: ApiRequestError, anonymous: boolean) {
  if (!anonymous && isTerminalAuthError(error)) {
    publishAuthChange({ reason: error.error.reason, redirect: true });
  }
}

// 같은 탭에서는 하나의 갱신 요청을 공유하고, Web Lock으로 탭 간 쿠키 회전을 순차 처리한다.
let refreshPromise: Promise<void> | undefined;

function refreshAccess(originalError: ApiRequestError, epoch: number) {
  // 탭 간 잠금을 사용할 수 없으면 갱신 토큰의 동시 재사용을 막기 위해 다시 로그인하도록 한다.
  if (!navigator.locks) return Promise.reject(originalError);
  if (refreshPromise) return refreshPromise;

  refreshPromise = navigator.locks
    .request(AUTH_LOCK_NAME, async () => {
      assertAuthEpoch(epoch);
      try {
        // 대기 중 다른 탭이 갱신했을 수 있으므로, 갱신이 재귀 호출되지 않는 직접 요청으로 확인한다.
        await rawRequest<MeResponse>('/me', {}, epoch);
        return;
      } catch (error) {
        if (
          !(error instanceof ApiRequestError) ||
          error.status !== 401 ||
          !REFRESHABLE_REASONS.has(error.error.reason)
        ) {
          throw error;
        }
      }
      assertAuthEpoch(epoch);
      await rawRequest<void>('/auth/refresh', { method: 'POST' }, epoch);
    })
    .finally(() => {
      refreshPromise = undefined;
    });

  return refreshPromise;
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
  requestEpoch = getAuthEpoch(),
): Promise<T> {
  const { anonymous = false, ...fetchOptions } = options;
  try {
    return await rawRequest<T>(path, fetchOptions, requestEpoch);
  } catch (error) {
    if (
      error instanceof ApiRequestError &&
      error.status === 401 &&
      REFRESHABLE_REASONS.has(error.error.reason)
    ) {
      try {
        assertAuthEpoch(requestEpoch);
        await refreshAccess(error, requestEpoch);
        assertAuthEpoch(requestEpoch);
        // 재시도는 직접 요청으로 끝내 갱신 재진입과 인증 종료 이벤트의 중복 발행을 막는다.
        return await rawRequest<T>(path, fetchOptions, requestEpoch);
      } catch (refreshError) {
        if (refreshError instanceof ApiRequestError) invalidate(refreshError, anonymous);
        throw refreshError;
      }
    }
    if (error instanceof ApiRequestError) invalidate(error, anonymous);
    throw error;
  }
}

function requestJson<T>(path: string, method: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

async function logout() {
  publishAuthChange({ reason: 'logout_pending', redirect: false });
  const performLogout = async () => {
    await rawRequest<void>('/auth/logout', { method: 'POST' });
    publishAuthChange({ reason: 'unauthenticated', redirect: true });
  };
  // 로그아웃도 갱신과 같은 잠금을 사용해 다른 탭의 쿠키 회전과 경합하지 않게 한다.
  if (navigator.locks) return navigator.locks.request(AUTH_LOCK_NAME, performLogout);
  return performLogout();
}

export function isAuthFailure(error: unknown) {
  return isTerminalAuthError(error);
}

export function errorMessage(error: unknown) {
  if (error instanceof ApiRequestError || error instanceof NetworkRequestError) {
    return error.error.message;
  }
  return '요청을 완료하지 못했습니다.';
}

export const api = {
  logout,
  getMe: (options?: { anonymous?: boolean; signal?: AbortSignal }) =>
    request<MeResponse>('/me', options),
  getProfile: () => request<MeProfileResponse>('/me/profile'),
  getHome: () => request<HomeResponse>('/me/home'),
  getInterviews: (params?: { page?: number; size?: number }) => {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.size) query.set('size', String(params.size));
    const qs = query.toString();
    return request<InterviewListResponse>(`/me/interviews${qs ? `?${qs}` : ''}`);
  },
  // multipart boundary는 브라우저가 생성하므로 Content-Type을 직접 지정하지 않는다.
  previewDocument: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<DocumentPreviewResponse>('/documents/preview', { method: 'POST', body: form });
  },
  createAnalysisRun: (body: CreateAnalysisRunRequest) =>
    requestJson<CreateAnalysisRunResponse>('/analysis-runs', 'POST', body),
  getAnalysisRun: (runId: string) => request<AnalysisRunResponse>(`/analysis-runs/${runId}`),
  getAnalysisRunResult: (runId: string) =>
    request<AnalysisResultResponse>(`/analysis-runs/${runId}/result`),
  // 200은 카드 목록, 202는 분석 중 응답이며 호출부가 status로 구분한다.
  getAnalysisRunCandidates: (runId: string, page: number) =>
    request<CandidatesResponse | CandidatesAnalyzingResponse>(
      `/analysis-runs/${runId}/candidates?page=${page}`,
    ),
  createInterview: (body: CreateInterviewRequest) =>
    requestJson<CreateInterviewResponse>('/interviews', 'POST', body),
  getInterview: (id: string) => request<InterviewDetailResponse>(`/interviews/${id}`),
  getInterviewReport: (id: string) =>
    request<ReportResponse | ReportGeneratingResponse>(`/interviews/${id}/report`),
  retryInterview: (id: string) =>
    request<CreateInterviewResponse>(`/interviews/${id}/retry`, { method: 'POST' }),
  submitFeedbackDisagreement: (id: string, body: FeedbackDisagreementRequest) =>
    requestJson<void>(`/interviews/${id}/feedback-disagreements`, 'POST', body),
  analysisRunEventsUrl: (runId: string) => `${BASE}/analysis-runs/${runId}/events`,
};
