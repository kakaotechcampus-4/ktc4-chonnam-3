/**
 * MSW 핸들러 점검 스크립트.
 *
 * 사용법: `npm run dev` 후 브라우저에서 앱을 열고, devtools 콘솔에 이 파일 전체를 붙여넣는다.
 * 등록된 핸들러의 정상 흐름과 상태 전이를 순서대로 호출하고 PASS/FAIL 표를 출력한다.
 * 약 15초 걸린다 (분석 run·면접 준비·리포트 생성 대기 포함).
 *
 * mock 상태는 메모리에 남으므로 페이지당 한 번만 유효하다. 다시 돌리려면 새로고침한다.
 *
 * 기준 계약은 `spec/shared/contracts/openapi.yaml` 이다.
 * 응답 필드는 required 집합을 그대로 비교하므로, 계약이 바뀌면 이 스크립트도 함께 고쳐야 한다.
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

  /** 응답 본문의 키 집합이 계약의 required 집합과 정확히 같은지 본다. */
  const checkKeys = (검사, 기대키, 본문) =>
    check(검사, 기대키.slice().sort().join(','), Object.keys(본문 ?? {}).sort().join(','));

  const SEED_FAILED_RUN = '5c7b9e10-0000-4000-8000-00000000bbbb';
  const SEED_INTERVIEW = 'a3d51c20-1001-4c00-9a00-000000000001';
  const SEED_PREPARING_FAILED = 'a3d51c20-1009-4c00-9a00-000000000009';

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

  // 사용자 -----------------------------------------------------------------
  check('GET /me', 200, (await call('GET', '/me')).status);
  checkKeys(
    'GET /me/profile',
    ['name', 'avatarUrl', 'loginId', 'joinedAt', 'desiredPosition', 'github', 'interviewSummary'],
    (await call('GET', '/me/profile')).data,
  );
  check('GET /me/home', 'completed', (await call('GET', '/me/home')).data.analysisStatus);
  check(
    '  └ 시나리오 전환',
    'no_repository',
    (await call('GET', '/me/home?scenario=no_repository')).data.analysisStatus,
  );
  check('GET /me/interviews', 200, (await call('GET', '/me/interviews?page=1&size=20')).status);
  check('POST /auth/refresh', 204, (await call('POST', '/auth/refresh')).status);
  check('POST /auth/logout', 204, (await call('POST', '/auth/logout')).status);

  // 문서 preview ------------------------------------------------------------
  const pdf = new FormData();
  pdf.append('file', new File(['x'], 'portfolio.pdf', { type: 'application/pdf' }));
  const doc = await call('POST', '/documents/preview', pdf);
  checkKeys('POST /documents/preview', ['documentId', 'extractStatus'], doc.data);
  check('  └ extractStatus', 'succeeded', doc.data.extractStatus);
  const failDoc = new FormData();
  failDoc.append('file', new File(['x'], 'fail-portfolio.pdf', { type: 'application/pdf' }));
  check(
    '  └ 실패 문서',
    'failed',
    (await call('POST', '/documents/preview', failDoc)).data.extractStatus,
  );
  const hwp = new FormData();
  hwp.append('file', new File(['x'], 'a.hwp'));
  check(
    '  └ .hwp 거부',
    'unsupported_document_type',
    (await call('POST', '/documents/preview', hwp)).data.error.reason,
  );

  // 분석 run ----------------------------------------------------------------
  const posting = { postingUrl: 'https://www.wanted.co.kr/wd/1', documentId: doc.data.documentId };
  const run = await call('POST', '/analysis-runs', posting);
  check('POST /analysis-runs', 202, run.status);
  checkKeys('  └ 응답 필드', ['runId'], run.data);
  const runId = run.data.runId;
  const dup = await call('POST', '/analysis-runs', posting);
  check('  └ 중복 요청 409', 'run_in_progress', dup.data.error.reason);
  check('  └ 중복 응답의 runId', runId, dup.data.error.details.runId);
  check(
    '  └ 원티드 외 URL',
    'unsupported_site',
    (await call('POST', '/analysis-runs', { postingUrl: 'https://saramin.co.kr/x' })).data.error
      .reason,
  );

  const runState = await call('GET', `/analysis-runs/${runId}`);
  checkKeys(
    'GET /analysis-runs/{id}',
    ['runId', 'status', 'steps', 'progress', 'failureReason', 'estimatedSeconds'],
    runState.data,
  );
  check('  └ status', 'running', runState.data.status);
  check('  └ step 7개', 7, runState.data.steps.length);
  check(
    'GET /result (완료 전)',
    'not_ready',
    (await call('GET', `/analysis-runs/${runId}/result`)).data.error.reason,
  );

  // documentId 없는 run 은 doc_extract 를 skipped 로 보고한다.
  const noDocRun = await call('POST', '/analysis-runs', {
    postingUrl: 'https://www.wanted.co.kr/wd/2',
  });
  const noDocState = await call('GET', `/analysis-runs/${noDocRun.data.runId}`);
  check(
    '  └ documentId 없으면 skipped',
    'skipped',
    noDocState.data.steps.find((s) => s.key === 'doc_extract').status,
  );

  // 실패 run seed
  const failedRun = await call('GET', `/analysis-runs/${SEED_FAILED_RUN}`);
  check('GET /analysis-runs (실패 seed)', 'failed', failedRun.data.status);
  check('  └ failureReason', 'jd_fetch_failed', failedRun.data.failureReason);
  check(
    '  └ 실패 step',
    'failed',
    failedRun.data.steps.find((s) => s.key === 'jd_fetch').status,
  );

  // SSE ---------------------------------------------------------------------
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
  /**
   * 이벤트 개수는 구독 시점에 따라 달라진다. 이미 지나간 step의 running은 받지 못한다.
   * 그래서 개수 대신 "모든 step이 종료 상태로 도착했는지"를 본다.
   */
  const terminalByKey = new Map(
    sse.filter((e) => e.type === 'step' && e.status !== 'running').map((e) => [e.key, e.status]),
  );
  check('SSE 모든 step 종료 도달', 7, terminalByKey.size);
  check('  └ 마지막 이벤트', 'completed', sse.at(-1).type);
  check('  └ 완료 상태값', 'completed', terminalByKey.get('match_score'));
  check('  └ succeeded 미사용', 0, sse.filter((e) => e.status === 'succeeded').length);
  check('  └ progress 이벤트 없음', 0, sse.filter((e) => e.type === 'progress').length);

  // 결과·후보 page ------------------------------------------------------------
  const result = await call('GET', `/analysis-runs/${runId}/result`);
  checkKeys(
    'GET /result (완료 후)',
    [
      'runId',
      'position',
      'companyName',
      'jdRequirements',
      'mentionedRepoCount',
      'matchedRepoCount',
      'repositories',
    ],
    result.data,
  );
  check('  └ jdRequirements', true, result.data.jdRequirements.length > 0);
  // 카드가 가리키는 요구사항 id가 모두 실제로 존재해야 화면의 매칭 표시가 비지 않는다.
  const reqIds = new Set(result.data.jdRequirements.map((r) => r.id));
  check(
    '  └ 고아 요구사항 참조',
    0,
    result.data.repositories.flatMap((r) => r.matchedRequirementIds).filter((id) => !reqIds.has(id))
      .length,
  );
  check('  └ 카드 식별자', true, 'id' in result.data.repositories[0]);

  check(
    'GET /candidates (page 누락)',
    400,
    (await call('GET', `/analysis-runs/${runId}/candidates`)).status,
  );
  check(
    'GET /candidates?page=2 (1차)',
    202,
    (await call('GET', `/analysis-runs/${runId}/candidates?page=2`)).status,
  );
  await sleep(2600);
  const page2 = await call('GET', `/analysis-runs/${runId}/candidates?page=2`);
  check('GET /candidates?page=2 (2차)', 200, page2.status);
  checkKeys('  └ 응답 필드', ['repositories'], page2.data);

  // 면접 ---------------------------------------------------------------------
  const repositoryIds = result.data.repositories
    .filter((r) => r.status === 'succeeded')
    .slice(0, 2)
    .map((r) => r.id);
  check(
    'POST /interviews repo 0개',
    'no_repository_selected',
    (await call('POST', '/interviews', { runId, repositoryIds: [] })).data.error.reason,
  );
  const iv = await call('POST', '/interviews', { runId, repositoryIds });
  check('POST /interviews', 201, iv.status);
  checkKeys('  └ 응답 필드', ['sessionId', 'interviewId'], iv.data);
  const ivId = iv.data.interviewId;
  check(
    '  └ 중복 생성',
    'session_limit_exceeded',
    (await call('POST', '/interviews', { runId, repositoryIds })).data.error.reason,
  );
  check('GET /interviews/{id} 준비중', 'preparing', (await call('GET', `/interviews/${ivId}`)).data.status);
  await sleep(3600);
  const ready = await call('GET', `/interviews/${ivId}`);
  checkKeys(
    'GET /interviews/{id} 준비완료',
    [
      'id',
      'sessionId',
      'runId',
      'status',
      'answerMode',
      'position',
      'companyName',
      'repositoryNames',
      'currentTurn',
      'totalTurns',
      'remainingSeconds',
      'turns',
      'lastError',
    ],
    ready.data,
  );
  check('  └ status', 'in_progress', ready.data.status);
  check('  └ 1턴 페르소나', 'hr_manager', ready.data.turns[0].persona);
  check('  └ repositoryNames', 2, ready.data.repositoryNames.length);
  check('  └ lastError', 'null', String(ready.data.lastError));

  const prepFailed = await call('GET', `/interviews/${SEED_PREPARING_FAILED}`);
  check('GET /interviews (준비실패 seed)', 'preparing_failed', prepFailed.data.status);
  check('  └ lastError.step', 'compose_question', prepFailed.data.lastError.step);

  check(
    'GET /report (진행중 면접)',
    'report_unavailable',
    (await call('GET', `/interviews/${ivId}/report`)).data.error.reason,
  );

  // 리포트 lazy generation (seed 면접) -------------------------------------------
  check('GET /report (1차)', 202, (await call('GET', `/interviews/${SEED_INTERVIEW}/report`)).status);
  await sleep(3100);
  const report = await call('GET', `/interviews/${SEED_INTERVIEW}/report`);
  checkKeys(
    'GET /report (2차)',
    [
      'interviewId',
      'position',
      'positionLabel',
      'totalScore',
      'headline',
      'summary',
      'scores',
      'agentFeedbacks',
      'coverage',
      'turns',
      'repositoryNames',
      'completedAt',
    ],
    report.data,
  );
  check(
    '  └ 점수/피드백/턴',
    '6/3/9',
    `${report.data.scores.length}/${report.data.agentFeedbacks.length}/${report.data.turns.length}`,
  );
  check('  └ disagreementSubmitted', false, report.data.agentFeedbacks[0].disagreementSubmitted);
  check(
    'POST /feedback-disagreements',
    204,
    (await call('POST', `/interviews/${SEED_INTERVIEW}/feedback-disagreements`, {
      persona: 'tech_lead',
      reasonType: 'overly_harsh',
    })).status,
  );
  check('POST /retry', 201, (await call('POST', `/interviews/${SEED_INTERVIEW}/retry`)).status);
  check('GET /interviews/없는id', 404, (await call('GET', '/interviews/nope')).status);
  check('GET /analysis-runs/없는id', 410, (await call('GET', `/analysis-runs/nope`)).status);
  check('미등록 /api 경로', 501, (await call('GET', '/no-such-endpoint')).status);

  console.table(rows);
  const failed = rows.filter((r) => r.결과 === 'FAIL');
  console.log(`전체 ${rows.length} · PASS ${rows.length - failed.length} · FAIL ${failed.length}`);
  if (failed.length) console.error('실패 항목', failed);
})();
