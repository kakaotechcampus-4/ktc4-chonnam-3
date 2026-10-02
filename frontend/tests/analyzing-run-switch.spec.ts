import { expect, test } from '@playwright/test';

// 같은 Analyzing 화면에서 runId만 A → B로 바뀌면(클라이언트 라우팅) 컴포넌트가 재사용된다.
// 이때 B의 SSE를 새로 열고, A의 SSE 단계 상태가 B 화면에 남지 않아야 한다.
test('runId가 바뀌면 새 SSE를 열고 이전 run의 단계 상태를 비운다', async ({ page }) => {
  await page.addInitScript(() => {
    type Fake = { url: string; closed: boolean; onmessage: ((e: { data: string }) => void) | null };
    const sources: Fake[] = [];
    (window as unknown as { __sources: Fake[] }).__sources = sources;
    (window as unknown as { EventSource: unknown }).EventSource = class {
      url: string;
      closed = false;
      onmessage: Fake['onmessage'] = null;
      onerror: (() => void) | null = null;
      constructor(url: string) {
        this.url = url;
        sources.push(this);
      }
      close() {
        this.closed = true;
      }
    };

    // REST 스냅샷은 두 run 모두 전 단계 pending인 running으로 고정한다.
    const originalFetch = window.fetch;
    window.fetch = async (input, options) => {
      const match = String(input).match(/\/api\/analysis-runs\/(run-[ab])$/);
      if (!match) return originalFetch(input, options);
      return new Response(
        JSON.stringify({
          runId: match[1],
          status: 'running',
          steps: [],
          progress: 0,
          failureReason: null,
          estimatedSeconds: 60,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    };
  });

  const doneMarks = page.locator('li', { hasText: '공고 문서 확인' }).getByText('✓');
  const sources = () =>
    page.evaluate(() =>
      (window as unknown as { __sources: { url: string; closed: boolean }[] }).__sources.map(
        ({ url, closed }) => ({ url, closed }),
      ),
    );
  const emit = (index: number, data: object) =>
    page.evaluate(
      ([i, payload]) =>
        (
          window as unknown as { __sources: { onmessage: (e: { data: string }) => void }[] }
        ).__sources[i as number].onmessage({ data: JSON.stringify(payload) }),
      [index, data] as const,
    );

  await page.goto('/interview/analyzing/run-a');
  await expect.poll(sources).toEqual([{ url: '/api/analysis-runs/run-a/events', closed: false }]);

  await emit(0, { type: 'step', key: 'doc_extract', status: 'completed' });
  await expect(doneMarks).toBeVisible();

  // 클라이언트 라우팅으로 같은 화면의 runId만 B로 바꾼다.
  await page.evaluate(() => {
    window.history.pushState({}, '', '/interview/analyzing/run-b');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/interview\/analyzing\/run-b$/);

  await expect.poll(sources).toEqual([
    { url: '/api/analysis-runs/run-a/events', closed: true },
    { url: '/api/analysis-runs/run-b/events', closed: false },
  ]);
  await expect(doneMarks).toHaveCount(0);

  await emit(1, { type: 'step', key: 'doc_extract', status: 'completed' });
  await expect(doneMarks).toBeVisible();
});
