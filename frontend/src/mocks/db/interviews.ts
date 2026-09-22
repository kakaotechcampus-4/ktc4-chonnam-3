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
  /**
   * WS가 진행시킨 턴. 질문을 보낼 때 추가하고 답변을 받을 때 채운다.
   *
   * 화면 상태를 WS 연결이 아니라 여기에 둔다. 계약상 재연결 절차가
   * `GET /interviews/{id}`로 `turns`를 다시 받는 것이라(api-spec #18),
   * 연결 클로저에 들고 있으면 새로고침 후 조회 응답과 어긋난다.
   */
  liveTurns?: InterviewTurn[];
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

/** WS 경로는 interviewId 가 아니라 sessionId 로 붙는다. api-spec.md #18 */
export function getInterviewBySessionId(sessionId: string) {
  for (const record of interviews.values()) {
    if (record.sessionId === sessionId) return record;
  }
  return undefined;
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
      // reason 은 화면 분기용 snake_case, code 는 배너에 노출하는 표시용 식별자다. api-spec.md #18
      reason: 'question_gen_timeout',
      code: 'ERR_QUESTION_GEN_TIMEOUT',
      step: 'compose_question',
      recoverable: true,
      occurredAt: new Date(now).toISOString(),
    }
  );
}

/**
 * 준비 중에는 턴이 없다. 준비가 끝나면 WS가 진행시킨 턴을 보여주고,
 * 아직 WS가 붙지 않았으면 첫 질문 1개만 보인다.
 */
export function interviewTurns(record: InterviewRecord, now = Date.now()): InterviewTurn[] {
  const status = interviewStatus(record, now);
  if (status === 'completed') return record.liveTurns ?? completedTurns;
  if (status === 'in_progress') return record.liveTurns ?? [firstTurn];
  return [];
}

export function interviewCurrentTurn(record: InterviewRecord, now = Date.now()) {
  const turns = interviewTurns(record, now);
  if (turns.length > 0) return turns[turns.length - 1].turn;
  return interviewStatus(record, now) === 'completed' ? TOTAL_TURNS : 0;
}

/**
 * WS가 새 질문을 보낼 때 호출한다. 턴 번호를 매기고 레코드에 남긴다.
 * 답변은 아직 없으므로 `null`이다.
 */
export function appendQuestion(record: InterviewRecord, turn: InterviewTurn) {
  record.liveTurns = [...(record.liveTurns ?? []), turn];
  return record.liveTurns;
}

/**
 * 답변 수신. 클라이언트가 지정한 턴의 `answer`를 채운다.
 *
 * 계약이 `answer`에 `turn`을 싣게 바뀌어(api-spec.md #18) "마지막 턴" 추정을 버렸다.
 * 추정에 기대면 재연결이 늦을 때 지난 턴 답변이 다음 질문에 붙는다.
 *
 * 없는 턴이거나 이미 답변된 턴이면 `null`이다. 호출자가 저장 실패로 처리해야 한다.
 */
export function recordAnswer(record: InterviewRecord, turn: number, text: string) {
  const turns = record.liveTurns;
  if (!turns) return null;

  const index = turns.findIndex((item) => item.turn === turn);
  if (index === -1) return null;
  if (turns[index].answer !== null) return null;

  const answered = { ...turns[index], answer: text };
  record.liveTurns = [...turns.slice(0, index), answered, ...turns.slice(index + 1)];
  return answered;
}

/**
 * 준비 실패를 풀고 다시 준비 상태로 되돌린다. WS `prepareRetry` 에서 부른다.
 * `createdAt` 을 옮겨 이미 성공한 단계는 다시 실행되지 않게 한다. api-spec.md #18
 */
export function clearPrepareFailure(record: InterviewRecord, createdAt: number) {
  record.fixedStatus = undefined;
  record.fixedLastError = undefined;
  record.createdAt = createdAt;
  return record;
}

/** 마지막 턴까지 답변이 끝났으면 면접을 종료 상태로 고정한다. */
export function finishInterview(record: InterviewRecord) {
  record.fixedStatus = 'completed';
  return record;
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
      reason: 'question_gen_timeout',
      code: 'ERR_QUESTION_GEN_TIMEOUT',
      step: 'compose_question',
      recoverable: true,
      occurredAt: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    },
  });
}

seedInterviews();
