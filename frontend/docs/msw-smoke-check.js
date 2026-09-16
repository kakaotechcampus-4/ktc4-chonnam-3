/**
 * MSW 핸들러 점검 스크립트.
 *
 * 사용법: `npm run dev` 후 브라우저에서 앱을 열고, devtools 콘솔에 이 파일 전체를 붙여넣는다.
 * 등록된 핸들러의 정상 흐름과 상태 전이를 순서대로 호출하고 PASS/FAIL 표를 출력한다.
 * 약 15초 걸린다 (분석 run·면접 준비·리포트 생성 대기 포함).
 *
 * mock 상태는 메모리에 남으므로 페이지당 한 번만 유효하다. 다시 돌리려면 새로고침한다.
 *
 * 테스트 러너가 아니다. 도구를 정하기 전까지 쓰는 수동 검증 절차다.
 */
(async () => {
  const rows = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const call = async (method, url, body) => {
    const init = { method };
    if (body instanceof FormData) {
      init.body = body;
    } else if (body) {
      init.headers = { 'Content-Type': 'application/json' };
      init.body = JSON.stringify(body);
    }
    const res = await fetch(`/api${url}`, init);
    let data = null;
    try {
      data = await res.json();
    } catch {
      /* 204 또는 비 JSON */
    }
    return { status: res.status, data };
  };

  const check = (검사, 기대, 실제) =>
    rows.push({
      검사,
      기대: String(기대),
      실제: String(실제),
      결과: String(기대) === String(실제) ? 'PASS' : 'FAIL',
    });

  const SEED_INTERVIEW = 'a3d51c20-1001-4c00-9a00-000000000001';

  // 워커가 붙어 있는지 먼저 확인한다. 여기서 실패하면 아래는 전부 무의미하다.
  if (!navigator.serviceWorker.controller) {
    console.error('[check] 서비스 워커가 페이지를 제어하고 있지 않습니다. 새로고침 후 다시 실행하세요.');
    return;
  }

  /**
   * mock db는 페이지 수명 동안 유지된다.
   * 같은 페이지에서 두 번 돌리면 리포트가 이미 생성돼 있거나 재면접이 활성 상태라
   * 정상 동작인데도 FAIL로 보인다. 혼동을 막기 위해 여기서 끊는다.
   */
  if (window.__mswSmokeRan) {
    console.error('[check] 이 페이지에서 이미 실행했습니다. 새로고침 후 다시 실행하세요.');
    return;
  }
  window.__mswSmokeRan = true;

  // 사용자 (아직 계약 이관 전 엔드포인트)
  check('GET /me', 200, (await call('GET', '/me')).status);
  check('GET /me/home', 'completed', (await call('GET', '/me/home')).data.analysisStatus);
  check(
    '  └ 시나리오 전환',
    'no_repository',
    (await call('GET', '/me/home?scenario=no_repository')).data.analysisStatus,
  );
  check('GET /me/interviews', 200, (await call('GET', '/me/interviews?page=1&size=20')).status);
  check('POST /auth/logout', 204, (await call('POST', '/auth/logout')).status);

  // 문서 preview
  const pdf = new FormData();
  pdf.append('file', new File(['x'], 'portfolio.pdf', { type: 'application/pdf' }));
  const doc = await call('POST', '/documents/preview', pdf);
  check('POST /documents/preview', 200, doc.status);
  const hwp = new FormData();
  hwp.append('file', new File(['x'], 'a.hwp'));
  check(
    '  └ .hwp 거부',
    'unsupported_document_type',
    (await call('POST', '/documents/preview', hwp)).data.error.reason,
  );

  // 분석 run
  const posting = { postingUrl: 'https://www.wanted.co.kr/wd/1', documentId: doc.data.documentId };
  const run = await call('POST', '/analysis-runs', posting);
  check('POST /analysis-runs', 202, run.status);
  const runId = run.data.runId;
  check('  └ 중복 요청 재사용', true, (await call('POST', '/analysis-runs', posting)).data.reused);
  check(
    '  └ 원티드 외 URL',
    'unsupported_site',
    (await call('POST', '/analysis-runs', { postingUrl: 'https://saramin.co.kr/x' })).data.error
      .reason,
  );
  check('GET /analysis-runs/{id}', 'running', (await call('GET', `/analysis-runs/${runId}`)).data.status);
  check(
    'GET /result (완료 전)',
    'not_ready',
    (await call('GET', `/analysis-runs/${runId}/result`)).data.error.reason,
  );

  // SSE
  const sse = await new Promise((resolve) => {
    const es = new EventSource(`/api/analysis-runs/${runId}/events`);
    const got = [];
    es.onmessage = (e) => {
      const d = JSON.parse(e.data);
      got.push(d);
      if (d.type === 'completed') {
        es.close();
        resolve(got);
      }
    };
    setTimeout(() => {
      es.close();
      resolve(got);
    }, 15000);
  });
  check('SSE /events 이벤트 수', 15, sse.length);
  check('  └ 마지막 이벤트', 'completed', sse.at(-1).type);

  // 결과·후보 page
  const result = await call('GET', `/analysis-runs/${runId}/result`);
  check('GET /result (완료 후)', 200, result.status);
  check('  └ analyzed/failed', '5/1', `${result.data.analyzedCount}/${result.data.failedCount}`);
  check(
    'GET /candidates?page=2 (1차)',
    202,
    (await call('GET', `/analysis-runs/${runId}/candidates?page=2`)).status,
  );
  await sleep(2600);
  check(
    'GET /candidates?page=2 (2차)',
    200,
    (await call('GET', `/analysis-runs/${runId}/candidates?page=2`)).status,
  );

  // 면접
  const repositoryIds = result.data.repositories
    .filter((r) => r.status === 'succeeded')
    .slice(0, 2)
    .map((r) => r.repositoryId);
  check(
    'POST /interviews repo 0개',
    'no_repository_selected',
    (await call('POST', '/interviews', { runId, repositoryIds: [] })).data.error.reason,
  );
  const iv = await call('POST', '/interviews', { runId, repositoryIds });
  check('POST /interviews', 201, iv.status);
  const ivId = iv.data.interviewId;
  check(
    '  └ 중복 생성',
    'session_limit_exceeded',
    (await call('POST', '/interviews', { runId, repositoryIds })).data.error.reason,
  );
  check('GET /interviews/{id} 준비중', 'preparing', (await call('GET', `/interviews/${ivId}`)).data.status);
  await sleep(3600);
  const ready = await call('GET', `/interviews/${ivId}`);
  check('GET /interviews/{id} 준비완료', 'in_progress', ready.data.status);
  check('  └ 1턴 페르소나', 'hr_manager', ready.data.turns[0].persona);
  check(
    'GET /report (진행중 면접)',
    'report_unavailable',
    (await call('GET', `/interviews/${ivId}/report`)).data.error.reason,
  );

  // 리포트 lazy generation (seed 면접)
  check('GET /report (1차)', 202, (await call('GET', `/interviews/${SEED_INTERVIEW}/report`)).status);
  await sleep(3100);
  const report = await call('GET', `/interviews/${SEED_INTERVIEW}/report`);
  check('GET /report (2차)', 200, report.status);
  check(
    '  └ 점수/피드백/턴',
    '6/3/9',
    `${report.data.scores.length}/${report.data.agentFeedbacks.length}/${report.data.turns.length}`,
  );
  check('POST /retry', 201, (await call('POST', `/interviews/${SEED_INTERVIEW}/retry`)).status);
  check('GET /interviews/없는id', 404, (await call('GET', '/interviews/nope')).status);
  check('미등록 /api 경로', 501, (await call('GET', '/no-such-endpoint')).status);

  console.table(rows);
  const failed = rows.filter((r) => r.결과 === 'FAIL');
  console.log(`전체 ${rows.length} · PASS ${rows.length - failed.length} · FAIL ${failed.length}`);
  if (failed.length) console.error('실패 항목', failed);
})();
