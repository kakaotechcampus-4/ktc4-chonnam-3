import { expect, test, type Page } from '@playwright/test';

// 음성 면접 WS·질문 음성 mock 검증. 계약은 spec/shared/decisions/0007 (Proposed).
// 화면 없이 페이지 안에서 WebSocket을 직접 열어 mock과 주고받는다.
const SEED_SESSION = 'sess_0000000000000005';
const SEED_INTERVIEW = 'a3d51c20-1005-4c00-9a00-000000000005';

async function bootMock(page: Page) {
  await page.goto('/home');
  await page.waitForFunction(() => 'msw' in window);
}

/** 소켓을 열고 첫 question을 받을 때까지 기다린다. */
function firstQuestion(page: Page) {
  return page.evaluate(
    (session) =>
      new Promise<Record<string, unknown>>((resolve) => {
        const socket = new WebSocket(`ws://${location.host}/api/ws/interviews/${session}`);
        socket.onmessage = (event) => {
          const message = JSON.parse(event.data as string) as Record<string, unknown>;
          if (message.type !== 'question') return;
          socket.close();
          resolve(message);
        };
      }),
    SEED_SESSION,
  );
}

test('question에 메인 질문 번호·꼬리질문 단계·질문 음성 주소가 실린다', async ({ page }) => {
  await bootMock(page);
  const question = await firstQuestion(page);
  expect(question).toMatchObject({
    turn: 1,
    mainIndex: 1,
    followUpDepth: 0,
    audioUrl: `/api/interviews/${SEED_INTERVIEW}/turns/1/question-audio`,
  });

  const detail = await page.evaluate(
    (id) => fetch(`/api/interviews/${id}`).then((res) => res.json()),
    SEED_INTERVIEW,
  );
  expect(detail.totalTurns).toBe(9);
  expect(detail.turns[0]).toMatchObject({ mainIndex: 1, followUpDepth: 0 });
});

test('질문 음성 주소는 WAV를 돌려주고 tts-unavailable이면 500이다', async ({ page }) => {
  await bootMock(page);
  const url = `/api/interviews/${SEED_INTERVIEW}/turns/1/question-audio`;
  const ok = await page.evaluate(async (target) => {
    const res = await fetch(target);
    return {
      status: res.status,
      type: res.headers.get('Content-Type'),
      size: (await res.arrayBuffer()).byteLength,
    };
  }, url);
  expect(ok.status).toBe(200);
  expect(ok.type).toBe('audio/wav');
  expect(ok.size).toBeGreaterThan(44);

  await page.evaluate(() =>
    (window as unknown as { msw: { scenario: (n: string) => void } }).msw.scenario(
      'tts-unavailable',
    ),
  );
  const failed = await page.evaluate((target) => fetch(target).then((res) => res.status), url);
  expect(failed).toBe(500);
});

type Received = Record<string, unknown> & { type: string };

/**
 * 첫 question을 받은 뒤 steps를 순서대로 보내고, until이 참이 될 때까지 받은 메시지를 모은다.
 * 숫자 step은 그 크기의 바이너리 조각 1개다.
 */
function exchange(page: Page, steps: (object | number)[], until: string, timeoutMs = 8000) {
  return page.evaluate(
    ({ session, steps, until, timeoutMs }) =>
      new Promise<Received[]>((resolve) => {
        const socket = new WebSocket(`ws://${location.host}/api/ws/interviews/${session}`);
        const got: Received[] = [];
        let started = false;
        const done = () => {
          socket.close();
          resolve(got);
        };
        setTimeout(done, timeoutMs);
        socket.onmessage = async (event) => {
          const message = JSON.parse(event.data as string) as Received;
          if (started) got.push(message);
          if (started && message.type === until) return done();
          if (started || message.type !== 'question') return;
          started = true;
          for (const step of steps) {
            socket.send(typeof step === 'number' ? new Uint8Array(step) : JSON.stringify(step));
            await new Promise((r) => setTimeout(r, 20));
          }
        };
      }),
    { session: SEED_SESSION, steps, until, timeoutMs },
  );
}

const start = { type: 'answerStart', turn: 1, mimeType: 'audio/webm;codecs=opus' };
const end = { type: 'answerEnd', turn: 1 };
const chunks = (count: number) => Array.from({ length: count }, () => 64);
const types = (got: Received[]) => got.map((m) => m.type);
const scenario = (page: Page, name: string) =>
  page.evaluate(
    (n) => (window as unknown as { msw: { scenario: (s: string) => void } }).msw.scenario(n),
    name,
  );

test('오디오 조각 4개마다 임시 전사가 늘고 answerEnd 뒤 최종 전사와 다음 질문이 온다', async ({
  page,
}) => {
  await bootMock(page);
  const got = await exchange(page, [start, ...chunks(8), end], 'question');
  const partials = got.filter((m) => m.type === 'transcriptPartial').map((m) => m.text);
  expect(partials).toEqual(['payment-service가', 'payment-service가 가장']);
  expect(types(got).filter((t) => t !== 'transcriptPartial')).toEqual([
    'transcript',
    'answerReceived',
    'thinking',
    'evidenceCheck',
    'question',
  ]);
  expect(got.find((m) => m.type === 'transcript')?.text).toBe(
    'payment-service가 가장 기억에 남습니다. 결제 실패 재시도를 직접 설계했습니다.',
  );
  expect(got.at(-1)).toMatchObject({ turn: 2, mainIndex: 2, followUpDepth: 0 });
});

test('no-partial이면 임시 전사 없이 최종 전사만 온다', async ({ page }) => {
  await bootMock(page);
  await scenario(page, 'no-partial');
  const got = await exchange(page, [start, ...chunks(8), end], 'transcript');
  expect(types(got)).toEqual(['transcript']);
});

test('stt 실패는 한 번만 나고 같은 턴에 다시 답할 수 있다', async ({ page }) => {
  await bootMock(page);
  await scenario(page, 'ws-stt-failed');
  const failed = await exchange(page, [start, ...chunks(4), end], 'error');
  expect(failed.at(-1)).toMatchObject({ reason: 'stt_failed', recoverable: true });

  const retried = await exchange(page, [start, ...chunks(4), end], 'transcript');
  expect(types(retried)).toContain('transcript');
});

test('빈 전사는 details.cause가 empty_transcript다', async ({ page }) => {
  await bootMock(page);
  await scenario(page, 'ws-stt-empty');
  const got = await exchange(page, [start, end], 'error');
  expect(got.at(-1)).toMatchObject({
    reason: 'stt_failed',
    details: { cause: 'empty_transcript' },
  });
});

test('다시 듣기 요청이면 answerReceived 없이 같은 턴 question이 다시 온다', async ({ page }) => {
  await bootMock(page);
  await scenario(page, 'ws-repeat-request');
  const got = await exchange(page, [start, ...chunks(4), end], 'question');
  expect(got.find((m) => m.type === 'transcript')?.text).toBe('다시 한 번 말씀해 주시겠어요?');
  expect(types(got)).not.toContain('answerReceived');
  expect(got.at(-1)).toMatchObject({ type: 'question', turn: 1 });
});

test('같은 턴 answerStart가 다시 오면 받던 오디오를 버리고 새로 받는다', async ({ page }) => {
  await bootMock(page);
  const got = await exchange(page, [start, ...chunks(4), start, ...chunks(4), end], 'transcript');
  expect(types(got)).not.toContain('error');
  expect(types(got)).toContain('transcript');
});

test('다른 턴의 answerStart는 answer_rejected다', async ({ page }) => {
  await bootMock(page);
  const got = await exchange(page, [{ ...start, turn: 5 }], 'error');
  expect(got.at(-1)).toMatchObject({ reason: 'answer_rejected', recoverable: true });
});

test('msw.dropWs()는 열린 면접 소켓을 서버 쪽에서 끊는다', async ({ page }) => {
  await bootMock(page);
  const closed = await page.evaluate(
    (session) =>
      new Promise<boolean>((resolve) => {
        const socket = new WebSocket(`ws://${location.host}/api/ws/interviews/${session}`);
        socket.onclose = () => resolve(true);
        socket.onmessage = (event) => {
          if ((JSON.parse(event.data as string) as Received).type !== 'question') return;
          (window as unknown as { msw: { dropWs: () => void } }).msw.dropWs();
        };
        setTimeout(() => resolve(false), 8000);
      }),
    SEED_SESSION,
  );
  expect(closed).toBe(true);
});

test('텍스트 answer 메시지는 더 받지 않고 상세 조회 answerMode는 voice다', async ({ page }) => {
  await bootMock(page);
  const got = await exchange(
    page,
    [{ type: 'answer', turn: 1, text: '텍스트 답변' }],
    'answerReceived',
    2500,
  );
  expect(types(got)).not.toContain('answerReceived');

  const detail = await page.evaluate(
    (id) => fetch(`/api/interviews/${id}`).then((res) => res.json()),
    SEED_INTERVIEW,
  );
  expect(detail.answerMode).toBe('voice');
});
