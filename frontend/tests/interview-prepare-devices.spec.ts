import { expect, test, type Page } from '@playwright/test';

// 면접 준비 화면의 마이크·스피커 점검. 실제 장치 대신 getUserMedia·enumerateDevices를 바꿔 끼운다.
// mic: 'ok'면 오실레이터로 만든 가짜 입력 스트림을, 그 외에는 해당 DOMException을 돌려준다.
// 열린 스트림은 window.__mics에 쌓아 마이크가 닫혔는지 확인한다.
// window.__micResult를 바꾸면 다음 요청부터 결과가 바뀐다(권한을 나중에 허용한 상황).
// 권한 상태 API는 window.__perm.onchange()로 변경 알림을 흉내 낸다.
type MicResult = 'ok' | 'NotAllowedError' | 'NotFoundError' | 'NotReadableError';

async function openPrepare(page: Page, mic: MicResult) {
  await page.addInitScript((initial) => {
    const w = window as unknown as { __micResult: string; __perm: { onchange: (() => void) | null } };
    w.__micResult = initial;
    w.__perm = { onchange: null };
    navigator.permissions.query = async () => w.__perm as unknown as PermissionStatus;
    const mics: MediaStream[] = [];
    (window as unknown as { __mics: MediaStream[] }).__mics = mics;
    navigator.mediaDevices.enumerateDevices = async () =>
      [
        { deviceId: 'mic-a', kind: 'audioinput', label: '마이크 A', groupId: 'a' },
        { deviceId: 'mic-b', kind: 'audioinput', label: '마이크 B', groupId: 'b' },
        { deviceId: 'spk-a', kind: 'audiooutput', label: '스피커 A', groupId: 'a' },
      ] as MediaDeviceInfo[];
    navigator.mediaDevices.getUserMedia = async () => {
      if (w.__micResult !== 'ok') throw new DOMException('stub', w.__micResult);
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const dst = ctx.createMediaStreamDestination();
      osc.connect(dst);
      osc.start();
      mics.push(dst.stream);
      return dst.stream;
    };

    // 준비 WS는 이 테스트 관심사가 아니다. 열리기만 하고 아무 메시지도 보내지 않는다.
    (window as unknown as { WebSocket: unknown }).WebSocket = class {
      static OPEN = 1;
      readyState = 0;
      onopen = null;
      onmessage = null;
      onclose = null;
      close() {}
    };

    const originalFetch = window.fetch;
    window.fetch = async (input, options) => {
      if (!String(input).endsWith('/api/interviews/iv-1')) return originalFetch(input, options);
      return new Response(
        JSON.stringify({
          id: 'iv-1',
          sessionId: 'ses-1',
          runId: 'run-1',
          status: 'preparing',
          answerMode: 'text',
          position: 'BE',
          companyName: null,
          repositoryNames: [],
          currentTurn: 0,
          totalTurns: 5,
          remainingSeconds: null,
          turns: [],
          lastError: null,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    };
  }, mic);

  await page.goto('/interview/iv-1/prepare');
  await expect(page.getByRole('heading', { name: '마이크 · 스피커 점검' })).toBeVisible();
}

/** 열렸던 마이크 스트림마다 트랙이 살아 있는지. */
const micStates = (page: Page) =>
  page.evaluate(() =>
    (window as unknown as { __mics: MediaStream[] }).__mics.map((m) =>
      m.getTracks().every((t) => t.readyState === 'live'),
    ),
  );

test('권한이 있으면 장치 목록을 보여주고 마이크는 녹음 중에만 연다', async ({ page }) => {
  await openPrepare(page, 'ok');
  await expect(page.getByText('✓ 정상 감지됨')).toBeVisible();
  await expect(page.getByLabel('마이크 선택').locator('option')).toHaveText(['마이크 A', '마이크 B']);
  await expect(page.getByLabel('스피커 선택').locator('option')).toHaveText(['스피커 A']);
  await expect(page.getByRole('button', { name: '테스트 재생' })).toBeEnabled();

  // 권한 확인용으로 연 마이크는 바로 닫는다.
  await expect.poll(() => micStates(page)).toEqual([false]);

  // 녹음 → 끝내기 → 재생 → 처음 상태. 녹음이 끝나면 재생 전에 마이크부터 닫는다.
  await page.getByRole('button', { name: '마이크 테스트' }).click();
  await expect(page.getByRole('button', { name: /녹음 끝내기/ })).toBeVisible();
  await expect.poll(() => micStates(page)).toEqual([false, true]);
  await page.getByRole('button', { name: /녹음 끝내기/ }).click();
  await expect.poll(() => micStates(page)).toEqual([false, false]);
  await expect(page.getByRole('button', { name: '마이크 테스트' })).toBeVisible({ timeout: 10_000 });

  // 다른 마이크를 고르면 진행 중인 녹음을 멈춘다.
  await page.getByRole('button', { name: '마이크 테스트' }).click();
  await expect.poll(() => micStates(page)).toEqual([false, false, true]);
  await page.getByLabel('마이크 선택').selectOption('mic-b');
  await expect(page.getByRole('button', { name: '마이크 테스트' })).toBeVisible();
  await expect.poll(() => micStates(page)).toEqual([false, false, false]);

  // 녹음 중 화면을 떠나도 마이크를 닫는다. 브라우저의 녹음 표시가 남지 않아야 한다.
  await page.getByRole('button', { name: '마이크 테스트' }).click();
  await expect.poll(() => micStates(page)).toEqual([false, false, false, true]);
  await page.evaluate(() => {
    window.history.pushState({}, '', '/home');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect.poll(() => micStates(page)).toEqual([false, false, false, false]);
});

test('녹음은 최대 시간이 지나면 저절로 끝난다', async ({ page }) => {
  await page.clock.install();
  await openPrepare(page, 'ok');
  await page.getByRole('button', { name: '마이크 테스트' }).click();
  await expect(page.getByRole('button', { name: '녹음 끝내기 (5)' })).toBeVisible();
  await page.clock.runFor(5000);
  await expect.poll(() => micStates(page)).toEqual([false, false]);
});

test('마이크 권한을 거부하면 허용 방법을 안내한다', async ({ page }) => {
  await openPrepare(page, 'NotAllowedError');
  await expect(page.getByText('권한 거부됨')).toBeVisible();
  await expect(page.getByText(/마이크 권한을 허용해주세요/)).toBeVisible();
});

test('마이크가 없으면 연결을 안내한다', async ({ page }) => {
  await openPrepare(page, 'NotFoundError');
  await expect(page.getByText('마이크 없음')).toBeVisible();
});

test('다른 앱이 마이크를 쓰고 있으면 따로 안내한다', async ({ page }) => {
  await openPrepare(page, 'NotReadableError');
  await expect(page.getByText('마이크 사용 중')).toBeVisible();
  await expect(page.getByText(/다른 앱이 마이크를 쓰고 있어요/)).toBeVisible();
});

test('다시 확인을 누르면 권한을 다시 요청한다', async ({ page }) => {
  await openPrepare(page, 'NotAllowedError');
  await expect(page.getByText('권한 거부됨')).toBeVisible();
  await page.evaluate(() => {
    (window as unknown as { __micResult: string }).__micResult = 'ok';
  });
  await page.getByRole('button', { name: '다시 확인' }).click();
  await expect(page.getByText('✓ 정상 감지됨')).toBeVisible();
  await expect(page.getByRole('button', { name: '다시 확인' })).toHaveCount(0);
});

test('사이트 설정에서 권한을 바꾸면 새로고침 없이 다시 확인한다', async ({ page }) => {
  await openPrepare(page, 'NotAllowedError');
  await expect(page.getByText('권한 거부됨')).toBeVisible();
  await page.evaluate(() => {
    const w = window as unknown as { __micResult: string; __perm: { onchange: () => void } };
    w.__micResult = 'ok';
    w.__perm.onchange();
  });
  await expect(page.getByText('✓ 정상 감지됨')).toBeVisible();
});
