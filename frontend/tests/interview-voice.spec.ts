import { expect, test, type Page } from '@playwright/test';

// 음성 면접 진행 화면(5b-v2). spec/frontend/designs/2026-10-05-voice-interview.md
// 마이크는 오실레이터로 만든 가짜 스트림을 쓰고, 서버는 MSW mock(seed 진행 중 면접)이다.
// 질문 음성이 사용자 동작 없이 재생되도록 자동재생 정책을 끈다.
test.use({ launchOptions: { args: ['--autoplay-policy=no-user-gesture-required'] } });

const SEED_IN_PROGRESS = 'a3d51c20-1005-4c00-9a00-000000000005';
type MicResult = 'ok' | 'NotAllowedError';

async function stubMic(page: Page, mic: MicResult = 'ok', options: { opus?: boolean } = {}) {
  await page.addInitScript(
    ({ mic, opus }) => {
      const mics: MediaStream[] = [];
      (window as unknown as { __mics: MediaStream[] }).__mics = mics;
      navigator.mediaDevices.getUserMedia = async () => {
        if (mic !== 'ok') throw new DOMException('stub', mic);
        const ctx = new AudioContext();
        const osc = ctx.createOscillator();
        const dst = ctx.createMediaStreamDestination();
        osc.connect(dst);
        osc.start();
        mics.push(dst.stream);
        return dst.stream;
      };
      if (!opus) {
        const original = MediaRecorder.isTypeSupported.bind(MediaRecorder);
        MediaRecorder.isTypeSupported = (type) => !type.includes('opus') && original(type);
      }
    },
    { mic, opus: options.opus ?? true },
  );
}

/** mock 콘솔이 뜬 뒤 시나리오를 걸고 진행 중 seed 면접 화면을 연다. */
async function openSession(page: Page, scenario?: string) {
  await page.goto('/home');
  await page.waitForFunction(() => 'msw' in window);
  if (scenario) {
    await page.evaluate(
      (name) =>
        (window as unknown as { msw: { scenario: (n: string) => void } }).msw.scenario(name),
      scenario,
    );
  }
  await page.goto(`/interview/${SEED_IN_PROGRESS}/session`);
  await expect(page.getByRole('button', { name: '답변 시작' })).toBeEnabled();
}

const liveMics = (page: Page) =>
  page.evaluate(
    () =>
      (window as unknown as { __mics: MediaStream[] }).__mics.filter((m) =>
        m.getTracks().some((t) => t.readyState === 'live'),
      ).length,
  );

const FIRST_ANSWER =
  'payment-service가 가장 기억에 남습니다. 결제 실패 재시도를 직접 설계했습니다.';

async function answerOnce(page: Page) {
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByTestId('transcript-partial')).toBeVisible();
  await page.getByRole('button', { name: '답변 끝내기' }).click();
}

test('답변을 녹음하면 실시간 자막 뒤 최종 전사로 바뀌고 다음 질문으로 넘어간다', async ({
  page,
}) => {
  await stubMic(page);
  await openSession(page);
  await expect(page.getByText('질문 1 / 9 · 인사팀')).toBeVisible();
  await expect(
    page.getByText(/질문을 다시 들으려면 면접관에게 다시 들려달라고 답변하셔도 좋아요/),
  ).toBeVisible();

  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByRole('button', { name: '답변 끝내기' })).toBeVisible();
  await expect(page.getByTestId('transcript-partial')).toContainText('payment-service가');
  await page.getByRole('button', { name: '답변 끝내기' }).click();

  await expect(page.getByTestId('transcript-final')).toHaveText(FIRST_ANSWER);
  await expect(page.getByText('최종 전사로 평가해요')).toBeVisible();
  await expect.poll(() => liveMics(page)).toBe(0);
  await expect(page.getByText('질문 2 / 9 · 개발팀')).toBeVisible({ timeout: 10_000 });
});

test('꼬리질문은 메인 질문 번호 옆에 단계를 붙인다', async ({ page }) => {
  await stubMic(page);
  await openSession(page);
  await answerOnce(page);
  await expect(page.getByText('질문 2 / 9 · 개발팀')).toBeVisible({ timeout: 10_000 });
  await answerOnce(page);
  await expect(page.getByText('질문 3 / 9 · 꼬리질문 1 · 개발팀')).toBeVisible({ timeout: 10_000 });
});

test('임시 전사가 없으면 최종 전사만 보여 준다', async ({ page }) => {
  await stubMic(page);
  await openSession(page, 'no-partial');
  await page.getByRole('button', { name: '답변 시작' }).click();
  await page.waitForTimeout(1500);
  await expect(page.getByTestId('transcript-partial')).toHaveCount(0);
  await page.getByRole('button', { name: '답변 끝내기' }).click();
  await expect(page.getByText('답변을 정리하고 있어요…')).toBeVisible();
  await expect(page.getByTestId('transcript-final')).toHaveText(FIRST_ANSWER);
});

test('질문 음성이 재생되면 질문 텍스트를 숨긴 설정을 따른다', async ({ page }) => {
  await stubMic(page);
  await page.addInitScript(() => localStorage.setItem('devon.showQuestionText', 'false'));
  await openSession(page);
  await expect(page.getByText(/가장 애착이 가는 걸 하나만 소개해주세요/)).toHaveCount(0);
});

test('질문 음성을 못 받으면 질문 텍스트를 숨겼어도 보여 준다', async ({ page }) => {
  await stubMic(page);
  await page.addInitScript(() => localStorage.setItem('devon.showQuestionText', 'false'));
  await openSession(page, 'tts-unavailable');
  await expect(page.getByText(/가장 애착이 가는 걸 하나만 소개해주세요/)).toBeVisible();
  await expect(page.getByText('질문 음성을 재생하지 못해 텍스트로 보여드려요')).toBeVisible();
  // 답변 시작이 음성을 멈춰도 실패 상태가 유지돼 질문 텍스트가 남아야 한다.
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByText(/가장 애착이 가는 걸 하나만 소개해주세요/)).toBeVisible();
  await expect(page.getByTestId('transcript-partial')).toBeVisible();
  await page.getByRole('button', { name: '답변 끝내기' }).click();
  await expect(page.getByTestId('transcript-final')).toHaveText(FIRST_ANSWER);
});

test('자동재생이 막히면 질문 텍스트를 숨겼어도 보여 준다', async ({ page }) => {
  await stubMic(page);
  await page.addInitScript(() => {
    localStorage.setItem('devon.showQuestionText', 'false');
    HTMLMediaElement.prototype.play = () =>
      Promise.reject(new DOMException('stub', 'NotAllowedError'));
  });
  await openSession(page);
  await expect(page.getByText(/가장 애착이 가는 걸 하나만 소개해주세요/)).toBeVisible();
  await expect(page.getByText('질문 음성을 재생하지 못해 텍스트로 보여드려요')).toBeVisible();
  await expect(page.getByRole('button', { name: /질문 듣기/ })).toHaveCount(0);
});

test('STT가 실패하면 안내 뒤 같은 턴에 다시 답할 수 있다', async ({ page }) => {
  await stubMic(page);
  await openSession(page, 'ws-stt-failed');
  await answerOnce(page);
  await expect(page.getByRole('alert')).toContainText(
    '음성을 글로 바꾸지 못했어요 · 다시 답변해주세요',
  );
  await page.getByRole('button', { name: '다시 답변하기' }).click();
  await expect(page.getByText('질문 1 / 9 · 인사팀')).toBeVisible();
  await answerOnce(page);
  await expect(page.getByTestId('transcript-final')).toHaveText(FIRST_ANSWER);
});

test('전사 결과가 비면 마이크 확인을 안내한다', async ({ page }) => {
  await stubMic(page);
  await openSession(page, 'ws-stt-empty');
  await answerOnce(page);
  await expect(page.getByRole('alert')).toContainText('목소리가 인식되지 않았어요');
});

test('다시 듣기를 요청하면 같은 질문으로 돌아간다', async ({ page }) => {
  await stubMic(page);
  await openSession(page, 'ws-repeat-request');
  await answerOnce(page);
  // 같은 턴 question이 곧바로 다시 오므로 전사는 남지 않고 듣기로 돌아간다. 다음 턴으로 넘어가지 않는다.
  await expect(page.getByRole('button', { name: '답변 시작' })).toBeVisible();
  await expect(page.getByTestId('transcript-final')).toHaveCount(0);
  await expect(page.getByText('질문 1 / 9 · 인사팀')).toBeVisible();
  await answerOnce(page);
  await expect(page.getByText('질문 2 / 9 · 개발팀')).toBeVisible({ timeout: 10_000 });
});

test('녹음 중 연결이 끊기면 실패로 보고 다시 연결된 뒤 다시 답할 수 있다', async ({ page }) => {
  await stubMic(page);
  await openSession(page);
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByTestId('transcript-partial')).toBeVisible();
  await page.evaluate(() => (window as unknown as { msw: { dropWs: () => void } }).msw.dropWs());

  await expect(page.getByRole('alert')).toContainText('연결이 끊겨 답변이 저장되지 않았어요');
  await expect.poll(() => liveMics(page)).toBe(0);
  await page.getByRole('button', { name: '다시 답변하기' }).click();
  await expect(page.getByRole('button', { name: '답변 시작' })).toBeEnabled({ timeout: 10_000 });
  await answerOnce(page);
  await expect(page.getByTestId('transcript-final')).toHaveText(FIRST_ANSWER);
});

// 전사(transcript)는 저장 완료가 아니다. 저장 완료 신호는 answerReceived다(0007 "실패와 복구").
test('저장 확인이 30초 안에 오지 않으면 저장 실패로 안내하고 다시 답할 수 있다', async ({
  page,
}) => {
  await page.clock.install();
  await stubMic(page);
  await openSession(page, 'ws-no-ack');
  await answerOnce(page);
  await expect(page.getByTestId('transcript-final')).toHaveText(FIRST_ANSWER);
  await page.clock.runFor(30_000);

  await expect(page.getByRole('alert')).toContainText('답변을 저장하지 못했어요');
  await page.getByRole('button', { name: '다시 답변하기' }).click();
  await answerOnce(page);
  await expect(page.getByText('질문 2 / 9 · 개발팀')).toBeVisible({ timeout: 10_000 });
});

test('전사 뒤 저장 확인 전에 연결이 끊기면 실패로 보고 다시 답할 수 있다', async ({ page }) => {
  await stubMic(page);
  await openSession(page, 'ws-no-ack');
  await answerOnce(page);
  await expect(page.getByTestId('transcript-final')).toHaveText(FIRST_ANSWER);
  await page.evaluate(() => (window as unknown as { msw: { dropWs: () => void } }).msw.dropWs());

  await expect(page.getByRole('alert')).toContainText('연결이 끊겨 답변이 저장되지 않았어요');
  await page.getByRole('button', { name: '다시 답변하기' }).click();
  await expect(page.getByRole('button', { name: '답변 시작' })).toBeEnabled({ timeout: 10_000 });
  await answerOnce(page);
  await expect(page.getByText('질문 2 / 9 · 개발팀')).toBeVisible({ timeout: 10_000 });
});

test('저장 뒤 확인 전에 연결이 끊겨도 재연결 후 저장된 답변을 보여 준다', async ({ page }) => {
  await stubMic(page);
  await openSession(page, 'ws-drop-before-ack');
  await answerOnce(page);

  // 재연결 뒤 서버가 다음 질문을 만드는 동안 본다. 재연결 전 GET으로 저장 여부를 이미 받았다.
  await expect(
    page.getByRole('status').filter({ hasText: '다음 질문을 만들고 있어요' }),
  ).toBeAttached({ timeout: 10_000 });
  expect(await page.getByRole('alert').count()).toBe(0);
  await expect(page.getByTestId('transcript-final')).toHaveText(FIRST_ANSWER);
  await expect(page.getByText('질문 2 / 9 · 개발팀')).toBeVisible({ timeout: 10_000 });
});

test('전사 뒤 저장 확인 전에 새로고침하면 끊김 안내와 함께 같은 턴부터 다시 시작한다', async ({
  page,
}) => {
  await stubMic(page);
  await openSession(page, 'ws-no-ack');
  await answerOnce(page);
  await expect(page.getByTestId('transcript-final')).toHaveText(FIRST_ANSWER);
  await page.reload();

  await expect(page.getByRole('alert')).toContainText('연결이 끊겨 답변이 저장되지 않았어요');
  await expect(page.getByText('질문 1 / 9 · 인사팀')).toBeVisible();
});

test('연결이 끊긴 동안에는 답변을 시작할 수 없다', async ({ page }) => {
  await stubMic(page);
  await openSession(page);
  await page.evaluate(() => (window as unknown as { msw: { dropWs: () => void } }).msw.dropWs());
  await expect(page.getByRole('button', { name: '답변 시작' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '답변 시작' })).toBeEnabled({ timeout: 10_000 });
});

test('녹음 중 마이크가 끊기면 안내하고 마이크를 정리한다', async ({ page }) => {
  await stubMic(page);
  await openSession(page);
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByRole('button', { name: '답변 끝내기' })).toBeVisible();
  await page.evaluate(() => {
    const mics = (window as unknown as { __mics: MediaStream[] }).__mics;
    mics.at(-1)!.getAudioTracks()[0].dispatchEvent(new Event('ended'));
  });
  await expect(page.getByRole('alert')).toContainText('마이크 연결이 끊겼어요');
  await expect.poll(() => liveMics(page)).toBe(0);
});

test('마이크를 열 수 없으면 녹음하지 않고 안내한다', async ({ page }) => {
  await stubMic(page, 'NotAllowedError');
  await openSession(page);
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByRole('alert')).toContainText('마이크를 사용할 수 없어요');
});

test('180초가 지나면 녹음이 저절로 끝나고 제출된다', async ({ page }) => {
  await page.clock.install();
  await stubMic(page);
  await openSession(page);
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByTestId('transcript-partial')).toBeVisible();
  await page.clock.runFor(180_000);
  await expect(page.getByTestId('transcript-final')).toHaveText(FIRST_ANSWER);
});

test('녹음 중 새로고침하면 끊김 안내와 함께 같은 턴부터 다시 시작한다', async ({ page }) => {
  await stubMic(page);
  await openSession(page);
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByTestId('transcript-partial')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('연결이 끊겨 답변이 저장되지 않았어요');
  await expect(page.getByText('질문 1 / 9 · 인사팀')).toBeVisible();
});

test('정상 제출 뒤 새로고침하면 끊김 안내가 없다', async ({ page }) => {
  await stubMic(page);
  await openSession(page);
  await answerOnce(page);
  await expect(page.getByTestId('transcript-final')).toHaveText(FIRST_ANSWER);
  await page.reload();
  await expect(page.getByRole('button', { name: '답변 시작' })).toBeEnabled();
  await expect(page.getByText(/연결이 끊겨 답변이 저장되지 않았어요/)).toHaveCount(0);
});

test('녹음 중 면접을 종료하면 마이크를 닫는다', async ({ page }) => {
  await stubMic(page);
  await openSession(page);
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByRole('button', { name: '답변 끝내기' })).toBeVisible();
  await page.getByRole('button', { name: '면접 종료' }).click();
  await page.getByRole('button', { name: '종료하기' }).click();
  await expect(page).toHaveURL(/\/home$/);
  await expect.poll(() => liveMics(page)).toBe(0);
});

test('opus 미지원이어도 답변이 끝까지 처리된다', async ({ page }) => {
  await stubMic(page, 'ok', { opus: false });
  await openSession(page);
  await answerOnce(page);
  await expect(page.getByTestId('transcript-final')).toHaveText(FIRST_ANSWER);
});

test('답변 시작을 연타해도 마이크는 하나만 열린다', async ({ page }) => {
  await stubMic(page);
  await openSession(page);
  await page.getByRole('button', { name: '답변 시작' }).dblclick();
  await expect(page.getByRole('button', { name: '답변 끝내기' })).toBeVisible();
  await expect.poll(() => liveMics(page)).toBe(1);
});

test('답변 끝내기를 연타해도 한 번만 제출된다', async ({ page }) => {
  await stubMic(page);
  await openSession(page);
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByTestId('transcript-partial')).toBeVisible();
  await page.getByRole('button', { name: '답변 끝내기' }).dblclick();
  await expect(page.getByTestId('transcript-final')).toHaveText(FIRST_ANSWER);
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('녹음 시작이 서버에서 거절되면 안내하고 마이크를 닫는다', async ({ page }) => {
  await stubMic(page);
  await openSession(page, 'ws-answer-rejected');
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByRole('alert')).toContainText('답변을 저장하지 못했어요');
  await expect.poll(() => liveMics(page)).toBe(0);
});

test('녹음기를 만들지 못하면 안내하고 마이크를 닫는다', async ({ page }) => {
  await stubMic(page);
  await page.addInitScript(() => {
    (window as unknown as { MediaRecorder: unknown }).MediaRecorder = class {
      static isTypeSupported() {
        return true;
      }
      constructor() {
        throw new DOMException('stub', 'NotSupportedError');
      }
    };
  });
  await openSession(page);
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByRole('alert')).toContainText('마이크를 사용할 수 없어요');
  await expect.poll(() => liveMics(page)).toBe(0);
});

test('새로고침하면 새로고침 전 턴부터 이어서 시작한다', async ({ page }) => {
  await stubMic(page);
  await openSession(page);
  await answerOnce(page);
  await expect(page.getByText('질문 2 / 9 · 개발팀')).toBeVisible({ timeout: 10_000 });
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByTestId('transcript-partial')).toBeVisible();

  await page.reload();
  await expect(page.getByText('질문 2 / 9 · 개발팀')).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('연결이 끊겨 답변이 저장되지 않았어요');
});

test('답변 저장 직후 새로고침해도 다음 질문으로 이어진다', async ({ page }) => {
  await stubMic(page);
  await openSession(page);
  await answerOnce(page);
  await expect(page.getByTestId('transcript-final')).toBeVisible();
  await page.reload();
  await expect(page.getByText('질문 2 / 9 · 개발팀')).toBeVisible({ timeout: 10_000 });
});

/** 녹음기 인스턴스를 window.__recorders에 모은다. 녹음 중 녹음기 오류를 흉내 내는 데 쓴다. */
async function trackRecorders(page: Page) {
  await page.addInitScript(() => {
    const Original = MediaRecorder;
    const recorders: MediaRecorder[] = [];
    (window as unknown as { __recorders: MediaRecorder[] }).__recorders = recorders;
    (window as unknown as { MediaRecorder: unknown }).MediaRecorder = class extends Original {
      constructor(stream: MediaStream, options?: MediaRecorderOptions) {
        super(stream, options);
        recorders.push(this);
      }
    };
  });
}

test('녹음기 오류가 나면 안내하고 마이크를 닫는다', async ({ page }) => {
  await stubMic(page);
  await trackRecorders(page);
  await openSession(page);
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByRole('button', { name: '답변 끝내기' })).toBeVisible();
  await page.evaluate(() =>
    (window as unknown as { __recorders: MediaRecorder[] }).__recorders
      .at(-1)!
      .dispatchEvent(new Event('error')),
  );
  await expect(page.getByRole('alert')).toContainText('마이크 연결이 끊겼어요');
  await expect.poll(() => liveMics(page)).toBe(0);
});

test('녹음기가 저절로 멈춘 뒤 답변 끝내기를 눌러도 화면이 멈추지 않는다', async ({ page }) => {
  await stubMic(page);
  await trackRecorders(page);
  await openSession(page);
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByTestId('transcript-partial')).toBeVisible();
  await page.evaluate(() =>
    (window as unknown as { __recorders: MediaRecorder[] }).__recorders.at(-1)!.stop(),
  );
  await page.getByRole('button', { name: '답변 끝내기' }).click();
  await expect(page.getByRole('alert')).toContainText('마이크 연결이 끊겼어요');
  await expect.poll(() => liveMics(page)).toBe(0);
});

test('녹음 중 복구 불가 오류가 오면 마이크와 녹음 표시를 정리한다', async ({ page }) => {
  await page.clock.install();
  await stubMic(page);
  await openSession(page);
  await page.getByRole('button', { name: '답변 시작' }).click();
  await expect(page.getByTestId('transcript-partial')).toBeVisible();
  await page.evaluate(() =>
    (window as unknown as { msw: { failWs: () => void } }).msw.failWs(),
  );

  await expect.poll(() => liveMics(page)).toBe(0);
  await expect(page.getByText(/^녹음 중/)).toHaveCount(0);
  expect(await page.evaluate(() => sessionStorage.getItem('devon.recordingAnswer'))).toBeNull();
  // 180초 자동 종료가 남아 있으면 끊김 안내가 fatal 오류 위에 한 번 더 뜬다.
  await page.clock.runFor(180_000);
  await expect(page.getByText(/연결이 끊겨 답변이 저장되지 않았어요/)).toHaveCount(0);
});
