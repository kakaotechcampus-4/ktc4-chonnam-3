import { addFault, clearFaults, listFaults, type FaultRule } from './faults';

/**
 * 이름 붙인 실패 시나리오.
 *
 * 규칙 JSON을 손으로 쓰면 오타가 나고, 무엇보다 `reason` 값을 지어내게 된다.
 * 여기 있는 값은 전부 `backend/docs/error-reasons.md` 레지스트리와
 * `frontend/docs/api-spec.md`의 엔드포인트별 실패 표에서 가져왔다.
 *
 * 화면이 실패를 어떻게 보여줘야 하는지는 계약 문서에 있다. 이 파일은 그 상황을 만들기만 한다.
 */

export type ScenarioName =
  | 'auth-expired'
  | 'refresh-failed'
  | 'github-token-invalid'
  | 'run-expired'
  | 'report-unavailable'
  | 'session-limit'
  | 'server-error'
  | 'ws-question-failed'
  | 'ws-repo-unreachable'
  | 'offline'
  | 'slow';

type Scenario = {
  /** devtools 목록에 뜨는 설명. */
  describe: string;
  rules: FaultRule[];
};

export const scenarios: Record<ScenarioName, Scenario> = {
  'auth-expired': {
    describe: '모든 요청이 401. 로그인 화면으로 밀려나는지 본다.',
    rules: [{ path: '*', status: 401, reason: 'unauthenticated', message: '로그인이 필요합니다.' }],
  },

  /**
   * 인터셉터가 401을 받고 갱신을 시도했을 때 그 갱신마저 실패하는 상황.
   * 조회 요청은 그대로 두어야 "401 → refresh → 재시도" 경로만 검증된다.
   */
  'refresh-failed': {
    describe: '/auth/refresh 만 401. 토큰 갱신 실패 후 처리를 본다.',
    rules: [
      {
        path: '/auth/refresh',
        method: 'POST',
        status: 401,
        reason: 'unauthenticated',
        message: '세션이 만료되었습니다.',
      },
    ],
  },

  'github-token-invalid': {
    describe: 'GitHub 연동이 끊긴 상태. 재연동 유도 화면을 본다.',
    rules: [
      {
        path: '/me/home',
        status: 403,
        reason: 'token_invalid',
        message: 'GitHub 연동 권한이 만료되었어요.',
      },
      {
        path: '/analysis-runs*',
        status: 403,
        reason: 'token_invalid',
        message: 'GitHub 연동 권한이 만료되었어요.',
      },
    ],
  },

  'run-expired': {
    describe: '분석 결과가 만료됨. 공고 입력부터 다시 시작하도록 안내하는지 본다.',
    rules: [
      {
        path: '/analysis-runs/*',
        status: 410,
        reason: 'run_expired',
        message: '분석 결과가 만료되었어요. 다시 분석해주세요.',
      },
    ],
  },

  'report-unavailable': {
    describe: '리포트를 만들 수 없는 면접. 409 분기를 본다.',
    rules: [
      {
        path: '/interviews/*/report',
        status: 409,
        reason: 'report_unavailable',
        message: '아직 리포트를 만들 수 없는 면접이에요.',
      },
    ],
  },

  'session-limit': {
    describe: '면접 생성이 동시 세션 제한에 걸린 상태.',
    rules: [
      {
        path: '/interviews',
        method: 'POST',
        status: 409,
        reason: 'session_limit_exceeded',
        message: '이미 진행 중인 면접이 있어요.',
      },
    ],
  },

  'server-error': {
    describe: '모든 요청이 500. 예상 못 한 오류의 공통 처리를 본다.',
    rules: [
      {
        path: '*',
        status: 500,
        reason: 'internal_error',
        message: '일시적인 오류가 발생했어요.',
      },
    ],
  },

  /**
   * WS 연결 직후 오류. `recoverable: true`라 같은 세션에서 재시도할 수 있다.
   * 준비 실패 화면은 seed 면접(`SEED_PREPARING_FAILED_INTERVIEW_ID`)으로도 열 수 있다.
   */
  'ws-question-failed': {
    describe: 'WS 연결 직후 question_failed. 복구 가능한 오류 배너를 본다.',
    rules: [
      {
        path: '/ws/interviews/*',
        reason: 'question_failed',
        code: 'ERR_QUESTION_FAILED',
        recoverable: true,
      },
    ],
  },

  /** `recoverable: false`라 서버가 세션을 닫는다. 레포 재선택으로 유도해야 한다. */
  'ws-repo-unreachable': {
    describe: 'WS 연결 직후 repo_unreachable 후 연결 종료. 복구 불가 분기를 본다.',
    rules: [
      {
        path: '/ws/interviews/*',
        reason: 'repo_unreachable',
        code: 'ERR_REPO_UNREACHABLE',
        recoverable: false,
      },
    ],
  },

  offline: {
    describe: '모든 요청이 네트워크 단계에서 실패. HTTP 실패와 구분되는지 본다.',
    rules: [{ path: '*', kind: 'network' }],
  },

  slow: {
    describe: '모든 요청이 10초 뒤 실패. 로딩 상태와 타임아웃 처리를 본다.',
    rules: [{ path: '*', kind: 'timeout', delayMs: 10_000 }],
  },
};

/**
 * 시나리오를 적용한다. 켜져 있던 규칙은 먼저 지운다.
 * 시나리오끼리 겹치면 어느 쪽이 이겼는지 알 수 없어 검증이 무의미해진다.
 */
export function applyScenario(name: ScenarioName) {
  const scenario = scenarios[name];
  if (!scenario) {
    throw new Error(
      `알 수 없는 시나리오: ${name}. 사용 가능: ${Object.keys(scenarios).join(', ')}`,
    );
  }
  clearFaults();
  scenario.rules.forEach(addFault);
  return scenario;
}

/**
 * devtools에서 부를 수 있는 콘솔 API.
 * 규칙을 직접 쓰는 `fault()`와 이름으로 거는 `scenario()`를 함께 노출한다.
 */
export function installMockConsole() {
  const api = {
    scenario: (name: ScenarioName) => {
      const applied = applyScenario(name);
      console.info(`[msw] 시나리오 '${name}' 적용 — ${applied.describe}`);
      return listFaults();
    },
    scenarios: () => {
      console.table(
        Object.entries(scenarios).map(([name, s]) => ({ 시나리오: name, 설명: s.describe })),
      );
      return Object.keys(scenarios);
    },
    fault: (rule: FaultRule) => {
      addFault(rule);
      console.info('[msw] 장애 주입 규칙 추가', rule);
      return listFaults();
    },
    faults: () => listFaults(),
    clear: () => {
      clearFaults();
      console.info('[msw] 장애 주입 규칙 전부 해제');
    },
  };
  Object.assign(window, { msw: api });

  const active = listFaults();
  if (active.length > 0) {
    console.warn(
      `[msw] 장애 주입 규칙 ${active.length}건이 켜져 있습니다. 해제하려면 msw.clear()`,
      active,
    );
  }
}
