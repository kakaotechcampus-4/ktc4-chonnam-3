import { ws } from 'msw';

import { getInterviewBySessionId, interviewStatus, setPrepareFailure } from '../db';
import { takeWsFault } from '../faults';
import { path } from '../http';
import { sendPrepareFailure, streamPrepare } from './prepare';
import { CLOSE_GRACE_MS, parseClientMessage, send, wait, wsLastError } from './protocol';
import { handleAnswer, resendPendingQuestion, sendFirstQuestion } from './turns';

/**
 * 면접 WebSocket mock. `frontend/docs/api-spec.md` #18.
 *
 * msw 2.15의 `ws.link()`를 쓴다. 서비스 워커가 아니라 페이지의 WebSocket 클래스를 가로채므로
 * REST 목과 같은 핸들러 배열에 얹히고, 별도 서버를 띄울 필요가 없다.
 * 방식 비교와 한계는 spec/frontend/designs/2026-09-21-ws-mock.md 참고.
 */

/** 경로는 REST와 같은 prefix를 따른다. 규약 확정 필요는 설계 문서 D9. */
export const interviewSocket = ws.link(path('/ws/interviews/:sessionId'));

/**
 * 이 세션에 열려 있는 연결. 준비 재시도가 REST 로 들어오므로(0010 결정)
 * REST 핸들러가 진행 상황을 흘려보낼 상대를 찾아야 한다.
 * 열린 연결이 없으면 빈 배열이고, 다음 연결이 경과 시간 기준으로 이어받는다.
 */
export function clientsForSession(sessionId: string) {
  return [...interviewSocket.clients].filter(
    (client) => new URL(client.url).pathname.endsWith(`/${sessionId}`),
  );
}

/**
 * 연결 수립.
 *
 * 핸드셰이크 실패(401·409)는 HTTP 상태코드로 표현되는데 WebSocket 목은 그 단계에 끼어들 수 없다.
 * 대신 정책 위반 코드(1008)로 닫고 사유를 남긴다. 설계 문서의 한계 항목 참고.
 */
export const interviewWsHandlers = [
  interviewSocket.addEventListener('connection', async ({ client, params }) => {
    const sessionId = String(params.sessionId);
    const record = getInterviewBySessionId(sessionId);

    if (!record) {
      console.warn(`[msw] 없는 세션의 WS 연결: ${sessionId}`);
      client.close(1008, 'not_found');
      return;
    }

    const status = interviewStatus(record);

    if (status === 'completed' || status === 'abandoned') {
      // 계약상 409. 이미 끝난 세션에는 붙을 수 없다.
      client.close(1008, 'already_ended');
      return;
    }

    /**
     * 클라이언트 메시지 수신을 준비 단계보다 먼저 등록한다.
     * 준비가 끝나기를 기다리는 동안 들어온 메시지를 놓치지 않기 위해서다.
     */
    client.addEventListener('message', (event) => {
      const message = parseClientMessage(event.data);
      if (!message) {
        console.warn('[msw] 해석할 수 없는 WS 메시지', event.data);
        return;
      }
      void handleAnswer(client, record, message.turn, message.text);
    });

    /**
     * 준비 실패 세션에는 오류를 다시 보내지 않는다.
     *
     * 계약의 복구 경로는 `GET /interviews/{id}`의 `lastError` 스냅샷이고(#18),
     * 화면은 그 스냅샷으로 실패를 그린 뒤 "다시 시도"를 눌러야 WS를 연다.
     * 연결 시점에 오류를 되보내면 화면이 방금 지운 오류가 되살아나 재시도가 끝나도
     * 실패 배너가 남는다. 실제로 재현했다(설계 문서 D14).
     * 재시도는 `POST /interviews/{id}/prepare/retry` REST 로 들어온다(0010 결정).
     */
    if (status === 'preparing_failed') return;

    /**
     * 장애 주입. REST와 같은 저장소를 쓰지만 경로를 `/ws/` 로 명시한 규칙만 받는다.
     * `msw.fault({ path: '/ws/interviews/*', ... })` 로 건다.
     *
     * `kind` 가 `network`·`timeout` 이면 연결 자체가 실패한 상황이라 메시지를 보내지 않는다.
     * 화면의 재연결 경로(onclose → GET → 재연결)를 검증할 수 있게 하기 위함이다.
     */
    const fault = takeWsFault(new URL(client.url).pathname);

    if (fault?.kind === 'network') {
      client.close();
      return;
    }
    if (fault?.kind === 'timeout') {
      // 연결은 열려 있는데 아무 말도 하지 않는 서버. 화면의 대기 상태를 본다.
      return;
    }

    if (fault?.reason) {
      const recoverable = fault.recoverable !== false;
      const lastError = wsLastError(fault.reason, fault.code ?? 'ERR_UNKNOWN', {
        recoverable,
        step: fault.step,
      });

      if (fault.step) {
        // 준비 단계 오류면 체크리스트부터 맞춰 준다. 그래야 화면이 실패 칸을 ✕로 바꾼다.
        sendPrepareFailure(client, fault.step);
        // 새로고침 후에도 배너가 유지되도록 레코드에 남긴다.
        setPrepareFailure(record, lastError);
      }

      send(client, { type: 'error', ...lastError });
      if (!recoverable) {
        // 같은 틱에 닫으면 클라이언트가 error 를 받기 전에 연결이 끊긴다.
        await wait(CLOSE_GRACE_MS);
        client.close(1008, fault.reason);
      }
      return;
    }

    /**
     * 재연결. 계약상 FE는 `GET /interviews/{id}`로 turns를 다시 받고 붙는다(#18).
     * 목은 준비 단계를 되풀이하지 않고, 아직 답변하지 않은 질문만 다시 보낸다.
     */
    if ((record.liveTurns?.length ?? 0) > 0) {
      send(client, { type: 'prepareCompleted' });
      resendPendingQuestion(client, record);
      return;
    }

    await streamPrepare(client, record.createdAt);
    sendFirstQuestion(client, record);
  }),
];
