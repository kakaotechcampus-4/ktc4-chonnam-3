import type { AnalysisStep, DocumentPreviewResponse, RunStatus, StepKey, StepStatus } from '@/types/api';
import {
  CANDIDATE_PAGE_MS,
  SEED_FAILED_RUN_ID,
  SEED_RUN_ID,
  STEP_DURATION_MS,
  STEP_KEYS,
} from './config';

/** 분석 run·문서·후보 page의 in-memory 상태. 새로고침하면 초기화된다. */

export type RunRecord = {
  runId: string;
  postingUrl: string;
  documentId: string | null;
  createdAt: number;
  /** seed 레코드처럼 시간과 무관하게 고정할 상태. failed run은 이 값으로만 만든다. */
  fixedStatus?: RunStatus;
  /** fixedStatus가 failed일 때 내려줄 reason. backend/docs/error-reasons.md 의 값만 쓴다. */
  fixedFailureReason?: string;
  /** fixedStatus가 failed일 때 어느 step에서 멈췄는지. */
  failedAtStep?: StepKey;
};

const runs = new Map<string, RunRecord>();
const documents = new Map<string, DocumentPreviewResponse>();
/** `${runId}:${page}` 키의 최초 요청 시각. */
const candidatePageRequests = new Map<string, number>();

// 분석 run ---------------------------------------------------------------

function fingerprint(postingUrl: string, documentId: string | null) {
  return `${postingUrl.trim().replace(/\/+$/, '')}::${documentId ?? ''}`;
}

/**
 * POST /analysis-runs 중복 요청 감지.
 * 같은 fingerprint의 run이 아직 running이면 기존 run을 reused로 돌려준다.
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

/**
 * 실제로 실행되는 step. documentId 없이 만든 run은 doc_extract를 돌리지 않는다.
 * 자기소개서·포트폴리오는 선택 입력이라 미첨부가 정상 경로다. failed가 아니라 skipped다.
 */
function executedStepKeys(run: RunRecord): StepKey[] {
  if (run.documentId) return STEP_KEYS;
  return STEP_KEYS.filter((key) => key !== 'doc_extract');
}

export function runStatus(run: RunRecord, now = Date.now()): RunStatus {
  if (run.fixedStatus) return run.fixedStatus;
  return elapsedSteps(run, now) >= executedStepKeys(run).length ? 'completed' : 'running';
}

/**
 * steps는 항상 StepKey 7개를 모두 담는다. 실행하지 않은 단계도 키를 생략하지 않고 skipped로 준다.
 * 완료 상태는 계약 enum인 completed다. succeeded는 문서·레포 분석 결과에만 쓰는 값이다.
 */
export function runSteps(run: RunRecord, now = Date.now()): AnalysisStep[] {
  const executed = executedStepKeys(run);
  // 실패 run은 멈춘 지점까지만 완료로 보여야 한다. 경과 시간으로 계산하면 계속 진행해 버린다.
  const failedIndex =
    runStatus(run, now) === 'failed' ? executed.indexOf(run.failedAtStep ?? 'repo_analyze') : -1;
  const done = failedIndex >= 0 ? failedIndex : elapsedSteps(run, now);

  return STEP_KEYS.map((key) => {
    const index = executed.indexOf(key);
    if (index === -1) return { key, status: 'skipped' as StepStatus };

    let status: StepStatus = 'pending';
    if (index < done) status = 'completed';
    else if (index === done) status = failedIndex >= 0 ? 'failed' : 'running';
    return { key, status };
  });
}

/** skipped는 분모·분자에서 모두 제외한다. frontend/docs/api-spec.md #14. */
export function runProgress(run: RunRecord, now = Date.now()) {
  const countable = runSteps(run, now).filter((step) => step.status !== 'skipped');
  if (countable.length === 0) return 100;
  const done = countable.filter((step) => step.status === 'completed').length;
  return Math.round((done / countable.length) * 100);
}

/** AnalysisRunResponse.estimatedSeconds는 required다. 진행 중이 아니면 null. */
export function runEstimatedSeconds(run: RunRecord, now = Date.now()): number | null {
  if (runStatus(run, now) !== 'running') return null;
  const remaining = executedStepKeys(run).length - elapsedSteps(run, now);
  return Math.max(0, Math.ceil((remaining * STEP_DURATION_MS) / 1000));
}

/** AnalysisRunResponse.failureReason 은 required다. 실패가 아니면 null. */
export function runFailureReason(run: RunRecord, now = Date.now()): string | null {
  if (runStatus(run, now) !== 'failed') return null;
  return run.fixedFailureReason ?? 'internal_error';
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

// seed -------------------------------------------------------------------

/** 완료된 run 1건과 실패한 run 1건. 분석을 처음부터 돌리지 않고 후속 화면을 열기 위함이다. */
function seedRuns() {
  runs.set(SEED_RUN_ID, {
    runId: SEED_RUN_ID,
    postingUrl: 'https://www.wanted.co.kr/wd/000000',
    documentId: null,
    // 이미 모든 step이 끝난 상태로 보이게 한다.
    createdAt: Date.now() - STEP_KEYS.length * STEP_DURATION_MS - 1000,
  });

  runs.set(SEED_FAILED_RUN_ID, {
    runId: SEED_FAILED_RUN_ID,
    postingUrl: 'https://www.wanted.co.kr/wd/999999',
    documentId: null,
    createdAt: Date.now() - STEP_KEYS.length * STEP_DURATION_MS - 1000,
    fixedStatus: 'failed',
    fixedFailureReason: 'jd_fetch_failed',
    failedAtStep: 'jd_fetch',
  });
}

seedRuns();
