import { expect, test, type Page } from '@playwright/test';

const ID = 'a3d51c20-1005-4c00-9a00-000000000005';
type Mode = 'success' | 'network' | 'server_unknown' | 'in_progress' | 'failed';
type Probe = {
  calls: { requestId: string }[];
  count: number;
  before: string;
  oldSessionId: string;
  sockets: string[];
  sent: string[];
  after: () => string;
};

/** 실제 MSW 저장 문답을 고정하고 새 REST 경계만 시험용 응답으로 대체한다. */
async function openFailure(
  page: Page,
  options: { mode?: Mode; eligible?: boolean; legacy?: boolean; used?: number } = {},
) {
  await page.goto('/home');
  await page.waitForFunction(() => 'msw' in window);
  await page.evaluate(
    async ({ id, options }) => {
      const dbPath = '/src/mocks/db/index.ts';
      const fixturePath = '/src/mocks/fixtures/interview.ts';
      const database = (await import(dbPath)) as typeof import('../src/mocks/db');
      const fixture = (await import(
        fixturePath
      )) as typeof import('../src/mocks/fixtures/interview');
      const record = database.getInterview(id)!;
      record.fixedStatus = 'in_progress';
      record.liveTurns = structuredClone(fixture.completedTurns.slice(0, 4));
      const state: Probe = {
        calls: [],
        count: options.used ?? 0,
        before: JSON.stringify(record.liveTurns),
        oldSessionId: record.sessionId,
        sockets: [],
        sent: [],
        after: () => JSON.stringify(record.liveTurns?.slice(0, 4)),
      };
      Object.assign(window, { __questionRetry: state });
      const actualFetch = window.fetch.bind(window);
      const detailPath = `/api/interviews/${id}`;
      let completed: { interviewId: string; sessionId: string; turnNo: number } | null = null;
      let pendingId: string | null = null;
      const response = (body: unknown, status = 200) =>
        new Response(JSON.stringify(body), {
          status,
          headers: { 'Content-Type': 'application/json' },
        });
      const failure = (reason: string) =>
        response({ error: { reason, message: '합성 시험 오류' } }, 409);
      window.fetch = async (input, init) => {
        const url = new URL(
          typeof input === 'string' ? input : input instanceof URL ? input.href : input.url,
          location.origin,
        );
        const method = init?.method ?? (input instanceof Request ? input.method : 'GET');
        if (url.pathname === `${detailPath}/question/retry` && method === 'POST') {
          const request = JSON.parse(String(init?.body)) as { requestId: string };
          state.calls.push(request);
          if (options.mode === 'network' && state.calls.length === 1) {
            throw new TypeError('합성 네트워크 결과 불명');
          }
          if (options.mode === 'server_unknown' && state.calls.length === 1) {
            return response({ error: { reason: 'internal_error', message: '결과 불명' } }, 503);
          }
          if (completed && request.requestId === pendingId) return response(completed);
          if (state.count >= 1 && request.requestId !== pendingId) {
            return failure('question_retry_limit');
          }
          pendingId = request.requestId;
          state.count = 1;
          if (options.mode === 'in_progress' && state.calls.length === 1) {
            return failure('question_retry_in_progress');
          }
          await new Promise((resolve) => setTimeout(resolve, 700));
          if (options.mode === 'failed') return failure('question_retry_failed');
          const next = structuredClone(fixture.completedTurns[4]);
          next.answer = null;
          record.liveTurns!.push(next);
          record.sessionId = `sess_retry_${crypto.randomUUID()}`;
          completed = { interviewId: id, sessionId: record.sessionId, turnNo: 5 };
          return response(completed);
        }
        const received = await actualFetch(input, init);
        if (url.pathname !== detailPath || method !== 'GET') return received;
        const detail = (await received.json()) as Record<string, unknown>;
        if (!options.legacy) {
          detail.canRetryQuestion = options.eligible !== false && state.count < 1;
          detail.questionRetryCount = state.count;
        }
        return response(detail, received.status);
      };
      const OriginalSocket = window.WebSocket;
      window.WebSocket = new Proxy(OriginalSocket, {
        construct(Target, args) {
          const socket = Reflect.construct(Target, args) as WebSocket;
          state.sockets.push(String(args[0]));
          const send = socket.send.bind(socket);
          socket.send = (data) => {
            state.sent.push(typeof data === 'string' ? data : '[binary]');
            send(data);
          };
          return socket;
        },
      });
      const control = (
        window as unknown as {
          msw: { clear: () => void; fault: (rule: object) => void };
        }
      ).msw;
      control.clear();
      // 원래 소켓의 한 번 실패만 재현한다. 성공 후 새 소켓까지 영구 실패시키지 않는다.
      control.fault({
        path: '/ws/interviews/*',
        reason: 'question_failed',
        code: 'ERR_QUESTION_FAILED',
        recoverable: false,
        times: 1,
      });
      history.pushState(null, '', `/interview/${id}/session`);
      dispatchEvent(new PopStateEvent('popstate'));
    },
    { id: ID, options },
  );
  await expect(page.getByRole('button', { name: '같은 레포로 다시 시작' })).toBeVisible();
}

async function probe(page: Page) {
  return page.evaluate(() => {
    const state = (window as unknown as { __questionRetry: Probe }).__questionRetry;
    return {
      calls: state.calls,
      count: state.count,
      preserved: state.before === state.after(),
      oldSessionId: state.oldSessionId,
      sockets: state.sockets,
      sent: state.sent,
    };
  });
}

test('저장된 네 답변을 보존하고 중복 요청 없이 새 소켓에서 5번 질문만 받는다', async ({ page }) => {
  await openFailure(page);
  const continueButton = page.getByRole('button', { name: '저장된 답변으로 계속하기' });
  await expect(continueButton).toBeEnabled();
  await continueButton.dblclick();
  await expect(page.getByRole('button', { name: '다음 질문을 준비하는 중…' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '나가기', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: '같은 레포로 다시 시작' })).toBeDisabled();
  await expect(page.getByText('질문 5 / 9 · 개발팀')).toBeVisible();
  await expect(page.getByRole('button', { name: '답변 시작' })).toBeEnabled();
  const state = await probe(page);
  expect(state.calls).toHaveLength(1);
  expect(state.calls[0].requestId).toMatch(/^[0-9a-f-]{36}$/);
  expect(state.preserved).toBe(true);
  expect(state.sockets).toHaveLength(2);
  expect(state.sockets[0]).toContain(`/${state.oldSessionId}`);
  expect(state.sockets[1]).not.toContain(`/${state.oldSessionId}`);
  expect(state.sent).toEqual([]);
});

for (const options of [{ eligible: false }, { legacy: true }, { used: 1 }]) {
  test(`이어서 받기 조건이 없는 경우 새 버튼을 숨긴다 ${JSON.stringify(options)}`, async ({
    page,
  }) => {
    await openFailure(page, options);
    await expect(page.getByRole('button', { name: '저장된 답변으로 계속하기' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '나가기', exact: true })).toBeEnabled();
    expect((await probe(page)).calls).toEqual([]);
  });
}

for (const mode of ['network', 'server_unknown', 'in_progress'] as const) {
  test(`${mode} 결과 불명 뒤 같은 requestId로 결과를 확인하고 이어간다`, async ({ page }) => {
    await openFailure(page, { mode });
    await page.getByRole('button', { name: '저장된 답변으로 계속하기' }).click();
    await expect(page.getByText(/같은 요청으로/)).toBeVisible();
    await page.getByRole('button', { name: '저장된 답변으로 계속하기' }).click();
    await expect(page.getByText('질문 5 / 9 · 개발팀')).toBeVisible();
    await expect(page.getByRole('button', { name: '답변 시작' })).toBeEnabled();
    const state = await probe(page);
    expect(state.calls).toHaveLength(2);
    expect(state.calls[0].requestId).toBe(state.calls[1].requestId);
    expect(state.count).toBe(1);
    expect(state.preserved).toBe(true);
  });
}

test('수동 재검토도 실패하면 답변을 보존하고 상한 뒤 새 요청을 막는다', async ({ page }) => {
  await openFailure(page, { mode: 'failed' });
  await page.getByRole('button', { name: '저장된 답변으로 계속하기' }).click();
  await expect(
    page.getByText('다음 질문을 다시 준비하지 못했어요. 나가거나 새 면접을 시작해주세요.'),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: '저장된 답변으로 계속하기' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '나가기', exact: true })).toBeEnabled();
  const state = await probe(page);
  expect(state.calls).toHaveLength(1);
  expect(state.count).toBe(1);
  expect(state.preserved).toBe(true);
});
