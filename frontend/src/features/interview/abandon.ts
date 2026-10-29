import { api } from '@/shared/api';
import { queryClient } from '@/shared/queryClient';
import { queryKeys } from '@/shared/queryKeys';
import { isApiError, type InterviewStatus } from '@/types/api';

/**
 * 면접을 abandoned로 바꾼다 (spec/shared/decisions/0009-interview-abandon-transition.md).
 *
 * 반환값은 호출 뒤 그 면접의 상태다.
 * - 204: `abandoned`
 * - 404 `not_found`: 정리할 면접이 없다. `null`
 * - 409 `already_completed`: `preparing`(다른 탭의 다시 시도)에도 오므로 GET으로 다시 확인한 상태
 * 그 밖의 실패는 그대로 던진다.
 */
export async function abandonInterview(id: string): Promise<InterviewStatus | null> {
  try {
    await api.abandonInterview(id);
    // 뒤로 가기로 돌아왔을 때 캐시된 이전 상태(준비 실패 등)로 그리지 않게 한다.
    void queryClient.invalidateQueries({ queryKey: queryKeys.interview(id) });
    void queryClient.invalidateQueries({ queryKey: queryKeys.interviewsAll });
    return 'abandoned';
  } catch (error) {
    if (!isApiError(error)) throw error;
    if (error.error.reason === 'not_found') return null;
    if (error.error.reason !== 'already_completed') throw error;
    return (await api.getInterview(id)).status;
  }
}

/** `GET /interviews/{id}`의 status별 도달 화면 (spec/frontend/features/interview.md). */
export function interviewPath(id: string, status: InterviewStatus) {
  if (status === 'completed') return `/interview/${id}/report`;
  if (status === 'in_progress') return `/interview/${id}/session`;
  if (status === 'abandoned') return '/home';
  return `/interview/${id}/prepare`;
}

/** [레포 다시 선택하기]가 레포 선택 화면에 넘기는 기존 면접. [면접 시작]에서 먼저 abandon한다. */
export type ReselectState = { previousInterviewId: string };

export function previousInterviewIdFrom(state: unknown): string | null {
  const value = (state as Partial<ReselectState> | null)?.previousInterviewId;
  return typeof value === 'string' ? value : null;
}
