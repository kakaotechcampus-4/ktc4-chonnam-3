import { completedTurns } from '../fixtures/interview';
import { takeWsFault } from '../faults';
import type { InterviewRecord } from '../db';
import { parseClientMessage, send, wait, wsError, type Client } from './protocol';
import { handleAnswer, resendPendingQuestion } from './turns';

/**
 * 음성 답변 mock. 계약은 spec/shared/decisions/0007 (Proposed).
 *
 * 실제 STT 대신 그 턴의 fixture 답변을 전사 결과로 쓴다. 조각 수에 비례해 임시 전사를
 * 한 단어씩 늘려, 화면이 조각을 실제로 보내고 있는지 자막으로 확인할 수 있게 한다.
 * 오디오 없음 타임아웃(0007 제안 10초)은 서버 규칙이라 mock에 두지 않는다.
 */

/** 250ms 조각 4개(≈1초)마다 임시 전사에 한 단어를 더한다. */
const CHUNKS_PER_WORD = 4;
/** answerEnd 뒤 최종 전사까지의 연출 간격. */
const TRANSCRIBE_MS = 600;
export const REPEAT_REQUEST_TEXT = '다시 한 번 말씀해 주시겠어요?';
const FALLBACK_ANSWER = '네, 그 부분은 직접 설계하고 구현했습니다.';

type AnswerFault = 'stt' | 'repeat' | 'no-partial' | 'reject';

/** `/ws/interviews/{sessionId}/{kind}` 규칙만 받는다. 연결 단계 규칙은 끝이 달라 걸러진다. */
function takeAnswerFault(socketPath: string, kind: AnswerFault) {
  return takeWsFault(`${socketPath}/${kind}`, (rule) => rule.path.endsWith(`/${kind}`));
}

export function createAnswerHandler(client: Client, record: InterviewRecord, socketPath: string) {
  /** 받는 중인 답변. 연결마다 따로 둔다 — 끊기면 받던 오디오는 함께 버려진다(0007). */
  let pending: { turn: number; chunks: number } | null = null;
  const answerText = (turn: number) => completedTurns[turn - 1]?.answer ?? FALLBACK_ANSWER;

  async function finish(turn: number) {
    if (!pending || pending.turn !== turn) {
      send(client, wsError('answer_rejected', 'ERR_ANSWER_REJECTED', { recoverable: true }));
      return;
    }
    pending = null;
    await wait(TRANSCRIBE_MS);

    const stt = takeAnswerFault(socketPath, 'stt');
    if (stt) {
      send(client, {
        ...wsError(stt.reason ?? 'stt_failed', stt.code ?? 'ERR_STT_FAILED', { recoverable: true }),
        details: stt.details,
      });
      return;
    }

    // 다시 듣기 요청은 답변으로 저장하지 않고 같은 턴 질문을 다시 보낸다(0007).
    if (takeAnswerFault(socketPath, 'repeat')) {
      send(client, { type: 'transcript', turn, text: REPEAT_REQUEST_TEXT });
      resendPendingQuestion(client, record);
      return;
    }

    const text = answerText(turn);
    send(client, { type: 'transcript', turn, text });
    await handleAnswer(client, record, turn, text);
  }

  return (data: unknown) => {
    if (typeof data !== 'string') {
      if (!pending) return;
      pending.chunks += 1;
      if (pending.chunks % CHUNKS_PER_WORD !== 0) return;
      if (takeAnswerFault(socketPath, 'no-partial')) return;
      const words = answerText(pending.turn).split(' ');
      send(client, {
        type: 'transcriptPartial',
        turn: pending.turn,
        text: words.slice(0, pending.chunks / CHUNKS_PER_WORD).join(' '),
      });
      return;
    }

    const message = parseClientMessage(data);
    if (!message) {
      console.warn('[msw] 해석할 수 없는 WS 메시지', data);
      return;
    }
    if (message.type === 'answerStart') {
      // 같은 턴으로 다시 오면 받던 오디오를 버리고 새로 받는다(0007).
      const last = record.liveTurns?.at(-1);
      const rejected = takeAnswerFault(socketPath, 'reject');
      if (rejected || !last || last.turn !== message.turn || last.answer !== null) {
        send(client, wsError('answer_rejected', 'ERR_ANSWER_REJECTED', { recoverable: true }));
        return;
      }
      pending = { turn: message.turn, chunks: 0 };
      return;
    }
    void finish(message.turn);
  };
}
