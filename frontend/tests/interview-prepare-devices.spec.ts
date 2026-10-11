import { expect, test, type Page } from '@playwright/test';

// 면접 준비 화면의 마이크·스피커 점검. 실제 장치 대신 getUserMedia·enumerateDevices를 바꿔 끼운다.
// mic: 'ok'면 오실레이터로 만든 가짜 입력 스트림을, 그 외에는 해당 DOMException을 돌려준다.
// 열린 스트림은 window.__mics에 쌓아 마이크가 닫혔는지 확인한다.
// window.__micResult를 바꾸면 다음 요청부터 결과가 바뀐다(권한을 나중에 허용한 상황).
// 권한 상태 API는 window.__perm.onchange()로 변경 알림을 흉내 낸다.
type MicResult = 'ok' | 'NotAllowedError' | 'NotFoundError' | 'NotReadableError';

async function stubMic(page: Page, mic: MicResult) {
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
  }, mic);
}

async function openPrepare(page: Page, mic: MicResult) {
  await stubMic(page, mic);
  await page.addInitScript(() => {
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
  });

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

test('녹음을 재생하지 못하면 안내하고, 다시 테스트하면 안내를 지운다', async ({ page }) => {
  // 자동재생 차단·스피커 분리 등으로 play()가 거부된 상황.
  await page.addInitScript(() => {
    HTMLMediaElement.prototype.play = () => Promise.reject(new DOMException('stub', 'NotAllowedError'));
  });
  await openPrepare(page, 'ok');
  const notice = page.getByRole('alert').filter({ hasText: '재생하지 못했어요' });

  await page.getByRole('button', { name: '마이크 테스트' }).click();
  await page.getByRole('button', { name: /녹음 끝내기/ }).click();
  await expect(notice).toBeVisible();
  await expect(page.getByRole('button', { name: '마이크 테스트' })).toBeEnabled();

  await page.getByRole('button', { name: '마이크 테스트' }).click();
  await expect(notice).toHaveCount(0);
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

/**
 * MSW로 면접을 새로 만들어 준비가 끝날 때까지(prepareCompleted) 기다린다.
 * runId·레포 id는 mock seed 값이다(src/mocks/db/config.ts, fixtures/analysis.ts).
 */
async function openReadyInterview(page: Page, mic: MicResult) {
  await stubMic(page, mic);
  await page.goto('/home');
  // mock 워커가 페이지를 잡기 전에 보낸 요청은 dev 서버로 새어 나간다.
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  const { interviewId } = await page.evaluate(async () => {
    const res = await fetch('/api/interviews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        runId: '5c7b9e10-0000-4000-8000-00000000aaaa',
        repositoryIds: ['9f1c0a6e-0001-4f00-8a01-000000000001'],
      }),
    });
    return (await res.json()) as { interviewId: string };
  });
  // mock DB는 페이지 메모리에 있다. page.goto로 새로 불러오면 방금 만든 면접이 사라진다.
  await page.evaluate((url) => {
    window.history.pushState({}, '', url);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, `/interview/${interviewId}/prepare`);
  await expect(page.getByText('첫 질문 구성 완료')).toBeVisible({ timeout: 10_000 });
}

test('마이크가 정상이면 준비가 끝난 뒤 면접을 시작할 수 있다', async ({ page }) => {
  await openReadyInterview(page, 'ok');
  await expect(page.getByRole('button', { name: '면접 시작하기' })).toBeEnabled();
  await expect(page.getByText(/마이크를 확인해야 면접을 시작할 수 있어요/)).toHaveCount(0);
});

test('마이크를 쓸 수 없으면 준비가 끝나도 면접 시작을 막고, 해결하면 풀린다', async ({ page }) => {
  await openReadyInterview(page, 'NotAllowedError');
  await expect(page.getByRole('button', { name: '면접 시작하기' })).toBeDisabled();
  await expect(page.getByText(/마이크를 확인해야 면접을 시작할 수 있어요/)).toBeVisible();

  await page.evaluate(() => {
    (window as unknown as { __micResult: string }).__micResult = 'ok';
  });
  await page.getByRole('button', { name: '다시 확인' }).click();
  await expect(page.getByRole('button', { name: '면접 시작하기' })).toBeEnabled();
});
