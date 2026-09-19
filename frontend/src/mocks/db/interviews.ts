import type { InterviewLastError, InterviewStatus, InterviewTurn } from '@/types/api';
import { candidatePages } from '../fixtures/analysis';
import { TOTAL_TURNS, completedTurns, firstTurn } from '../fixtures/interview';
import { jdCompanyName, jdPosition } from '../fixtures/jd';
import {
  INTERVIEW_LIMIT_SECONDS,
  PREPARE_DURATION_MS,
  REPORT_GENERATE_MS,
  SEED_INTERVIEW_ID,
  SEED_PREPARING_FAILED_INTERVIEW_ID,
  SEED_RUN_ID,
  SEED_SESSION_ID,
} from './config';

/** 면접·리포트의 in-memory 상태. 새로고침하면 초기화된다. */

export type InterviewRecord = {
  interviewId: string;
  sessionId: string;
  runId: string;
  repositoryIds: string[];
  createdAt: number;
  /** 공고에서 온 값. InterviewDetailResponse 의 required 필드라 레코드가 함께 들고 있는다. */
  position: string;
  companyName: string | null;
  /** seed 레코드처럼 시간과 무관하게 고정할 상태. */
  fixedStatus?: InterviewStatus;
  /** status 가 preparing_failed 일 때만 값이 있다. */
  fixedLastError?: InterviewLastError;
  /** 리포트 lazy generation 시작 시각. 최초 조회 때 기록한다. */
  reportRequestedAt?: number;
};

const interviews = new Map<string, InterviewRecord>();

/** repositoryIds -> 레포 이름. 계약의 repositoryNames 는 후보 카드에서 파생시킨다. */
const repositoryNameById = new Map(
  Object.values(candidatePages)
    .flat()
    .map((card) => [card.id, card.name] as const),
);

export function interviewRepositoryNames(record: InterviewRecord): string[] {
  return record.repositoryIds.map((id) => repositoryNameById.get(id) ?? id);
}

export function hasActiveInterviewForRun(runId: string, now = Date.now()) {
  for (const record of interviews.values()) {
    if (record.runId !== runId) continue;
    const status = interviewStatus(record, now);
    if (status === 'preparing' || status === 'in_progress') return true;
  }
  return false;
}

export function createInterview(runId: string, repositoryIds: string[]) {
  const record: InterviewRecord = {
    interviewId: crypto.randomUUID(),
    sessionId: `sess_${crypto.randomUUID().replace(/-/g, '').slice(0, 16)}`,
    runId,
    repositoryIds,
    createdAt: Date.now(),
    position: jdPosition,
    companyName: jdCompanyName,
  };
  interviews.set(record.interviewId, record);
  return record;
}

export function getInterview(id: string) {
  return interviews.get(id);
}

export function interviewStatus(record: InterviewRecord, now = Date.now()): InterviewStatus {
  if (record.fixedStatus) return record.fixedStatus;
  return now - record.createdAt < PREPARE_DURATION_MS ? 'preparing' : 'in_progress';
}

/** lastError 는 preparing_failed 일 때만 값이 있다. 그 외에는 null 이다. */
export function interviewLastError(
  record: InterviewRecord,
  now = Date.now(),
): InterviewLastError | null {
  if (interviewStatus(record, now) !== 'preparing_failed') return null;
  return (
    record.fixedLastError ?? {
      reason: '면접 준비에 실패했어요.',
      code: 'internal_error',
      step: null,
      recoverable: true,
      occurredAt: new Date(now).toISOString(),
    }
  );
}

/**
 * 준비 중에는 턴이 없고, 준비가 끝나면 첫 질문 1개가 보인다.
 * 2턴 이후 진행은 WebSocket이 담당하므로 다음 작업 범위다.
 */
export function interviewTurns(record: InterviewRecord, now = Date.now()): InterviewTurn[] {
  const status = interviewStatus(record, now);
  if (status === 'completed') return completedTurns;
  if (status === 'in_progress') return [firstTurn];
  return [];
}

export function interviewCurrentTurn(record: InterviewRecord, now = Date.now()) {
  const status = interviewStatus(record, now);
  if (status === 'completed') return TOTAL_TURNS;
  if (status === 'in_progress') return 1;
  return 0;
}

export function interviewRemainingSeconds(record: InterviewRecord, now = Date.now()) {
  const status = interviewStatus(record, now);
  if (status !== 'in_progress') return status === 'completed' ? 0 : INTERVIEW_LIMIT_SECONDS;
  const startedAt = record.createdAt + PREPARE_DURATION_MS;
  return Math.max(0, INTERVIEW_LIMIT_SECONDS - Math.floor((now - startedAt) / 1000));
}

/**
 * 리포트는 lazy generation이다. spec/backend/features/report.md.
 * 최초 조회에서 생성을 시작하고, 생성이 끝나기 전까지 202 generating을 반환한다.
 */
export function reportReady(record: InterviewRecord, now = Date.now()) {
  if (record.reportRequestedAt === undefined) {
    record.reportRequestedAt = now;
    return false;
  }
  return now - record.reportRequestedAt >= REPORT_GENERATE_MS;
}

// seed -------------------------------------------------------------------

const SEED_REPOSITORY_IDS = [
  '9f1c0a6e-0001-4f00-8a01-000000000001',
  '9f1c0a6e-0002-4f00-8a01-000000000002',
];

/** 종료된 면접 1건과 준비 실패 면접 1건. 리포트·준비실패 화면을 바로 열기 위함이다. */
function seedInterviews() {
  interviews.set(SEED_INTERVIEW_ID, {
    interviewId: SEED_INTERVIEW_ID,
    sessionId: SEED_SESSION_ID,
    runId: SEED_RUN_ID,
    repositoryIds: SEED_REPOSITORY_IDS,
    createdAt: Date.now() - 60 * 60 * 1000,
    position: jdPosition,
    companyName: jdCompanyName,
    fixedStatus: 'completed',
  });

  interviews.set(SEED_PREPARING_FAILED_INTERVIEW_ID, {
    interviewId: SEED_PREPARING_FAILED_INTERVIEW_ID,
    sessionId: 'sess_0000000000000009',
    runId: SEED_RUN_ID,
    repositoryIds: SEED_REPOSITORY_IDS,
    createdAt: Date.now() - 10 * 60 * 1000,
    position: jdPosition,
    companyName: jdCompanyName,
    fixedStatus: 'preparing_failed',
    fixedLastError: {
      reason: '질문을 만드는 중 문제가 생겼어요. 다시 시도해주세요.',
      code: 'llm_failed',
      step: 'compose_question',
      recoverable: true,
      occurredAt: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    },
  });
}

seedInterviews();
