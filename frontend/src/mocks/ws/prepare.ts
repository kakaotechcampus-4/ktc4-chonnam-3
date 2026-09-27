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
 * 준비 단계 실패를 체크리스트로 알린다.
 *
 * 실패한 단계 앞은 `completed`, 그 단계는 `failed`, 뒤는 `pending`.
 * 화면(5a2-v2)이 체크리스트를 유지한 채 실패 칸만 ✕로 바꾸기 때문에
 * 이 메시지 없이 `error`만 보내면 실패한 칸이 pending 인 채로 배너만 뜬다.
 */
export function sendPrepareFailure(client: Client, failedStep: PrepareStepKey) {
  const failedIndex = PREPARE_STEPS.indexOf(failedStep);

  PREPARE_STEPS.forEach((key, index) => {
    if (index < failedIndex) send(client, { type: 'prepareStep', key, status: 'completed' });
    else if (index === failedIndex) send(client, { type: 'prepareStep', key, status: 'failed' });
    else send(client, { type: 'prepareStep', key, status: 'pending' });
  });
}

/**
 * 준비 재시도. 실패한 단계부터 다시 실행하도록 시계를 되돌린다.
 * 성공한 단계는 재실행하지 않고 세션·선택 레포는 유지한다.
 *
 * 0010 결정으로 트리거가 WS 메시지에서 `POST /interviews/{id}/prepare/retry` 로 바뀌었다.
 * 그래서 이 함수는 연결을 모르고 레코드만 되돌린다. 진행 상황 전송은 호출자가 한다.
 * 재시도할 수 없는 상태면 `null`.
 */
export function retryPrepare(record: InterviewRecord) {
  const lastError = interviewLastError(record);
  if (!lastError) return null;

  const failedIndex = lastError.step ? PREPARE_STEPS.indexOf(lastError.step) : 0;
  const doneCount = Math.max(0, failedIndex);

  // 이미 끝난 단계만큼 시계를 과거로 옮기면 streamPrepare 가 그 단계를 건너뛴다.
  clearPrepareFailure(record, Date.now() - doneCount * STEP_MS);
  return lastError;
}

/** 재시도 진행 상황을 열려 있는 연결로 흘려보낸다. */
export async function streamPrepareFrom(client: Client, record: InterviewRecord) {
  await streamPrepare(client, record.createdAt);
  sendFirstQuestion(client, record);
}
