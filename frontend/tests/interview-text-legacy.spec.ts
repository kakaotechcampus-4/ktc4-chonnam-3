import { expect, test, type Page } from '@playwright/test';

const LIVE = 'a3d51c20-1005-4c00-9a00-000000000005';
const PREPARING = 'a3d51c20-1009-4c00-9a00-000000000009';

async function openLegacy(page: Page, prepare = false) {
  await page.addInitScript(() => {
    Reflect.set(window, '__legacyMicRequests', 0);
    navigator.mediaDevices.getUserMedia = async () => {
      Reflect.set(
        window,
        '__legacyMicRequests',
        Number(Reflect.get(window, '__legacyMicRequests')) + 1,
      );
      throw new DOMException('legacy text needs no microphone', 'NotAllowedError');
    };
  });
  await page.goto('/home');
  await page.waitForFunction(() => 'msw' in window);
  await page.evaluate(
    async ({ id, prepare }) => {
      const modulePath = '/src/mocks/db/interviews.ts';
      const { getInterview } = await import(modulePath);
      const record = getInterview(id);
      if (!record) throw new Error('isolated legacy fixture missing');
      record.answerMode = 'text';
      if (prepare) {
        record.fixedStatus = undefined;
        record.fixedLastError = undefined;
        record.createdAt = Date.now();
      }
      history.pushState({}, '', `/interview/${id}/${prepare ? 'prepare' : 'session'}`);
      dispatchEvent(new PopStateEvent('popstate'));
    },
    { id: prepare ? PREPARING : LIVE, prepare },
  );
}

test('기존 text 면접은 마이크와 TTS 없이 원문 답변을 제출한다', async ({ page }) => {
  const audioRequests: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/question-audio')) audioRequests.push(request.url());
  });
  await openLegacy(page);
  const input = page.getByRole('textbox', { name: '답변' });
  await expect(input).toBeEnabled();
  await expect(page.getByRole('button', { name: '답변 시작', exact: true })).toHaveCount(0);
  const original = '원문을 유지한 텍스트 답변입니다.\n직접 확인한 범위를 구분합니다.';
  await input.fill(original);
  await page.getByRole('button', { name: '답변 제출', exact: true }).click();
  await expect(page.getByText('질문 2 / 9 · 개발팀')).toBeVisible();
  const saved = await page.evaluate(async (id) => {
    const response = await fetch(`/api/interviews/${id}`);
    return (await response.json()).turns[0].answer;
  }, LIVE);
  expect(saved).toBe(original);
  expect(await page.evaluate(() => Reflect.get(window, '__legacyMicRequests'))).toBe(0);
  expect(audioRequests).toEqual([]);
});

test('기존 text 초안은 재접속으로 사라지지 않고 같은 턴에서 수동 제출한다', async ({ page }) => {
  await openLegacy(page);
  const input = page.getByRole('textbox', { name: '답변' });
  await expect(input).toBeEnabled();
  await input.fill('재접속 전에 작성한 초안');
  await page.evaluate(async () => {
    const modulePath = '/src/mocks/ws/interview.ts';
    const { dropInterviewSockets } = await import(modulePath);
    dropInterviewSockets();
  });
  await expect(page.getByText('연결이 끊겼어요 · 다시 연결하는 중이에요')).toBeVisible();
  await expect(input).toBeDisabled();
  await expect(input).toBeEnabled({ timeout: 10_000 });
  await expect(input).toHaveValue('재접속 전에 작성한 초안');
  await page.getByRole('button', { name: '답변 제출', exact: true }).click();
  await expect(page.getByText('질문 2 / 9 · 개발팀')).toBeVisible();
  await expect(page.getByRole('textbox', { name: '답변' })).toHaveValue('');
});

test('기존 text 준비는 마이크 권한 없이 완료하고 text 화면으로 들어간다', async ({ page }) => {
  await openLegacy(page, true);
  const start = page.getByRole('button', { name: '면접 시작하기', exact: true });
  await expect(start).toBeEnabled({ timeout: 15_000 });
  await expect(page.getByText('마이크 · 스피커 점검', { exact: true })).toHaveCount(0);
  await start.click();
  await expect(page.getByRole('textbox', { name: '답변' })).toBeEnabled();
  expect(await page.evaluate(() => Reflect.get(window, '__legacyMicRequests'))).toBe(0);
});


test('텍스트 stale 오류는 질문 재전송 없이 즉시 초안과 저장 대기를 정리한다', async ({ page }) => {
  await openLegacy(page);
  const input = page.getByRole('textbox', { name: '답변' });
  await expect(input).toBeEnabled();
  await page.evaluate(() => {
    (window as unknown as { msw: { fault: (rule: object) => void } }).msw.fault({
      path: '/ws/interviews/*/reject', reason: 'answer_stale_turn',
      code: 'ERR_ANSWER_STALE_TURN', times: 1,
    });
  });
  await input.fill('지난 턴에 작성한 초안');
  await page.getByRole('button', { name: '답변 제출', exact: true }).click();
  await expect(input).toBeEnabled();
  await expect(input).toHaveValue('');
  await expect(page.getByText('답변을 저장하지 못했어요 · 다시 답변해주세요')).toHaveCount(0);
});
