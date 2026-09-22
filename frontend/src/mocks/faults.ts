import type { PrepareStepKey } from '@/types/api';
import { BASE } from '@/shared/api';

/**
 * 장애 주입(fault injection).
 *
 * 실패 케이스는 정상 흐름과 달리 "언제든 임의의 요청에" 일어나야 검증할 수 있다.
 * 핸들러마다 분기를 심으면 정상 경로가 지저분해지고 조합도 못 만든다.
 * 그래서 규칙을 바깥에 두고 모든 핸들러가 요청 직전에 한 번 조회한다.
 *
 * 규칙은 localStorage에 있으므로 devtools에서 바로 고칠 수 있고 새로고침해도 남는다.
 * 켜 둔 채로 잊는 사고를 막으려고 워커 시작 시 활성 규칙을 콘솔에 알린다.
 */

const STORAGE_KEY = 'msw.faults';

/** `http`는 계약 에러 응답, `network`는 fetch 자체 실패, `timeout`은 응답 없이 지연. */
export type FaultKind = 'http' | 'network' | 'timeout';

export type FaultRule = {
  /** BASE 이후 경로. `*`는 나머지 전부를 의미한다. 예: `/me/home`, `/analysis-runs/*`, `*` */
  path: string;
  /** 생략하면 모든 메서드. */
  method?: string;
  /** 생략하면 `http`. */
  kind?: FaultKind;
  /** `http`일 때 필수. */
  status?: number;
  /** `backend/docs/error-reasons.md`에 있는 값만 쓴다. */
  reason?: string;
  message?: string;
  retryAfter?: number;
  details?: Record<string, unknown>;
  /** WebSocket 오류 전용. 배너에 노출하는 표시용 식별자. api-spec.md #18 */
  code?: string;
  /** WebSocket 오류 전용. `false`면 서버가 세션을 닫는다. 생략하면 `true`. */
  recoverable?: boolean;
  /**
   * WebSocket 준비 단계 오류 전용. 어느 단계에서 실패했는지.
   *
   * 주입 규칙이 오류의 유일한 입력 통로다. 이 값이 없으면 `error.step`이 항상 `null`이 되고,
   * 화면은 체크리스트의 어느 칸을 ✕로 칠지 알 수 없다(api-spec.md #18 UI states).
   * 진행 중 오류에는 넣지 않는다. 계약상 `step`은 준비 단계 오류일 때만 값이 있다.
   */
  step?: PrepareStepKey;
  /** `timeout`일 때 지연 시간. 생략하면 30초. */
  delayMs?: number;
  /** 남은 적용 횟수. 생략하면 해제할 때까지 계속 적용된다. */
  times?: number;
};

function read(): FaultRule[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as FaultRule[]) : [];
  } catch {
    // 시크릿 창이나 손으로 깨뜨린 JSON. 장애 주입 때문에 앱이 죽으면 안 된다.
    return [];
  }
}

function write(rules: FaultRule[]) {
  try {
    if (rules.length === 0) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, JSON.stringify(rules));
  } catch {
    /* 저장 못 해도 이번 요청에는 이미 적용된 뒤다. */
  }
}

/** `*`는 `/`를 포함한 나머지 전부와 맞춘다. 그 밖의 문자는 문자 그대로 비교한다. */
function matchesPath(pattern: string, pathname: string) {
  const escaped = pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*');
  return new RegExp(`^${escaped}$`).test(pathname);
}

/**
 * 이 경로에 적용할 규칙을 찾아 소비한다.
 * `times`가 있으면 1 줄이고, 0이 되면 규칙을 지운다.
 * 규칙이 없으면 `null`을 돌려주고 호출자는 평소대로 동작한다.
 *
 * WebSocket 연결도 같은 저장소를 쓴다. 연결에는 `Request`가 없어 경로로 받는다.
 */
export function takeFaultFor(pathname: string, method = 'GET'): FaultRule | null {
  const rules = read();
  if (rules.length === 0) return null;

  const suffix = pathname.startsWith(BASE) ? pathname.slice(BASE.length) : pathname;

  const index = rules.findIndex((rule) => {
    if (rule.method && rule.method.toUpperCase() !== method.toUpperCase()) return false;
    return matchesPath(rule.path, suffix);
  });
  if (index === -1) return null;

  const rule = rules[index];
  if (typeof rule.times === 'number') {
    const left = rule.times - 1;
    if (left <= 0) rules.splice(index, 1);
    else rules[index] = { ...rule, times: left };
    write(rules);
  }
  return rule;
}

export function takeFault(request: Request): FaultRule | null {
  return takeFaultFor(new URL(request.url).pathname, request.method);
}

export function listFaults(): FaultRule[] {
  return read();
}

export function addFault(rule: FaultRule) {
  const rules = read();
  rules.push(rule);
  write(rules);
  return rules;
}

export function clearFaults() {
  write([]);
}
