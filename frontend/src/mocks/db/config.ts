import type { StepKey } from '@/types/api';

/**
 * mock 저장소의 공통 설정.
 *
 * 분석 run·면접 준비·리포트 생성은 시간이 지나면 상태가 변해야 하므로 정적 응답으로 둘 수 없다.
 * 호출 횟수가 아니라 createdAt 기준 경과 시간으로 상태를 계산한다.
 * SSE 스트림과 폴링 응답이 같은 값을 봐야 하기 때문이다.
 */

// 진행 속도 — 개발 중 기다리는 시간을 줄이려면 이 값만 조정한다.
export const STEP_DURATION_MS = 1200;
export const PREPARE_DURATION_MS = 3500;
export const REPORT_GENERATE_MS = 3000;
export const CANDIDATE_PAGE_MS = 2500;

/** 면접 제한 시간. 계약에 근거가 없어 임시값이다. spec/backend/features/interview.md 확정 필요. */
export const INTERVIEW_LIMIT_SECONDS = 900;

/** spec/backend/features/analysis-run.md — step key 7개 고정. */
export const STEP_KEYS: StepKey[] = [
  'doc_extract',
  'repo_select',
  'repo_detail',
  'jd_fetch',
  'jd_extract',
  'repo_analyze',
  'match_score',
];

/**
 * seed 레코드 식별자.
 * 분석부터 진행하지 않고도 후속 화면을 바로 열 수 있게 고정 id로 둔다.
 */
export const SEED_RUN_ID = '5c7b9e10-0000-4000-8000-00000000aaaa';
export const SEED_INTERVIEW_ID = 'a3d51c20-1001-4c00-9a00-000000000001';
export const SEED_SESSION_ID = 'sess_0000000000000001';

/** 분석 실패 화면(3-3)용. */
export const SEED_FAILED_RUN_ID = '5c7b9e10-0000-4000-8000-00000000bbbb';
/** 면접 준비 실패 화면(1b)용. lastError 가 채워져 있다. */
export const SEED_PREPARING_FAILED_INTERVIEW_ID = 'a3d51c20-1009-4c00-9a00-000000000009';
/** 면접 진행 화면(5b-v2)을 바로 여는 진행 중 면접. 새로고침해도 1턴부터 다시 시작한다. */
export const SEED_IN_PROGRESS_INTERVIEW_ID = 'a3d51c20-1005-4c00-9a00-000000000005';
/**
 * 진행 중 seed 면접 전용 run. SEED_RUN_ID를 쓰면 그 run에 진행 중 면접이 늘 있어
 * 새 면접 생성·다시 보기가 409 session_limit_exceeded로 막힌다.
 * 완료 run으로 seed해 "레포 다시 선택하기"(/interview/repos/:runId)가 410 run_expired로 막히지 않게 한다.
 */
export const SEED_IN_PROGRESS_RUN_ID = '5c7b9e10-0000-4000-8000-00000000cccc';
