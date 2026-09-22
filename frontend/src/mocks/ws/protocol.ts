import type { PrepareStepKey, WsClientMessage, WsServerMessage } from '@/types/api';

/**
 * 면접 WS 목의 공통 조각. `frontend/docs/api-spec.md` #18.
 * 메시지 송수신 형태만 다루고 면접 진행 규칙은 prepare.ts·turns.ts 에 둔다.
 */

/** msw의 클라이언트 연결 객체. `send`만 쓰므로 최소 형태로 좁힌다. */
export type Client = { send: (data: string) => void };

/** 답변 길이 상한. 초과하면 `answer_too_long`. */
export const ANSWER_MAX_LENGTH = 2000;

/** 종료 직전 여유. 오류 메시지가 클라이언트에 닿을 시간을 준다. */
export const CLOSE_GRACE_MS = 50;

export const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function send(client: Client, message: WsServerMessage) {
  client.send(JSON.stringify(message));
}

export function wsError(
  reason: string,
  code: string,
  options: { recoverable: boolean; step?: PrepareStepKey | null },
): WsServerMessage {
  return {
    type: 'error',
    reason,
    code,
    step: options.step ?? null,
    recoverable: options.recoverable,
    occurredAt: new Date().toISOString(),
  };
}

/** 클라이언트 메시지를 계약 타입으로 좁힌다. 모르는 모양이면 무시한다. */
export function parseClientMessage(data: unknown): WsClientMessage | null {
  if (typeof data !== 'string') return null;
  try {
    const parsed: unknown = JSON.parse(data);
    if (typeof parsed !== 'object' || parsed === null) return null;
    const { type, turn, text } = parsed as { type?: unknown; turn?: unknown; text?: unknown };
    if (type !== 'answer') return null;
    if (typeof turn !== 'number' || typeof text !== 'string') return null;
    return { type: 'answer', turn, text };
  } catch {
    return null;
  }
}
