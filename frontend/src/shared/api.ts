import type {
  AnalysisResultResponse,
  AnalysisRunResponse,
  ApiError,
  CreateAnalysisRunResponse,
  CreateInterviewRequest,
  CreateInterviewResponse,
  FeedbackDisagreementRequest,
  HomeResponse,
  InterviewDetailResponse,
  InterviewListResponse,
  MeResponse,
  ReportResponse,
} from '@/types/api';
import { AUTH_LOCK_NAME, getAuthEpoch, publishAuthChange } from '@/shared/authEvents';

const BASE = '/api';
const REFRESHABLE_REASONS = new Set(['unauthenticated', 'access_token_expired']);
const BLOCKED_REASONS = new Set(['account_suspended', 'account_withdrawn']);

type RequestOptions = RequestInit & {
  anonymous?: boolean;
  canRefresh?: boolean;
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

function isErrorEnvelope(value: unknown): value is { error: ApiError['error'] } {
  if (!value || typeof value !== 'object' || !('error' in value)) return false;
  const error = (value as { error?: unknown }).error;
  return Boolean(
    error &&
    typeof error === 'object' &&
    typeof (error as { reason?: unknown }).reason === 'string' &&
    typeof (error as { message?: unknown }).message === 'string',
  );
}

async function responseError(response: Response) {
  try {
    const body: unknown = await response.json();
    if (isErrorEnvelope(body)) {
      return new ApiRequestError(response.status, {
        reason: body.error.reason,
        message: body.error.message,
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
  return (
    error instanceof ApiRequestError &&
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
  const { anonymous = false, canRefresh = true, ...fetchOptions } = options;
  try {
    return await rawRequest<T>(path, fetchOptions, requestEpoch);
  } catch (error) {
    if (
      canRefresh &&
      error instanceof ApiRequestError &&
      error.status === 401 &&
      REFRESHABLE_REASONS.has(error.error.reason)
    ) {
      try {
        assertAuthEpoch(requestEpoch);
        await refreshAccess(error, requestEpoch);
        assertAuthEpoch(requestEpoch);
        return await request<T>(
          path,
          { ...fetchOptions, anonymous, canRefresh: false },
          requestEpoch,
        );
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
  getHome: () => request<HomeResponse>('/me/home'),
  getInterviews: (params?: { page?: number; size?: number }) => {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.size) query.set('size', String(params.size));
    const qs = query.toString();
    return request<InterviewListResponse>(`/me/interviews${qs ? `?${qs}` : ''}`);
  },
  createAnalysisRun: (formData: FormData) =>
    request<CreateAnalysisRunResponse>('/analysis-runs', { method: 'POST', body: formData }),
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
