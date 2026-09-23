import type { InterviewTurn } from '@/types/api';
import {
  appendQuestion,
  finishInterview,
  interviewRepositoryNames,
  recordAnswer,
  type InterviewRecord,
} from '../db';
import { TOTAL_TURNS, completedTurns, firstTurn } from '../fixtures/interview';
import { ANSWER_MAX_LENGTH, send, wait, wsError, type Client } from './protocol';

/** 면접 진행 턴. api-spec.md #18 */

/** 답변 수신부터 다음 질문까지의 연출 간격. */
const THINKING_MS = 900;
const EVIDENCE_MS = 700;

/** `evidenceCheck` 배너에 띄울 파일. 실제 근거 탐색을 흉내 내기만 한다. */
const EVIDENCE_FILES = ['CacheConfig.java', 'PaymentRetryService.java', 'README.md'];

/**
 * 해당 턴의 질문을 낸다. 문구는 종료된 면접 fixture를 재사용한다.
 * 계약이 요구하는 것은 턴 번호와 persona의 정합성이지 문구가 아니다.
 */
function questionForTurn(turn: number): InterviewTurn | null {
  const source = completedTurns[turn - 1];
  if (!source) return null;
  return { turn, persona: source.persona, question: source.question, answer: null };
}

/** 질문을 보내고 레코드에도 남긴다. 둘이 어긋나면 재연결 후 화면이 틀어진다. */
export function askQuestion(client: Client, record: InterviewRecord, turn: InterviewTurn) {
  appendQuestion(record, turn);
  send(client, { type: 'question', persona: turn.persona, text: turn.question, turn: turn.turn });
}

/** 준비가 끝난 직후 보내는 첫 질문. 1턴은 `hr_manager` 고정이다. */
export function sendFirstQuestion(client: Client, record: InterviewRecord) {
  askQuestion(client, record, { ...firstTurn, answer: null });
}

/** 재연결 시 아직 답변하지 않은 질문만 다시 보낸다. 레코드에는 이미 있으므로 추가하지 않는다. */
export function resendPendingQuestion(client: Client, record: InterviewRecord) {
  const last = record.liveTurns?.[record.liveTurns.length - 1];
  if (!last || last.answer !== null) return;
  send(client, { type: 'question', persona: last.persona, text: last.question, turn: last.turn });
}

/**
 * 답변 1건을 처리한다.
 *
 * 계약 순서를 지킨다: `answerReceived`(저장 완료) → `thinking` → `evidenceCheck` → 다음 `question`.
 *
 * `answerReceived`는 "수신·저장 완료" 신호다. 저장이 안 됐는데 보내면 화면은 제출 중
 * 상태만 풀고 다음 `question`을 영영 기다린다. 그렇다고 아무것도 안 보내면 입력창이
 * 잠긴 채로 남는다. 둘 다 막히므로 저장 실패는 `answer_rejected`로 알린다(api-spec.md #18).
 */
export async function handleAnswer(
  client: Client,
  record: InterviewRecord,
  turn: number,
  text: string,
) {
  if (text.length > ANSWER_MAX_LENGTH) {
    // 같은 턴 재제출. 답변은 저장하지 않는다.
    send(client, wsError('answer_too_long', 'ERR_ANSWER_TOO_LONG', { recoverable: true }));
    return;
  }

  const answered = recordAnswer(record, turn, text);
  if (!answered) {
    // 없는 턴이거나 이미 답변된 턴. 같은 턴 재제출로 유도한다.
    send(client, wsError('answer_rejected', 'ERR_ANSWER_REJECTED', { recoverable: true }));
    return;
  }

  send(client, { type: 'answerReceived' });

  const nextTurn = questionForTurn(answered.turn + 1);
  if (!nextTurn || answered.turn >= TOTAL_TURNS) {
    finishInterview(record);
    send(client, { type: 'interviewEnd' });
    return;
  }

  send(client, { type: 'thinking' });
  await wait(THINKING_MS);

  // 근거 기반 질문일 때만 탐색 배너를 띄운다.
  if (nextTurn.persona === 'tech_lead') {
    const repository = interviewRepositoryNames(record)[0] ?? 'project-a';
    const file = EVIDENCE_FILES[nextTurn.turn % EVIDENCE_FILES.length];
    send(client, { type: 'evidenceCheck', repository, file });
    await wait(EVIDENCE_MS);
  }

  askQuestion(client, record, nextTurn);
}
