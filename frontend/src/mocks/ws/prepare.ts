import type { PrepareStepKey } from '@/types/api';
import {
  PREPARE_DURATION_MS,
  clearPrepareFailure,
  interviewLastError,
  type InterviewRecord,
} from '../db';
import { send, wait, type Client } from './protocol';
import { sendFirstQuestion } from './turns';

/** 면접 준비 단계. api-spec.md #18 */

/** 실행 순서. 첫 질문 생성이 마지막이다. spec/backend/features/interview.md */
export const PREPARE_STEPS: PrepareStepKey[] = [
  'analyze_repo',
  'build_persona',
  'set_criteria',
  'compose_question',
];

const STEP_MS = PREPARE_DURATION_MS / PREPARE_STEPS.length;

/**
 * 준비 단계를 흘려보낸다.
 *
 * 면접 레코드의 `createdAt` 기준으로 이미 지난 단계는 `completed`만 즉시 보낸다.
 * 화면을 늦게 열었다고 해서 처음부터 다시 기다리면 `GET /interviews/{id}`의
 * 상태와 어긋나기 때문이다. REST 목이 경과 시간으로 상태를 파생하는 것과 같은 규칙이다.
 */
export async function streamPrepare(client: Client, createdAt: number) {
  for (const [index, key] of PREPARE_STEPS.entries()) {
    const remaining = createdAt + STEP_MS * (index + 1) - Date.now();

    if (remaining <= 0) {
      // 이미 끝난 단계. 체크리스트를 채우기만 한다.
      send(client, { type: 'prepareStep', key, status: 'completed' });
      continue;
    }

    send(client, { type: 'prepareStep', key, status: 'running' });
    await wait(remaining);
    send(client, { type: 'prepareStep', key, status: 'completed' });
  }

  send(client, { type: 'prepareCompleted' });
}

/**
 * 준비 실패 상태로 붙은 연결에 체크리스트와 오류를 재생한다.
 *
 * 성공한 단계는 `completed`, 실패한 단계는 `failed`, 그 뒤는 `pending`으로 남긴다.
 * 화면(5a2-v2)이 체크리스트를 유지한 채 실패 단계만 ✕로 바꾸기 때문이다.
 */
export function replayPrepareFailure(client: Client, record: InterviewRecord) {
  const lastError = interviewLastError(record);
  const failedIndex = lastError?.step ? PREPARE_STEPS.indexOf(lastError.step) : -1;

  PREPARE_STEPS.forEach((key, index) => {
    if (failedIndex === -1 || index < failedIndex) {
      send(client, { type: 'prepareStep', key, status: 'completed' });
    } else if (index === failedIndex) {
      send(client, { type: 'prepareStep', key, status: 'failed' });
    } else {
      send(client, { type: 'prepareStep', key, status: 'pending' });
    }
  });

  if (lastError) send(client, { type: 'error', ...lastError });
}

/**
 * `prepareRetry`. 실패한 단계부터 다시 실행한다. 성공한 단계는 재실행하지 않는다.
 * 세션과 선택 레포는 그대로 유지된다.
 */
export async function handlePrepareRetry(client: Client, record: InterviewRecord) {
  const lastError = interviewLastError(record);
  if (!lastError) return;

  const failedIndex = lastError.step ? PREPARE_STEPS.indexOf(lastError.step) : 0;
  const doneCount = Math.max(0, failedIndex);

  // 이미 끝난 단계만큼 시계를 과거로 옮기면 streamPrepare 가 그 단계를 건너뛴다.
  clearPrepareFailure(record, Date.now() - doneCount * STEP_MS);

  await streamPrepare(client, record.createdAt);
  sendFirstQuestion(client, record);
}
