import { ws } from 'msw';

import { getInterviewBySessionId, interviewStatus } from '../db';
import { takeFaultFor } from '../faults';
import { path } from '../http';
import { handlePrepareRetry, replayPrepareFailure, streamPrepare } from './prepare';
import { CLOSE_GRACE_MS, parseClientMessage, send, wait, wsError } from './protocol';
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
      if (message.type === 'answer') void handleAnswer(client, record, message.text);
      if (message.type === 'prepareRetry') void handlePrepareRetry(client, record);
    });

    if (status === 'preparing_failed') {
      replayPrepareFailure(client, record);
      return;
    }

    /**
     * 장애 주입 규칙이 이 연결을 겨냥하면 오류만 보내고 끝낸다.
     * REST와 같은 저장소를 쓰므로 `msw.fault({ path: '/ws/interviews/*', ... })` 로 건다.
     * `recoverable: false` 면 계약대로 서버가 세션을 닫는다.
     */
    const fault = takeFaultFor(new URL(client.url).pathname);
    if (fault?.reason) {
      const recoverable = fault.recoverable !== false;
      send(client, wsError(fault.reason, fault.code ?? 'ERR_UNKNOWN', { recoverable }));
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
