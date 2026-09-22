import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';
import type { WsClientMessage, WsServerMessage } from '@/types/api';

/**
 * 재연결 간격. 명세는 "실패해도 계속 재시도"만 정하고 간격은 정하지 않는다.
 * ponytail: 고정 2초. 서버가 오래 죽어 있는 상황이 문제가 되면 지수 백오프로 올린다.
 */
const RECONNECT_DELAY_MS = 2000;

export type WsStatus = 'connecting' | 'open' | 'reconnecting';

type Options = {
  interviewId: string;
  sessionId: string | undefined;
  /** false면 연결하지 않는다. 화면별 status 조건을 여기로 넘긴다. */
  enabled: boolean;
  onMessage: (message: WsServerMessage) => void;
};

/**
 * 5a2-v2 준비 화면과 5b-v2 진행 화면이 공유하는 WS 연결.
 * 두 화면은 같은 연결을 쓰지만 메시지 처리는 각자 하므로 여기서는 연결만 책임진다.
 */
export function useInterviewSocket({ interviewId, sessionId, enabled, onMessage }: Options) {
  const queryClient = useQueryClient();

  const [wsStatus, setWsStatus] = useState<WsStatus>('connecting');
  /** 연결이 끊긴 횟수. 보낸 메시지가 전달되지 못했을 가능성을 화면이 판단하는 데 쓴다. */
  const [dropCount, setDropCount] = useState(0);
  /** 값이 바뀌면 새 연결을 연다. 재연결과 send의 큐 비우기가 함께 올린다. */
  const [attempt, setAttempt] = useState(0);

  const socketRef = useRef<WebSocket | null>(null);
  /** 연결이 열리는 즉시 보낼 메시지. 끊긴 상태에서 send를 호출하면 여기 담긴다. */
  const pendingSendRef = useRef<WsClientMessage | null>(null);
  /** recoverable: false면 서버가 세션을 닫는다. 그때는 재연결하지 않는다. */
  const sessionClosedRef = useRef(false);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /**
   * 예약된 재연결의 일련번호. send가 번호를 올리면
   * 이미 떠 있는 GET 응답이 돌아와도 attempt를 올리지 못한다.
   */
  const reconnectSeqRef = useRef(0);

  // 핸들러가 매 렌더 새로 만들어져도 연결이 끊기지 않게 ref로 받는다.
  const onMessageRef = useRef(onMessage);
  useEffect(() => {
    onMessageRef.current = onMessage;
  });

  /**
   * 닫힘 표시는 그 세션에만 해당한다. 레포 재선택 등으로 sessionId가 바뀌면 새 세션이므로
   * 풀어준다. 그러지 않으면 이 훅이 살아 있는 한 새 세션에도 연결하지 못한다.
   * 아래 연결 effect보다 먼저 선언해야 같은 커밋에서 이 리셋이 먼저 돈다.
   */
  useEffect(() => {
    sessionClosedRef.current = false;
  }, [sessionId]);

  useEffect(() => {
    if (!enabled || !sessionId) return;
    // 서버가 닫은 세션이나 명시적 이탈 이후에는 다시 열지 않는다.
    if (sessionClosedRef.current) return;

    let disposed = false;
    const socket = new WebSocket(api.interviewSocketUrl(sessionId));
    socketRef.current = socket;

    socket.onopen = () => {
      setWsStatus('open');
      const pending = pendingSendRef.current;
      if (!pending) return;
      pendingSendRef.current = null;
      socket.send(JSON.stringify(pending));
    };

    socket.onmessage = (event) => {
      let message: WsServerMessage;
      try {
        message = JSON.parse(event.data as string) as WsServerMessage;
      } catch {
        // 깨진 프레임 하나 때문에 이후 메시지 처리까지 죽지 않게 한다.
        return;
      }
      if (message.type === 'error' && !message.recoverable) sessionClosedRef.current = true;
      onMessageRef.current(message);
    };

    socket.onclose = () => {
      // close 이벤트는 비동기라 새 소켓이 이미 socketRef에 들어온 뒤 도착할 수 있다.
      // 자기 소켓일 때만 비운다. 아니면 살아 있는 연결의 참조를 지워, 재시도·제출이
      // OPEN 분기 대신 재연결 경로를 타면서 멀쩡한 소켓을 한 번 더 끊는다.
      if (socketRef.current === socket) socketRef.current = null;
      if (disposed || sessionClosedRef.current) return;

      setDropCount((count) => count + 1);

      setWsStatus('reconnecting');
      // 큐는 비우지 않는다. 사용자가 누른 재시도·제출은 재연결 후 보내야 한다.
      /**
       * 재연결 전에 GET /interviews/{id}를 먼저 호출한다. 이 요청이 401 인터셉터를 타면서
       * 토큰이 갱신되고 복구용 turns도 함께 확보된다. 순서를 바꾸면 만료 토큰으로
       * 핸드셰이크를 시도해 401이 반복된다. 재연결 실패는 세션 상태를 바꾸지 않는다.
       */
      const seq = ++reconnectSeqRef.current;
      reconnectTimerRef.current = setTimeout(() => {
        void queryClient
          .refetchQueries({ queryKey: queryKeys.interview(interviewId) })
          .finally(() => {
            if (reconnectSeqRef.current !== seq) return;
            setAttempt((count) => count + 1);
          });
      }, RECONNECT_DELAY_MS);
    };

    return () => {
      disposed = true;
      // 화면을 떠나거나 새 연결로 넘어갈 때 예약된 재연결을 남기지 않는다.
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
      socket.close();
    };
  }, [enabled, sessionId, attempt, interviewId, queryClient]);

  /**
   * 보냈으면 true. 연결이 없을 때 큐에 담을지는 호출자가 정한다.
   *
   * queue: true는 멱등한 메시지(prepareRetry)에만 쓴다. answer는 turn을 싣지만 서버가
   * 불일치를 거절한다는 보장이 아직 없어(migration.md의 `answer`의 `turn` 행, 불일치
   * reason 미정) 큐에 담지 않고 실패로 돌려준다. 재연결이 늦으면 지난 턴 답변이 다음
   * 질문에 붙을 수 있기 때문이다. 잠금이 턴 기준이라 다시 누르면 된다.
   */
  const send = useCallback((message: WsClientMessage, options?: { queue?: boolean }) => {
    if (sessionClosedRef.current) return false;

    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(message));
      return true;
    }

    if (!options?.queue) return false;

    // 예약된 재연결과 이미 떠 있는 GET을 무효화한다. attempt가 두 번 오르면
    // 새로 연 소켓이 곧바로 닫히면서 이 메시지가 유실된다.
    reconnectSeqRef.current += 1;
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    reconnectTimerRef.current = null;
    pendingSendRef.current = message;
    setAttempt((count) => count + 1);
    return false;
  }, []);

  /** 명시적 이탈. 서버가 닫은 것과 같게 취급해 재연결하지 않는다. */
  const close = useCallback(() => {
    sessionClosedRef.current = true;
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    reconnectTimerRef.current = null;
    socketRef.current?.close();
  }, []);

  return { wsStatus, dropCount, send, close };
}
