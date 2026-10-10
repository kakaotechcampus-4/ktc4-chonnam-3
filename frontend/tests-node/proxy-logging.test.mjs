import assert from 'node:assert/strict';
import { once } from 'node:events';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { createServer } from 'vite';

test('OAuth 프록시 전달과 오류 로그의 민감정보 제거', { timeout: 15_000 }, async (t) => {
  const root = fileURLToPath(new URL('../', import.meta.url));
  const code = 'PRIVATE_OAUTH_CODE';
  const state = 'PRIVATE_OAUTH_STATE';
  const routes = ['/auth/github/callback', '/api/auth/github/callback'];
  const backend = http.createServer((req, res) => {
    res.writeHead(302, {
      Location: '/login?error=invalid_state',
      'Set-Cookie': 'audit=ok; HttpOnly; Path=/',
    });
    res.end(JSON.stringify({ url: req.url, cookie: req.headers.cookie }));
  });
  backend.listen(0, '127.0.0.1');
  await once(backend, 'listening');
  t.after(() => new Promise((resolve) => backend.close(resolve)));
  const target = `http://127.0.0.1:${backend.address().port}`;
  const vite = await createServer({
    root,
    configFile: fileURLToPath(new URL('../vite.config.ts', import.meta.url)),
    server: {
      middlewareMode: true,
      hmr: false,
      proxy: { '/api': { target }, '/auth/github': { target } },
    },
  });
  t.after(() => vite.close());
  const web = http.createServer(vite.middlewares);
  web.listen(0, '127.0.0.1');
  await once(web, 'listening');
  t.after(() => new Promise((resolve) => web.close(resolve)));
  const origin = `http://127.0.0.1:${web.address().port}`;

  await t.test('정상 callback의 쿼리·쿠키·리다이렉트를 보존한다', async () => {
    for (const route of routes) {
      const response = await fetch(`${origin}${route}?code=${code}&state=${state}`, {
        redirect: 'manual',
        headers: { Cookie: 'oauthState=PRIVATE_COOKIE' },
      });
      assert.equal(response.status, 302);
      assert.equal(response.headers.get('location'), '/login?error=invalid_state');
      assert.equal(response.headers.get('set-cookie'), 'audit=ok; HttpOnly; Path=/');
      assert.deepEqual(await response.json(), {
        url: `/api/auth/github/callback?code=${code}&state=${state}`,
        cookie: 'oauthState=PRIVATE_COOKIE',
      });
    }
  });

  const messages = [];
  const originalError = console.error;
  console.error = (...args) => messages.push(args.join(' '));
  t.after(() => {
    console.error = originalError;
  });
  await t.test('일반 오류와 Vite의 오류 기록 여부를 보존한다', () => {
    const error = new Error('build failure');
    vite.config.logger.error('일반 빌드 오류', { error });
    assert.equal(messages.at(-1), '일반 빌드 오류');
    assert.equal(vite.config.logger.hasErrorLogged(error), true);
  });

  await new Promise((resolve) => backend.close(resolve));
  messages.length = 0;
  await t.test('upstream 연결 실패는 502와 고정 진단만 남긴다', async () => {
    for (const route of routes) {
      const response = await fetch(`${origin}${route}?code=${code}&state=${state}`);
      assert.equal(response.status, 502);
      await response.text();
    }
    assert.equal(messages.length, routes.length);
    assert.doesNotMatch(messages.join('\n'), /PRIVATE_OAUTH_CODE|PRIVATE_OAUTH_STATE/);
    assert.ok(
      messages.every((message) => message.includes('API 프록시 요청을 전달하지 못했습니다.')),
    );
  });
});
