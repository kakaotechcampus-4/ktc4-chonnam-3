import type {
  ContractInterviewStatus,
  ContractStep,
  ContractStepKey,
  ContractStepStatus,
  ContractTurn,
  DocumentPreviewResponse,
  RunStatus,
} from '@/types/contract';
import { TOTAL_TURNS, completedTurns, firstTurn } from './fixtures/interview';

/**
 * mock 전용 in-memory 저장소.
 *
 * 분석 run·면접 준비·리포트 생성은 시간이 지나면 상태가 변해야 하므로 정적 응답으로 둘 수 없다.
 * 호출 횟수가 아니라 createdAt 기준 경과 시간으로 상태를 계산한다.
 * SSE 스트림과 폴링 응답이 같은 값을 봐야 하기 때문이다.
 *
 * 새로고침하면 초기화된다. seed 레코드는 화면 단독 개발용으로 항상 존재한다.
 */

// 진행 속도 — 개발 중 기다리는 시간을 줄이려면 이 값만 조정한다.
export const STEP_DURATION_MS = 1200;
export const PREPARE_DURATION_MS = 3500;
export const REPORT_GENERATE_MS = 3000;
export const CANDIDATE_PAGE_MS = 2500;
export const INTERVIEW_LIMIT_SECONDS = 900;

/** spec/backend/features/analysis-run.md — step key 7개 고정. */
export const STEP_KEYS: ContractStepKey[] = [
  'doc_extract',
  'repo_select',
  'repo_detail',
  'jd_fetch',
  'jd_extract',
  'repo_analyze',
  'match_score',
];

export const SEED_RUN_ID = '5c7b9e10-0000-4000-8000-00000000aaaa';
export const SEED_INTERVIEW_ID = 'a3d51c20-1001-4c00-9a00-000000000001';
export const SEED_SESSION_ID = 'sess_0000000000000001';

type RunRecord = {
  runId: string;
  postingUrl: string;
  documentId: string | null;
  createdAt: number;
};

type InterviewRecord = {
  interviewId: string;
  sessionId: string;
  runId: string;
  repositoryIds: string[];
  createdAt: number;
  /** seed 레코드처럼 시간과 무관하게 고정할 상태. */
  fixedStatus?: ContractInterviewStatus;
  /** 리포트 lazy generation 시작 시각. 최초 조회 때 기록한다. */
  reportRequestedAt?: number;
};

const runs = new Map<string, RunRecord>();
const interviews = new Map<string, InterviewRecord>();
const documents = new Map<string, DocumentPreviewResponse>();
/** `${runId}:${page}` 키의 최초 요청 시각. */
const candidatePageRequests = new Map<string, number>();

// 분석 run ---------------------------------------------------------------

function fingerprint(postingUrl: string, documentId: string | null) {
  return `${postingUrl.trim().replace(/\/+$/, '')}::${documentId ?? ''}`;
}

/**
 * POST /analysis-runs 중복 요청 재사용.
 * 같은 fingerprint의 run이 아직 running이면 기존 runId를 돌려준다.
 */
export function createRun(postingUrl: string, documentId: string | null) {
  const target = fingerprint(postingUrl, documentId);
  for (const run of runs.values()) {
    if (fingerprint(run.postingUrl, run.documentId) === target && runStatus(run) === 'running') {
      return { run, reused: true };
    }
  }

  const run: RunRecord = {
    runId: crypto.randomUUID(),
    postingUrl,
    documentId,
    createdAt: Date.now(),
  };
  runs.set(run.runId, run);
  return { run, reused: false };
}

export function getRun(runId: string) {
  return runs.get(runId);
}

/** 경과 시간 기준으로 완료된 step 수. */
function elapsedSteps(run: RunRecord, now = Date.now()) {
  return Math.floor((now - run.createdAt) / STEP_DURATION_MS);
}

export function runStatus(run: RunRecord, now = Date.now()): RunStatus {
  return elapsedSteps(run, now) >= STEP_KEYS.length ? 'completed' : 'running';
}

export function runSteps(run: RunRecord, now = Date.now()): ContractStep[] {
  const done = elapsedSteps(run, now);
  return STEP_KEYS.map((key, index) => {
    let status: ContractStepStatus = 'pending';
    if (index < done) status = 'succeeded';
    else if (index === done) status = 'running';
    return { key, status };
  });
}

export function runProgress(run: RunRecord, now = Date.now()) {
  const done = Math.min(elapsedSteps(run, now), STEP_KEYS.length);
  return Math.round((done / STEP_KEYS.length) * 100);
}

// 후보 page --------------------------------------------------------------

/**
 * 미분석 page는 202 analyzing을 주고, 일정 시간이 지나면 200으로 바뀐다.
 * spec/backend/features/analysis-run.md의 ARQ page 분석 job을 흉내 낸다.
 */
export function candidatePageReady(runId: string, page: number, now = Date.now()) {
  const key = `${runId}:${page}`;
  const requestedAt = candidatePageRequests.get(key);
  if (requestedAt === undefined) {
    candidatePageRequests.set(key, now);
    return false;
  }
  return now - requestedAt >= CANDIDATE_PAGE_MS;
}

// 문서 preview -----------------------------------------------------------

export function saveDocument(preview: DocumentPreviewResponse) {
  documents.set(preview.documentId, preview);
  return preview;
}

// 면접 -------------------------------------------------------------------

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
  };
  interviews.set(record.interviewId, record);
  return record;
}

export function getInterview(id: string) {
  return interviews.get(id);
}

export function interviewStatus(
  record: InterviewRecord,
  now = Date.now(),
): ContractInterviewStatus {
  if (record.fixedStatus) return record.fixedStatus;
  return now - record.createdAt < PREPARE_DURATION_MS ? 'preparing' : 'in_progress';
}

/**
 * 준비 중에는 턴이 없고, 준비가 끝나면 첫 질문 1개가 보인다.
 * 2턴 이후 진행은 WebSocket이 담당하므로 다음 작업 범위다.
 */
export function interviewTurns(record: InterviewRecord, now = Date.now()): ContractTurn[] {
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

/**
 * 분석부터 진행하지 않고도 면접 상세·리포트 화면을 열 수 있도록
 * 종료된 면접 1건과 완료된 run 1건을 미리 넣어 둔다.
 */
function seed() {
  runs.set(SEED_RUN_ID, {
    runId: SEED_RUN_ID,
    postingUrl: 'https://www.wanted.co.kr/wd/000000',
    documentId: null,
    // 이미 모든 step이 끝난 상태로 보이게 한다.
    createdAt: Date.now() - STEP_KEYS.length * STEP_DURATION_MS - 1000,
  });

  interviews.set(SEED_INTERVIEW_ID, {
    interviewId: SEED_INTERVIEW_ID,
    sessionId: SEED_SESSION_ID,
    runId: SEED_RUN_ID,
    repositoryIds: ['9f1c0a6e-0001-4f00-8a01-000000000001', '9f1c0a6e-0002-4f00-8a01-000000000002'],
    createdAt: Date.now() - 60 * 60 * 1000,
    fixedStatus: 'completed',
  });
}

seed();
