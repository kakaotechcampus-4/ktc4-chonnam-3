/**
 * MSW 핸들러 점검 스크립트.
 *
 * 사용법: `npm run dev` 후 브라우저에서 앱을 열고, devtools 콘솔에 이 파일 전체를 붙여넣는다.
 * 등록된 핸들러의 정상 흐름·실패 케이스·WebSocket 을 순서대로 호출하고 PASS/FAIL 표를 출력한다.
 * 약 30초 걸린다 (분석 run·면접 준비·리포트 생성·WS 턴 대기 포함).
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
    check(
      검사,
      기대키.slice().sort().join(','),
      Object.keys(본문 ?? {})
        .sort()
        .join(','),
    );

  const SEED_FAILED_RUN = '5c7b9e10-0000-4000-8000-00000000bbbb';
  const SEED_INTERVIEW = 'a3d51c20-1001-4c00-9a00-000000000001';
  const SEED_PREPARING_FAILED = 'a3d51c20-1009-4c00-9a00-000000000009';
  /** WS 경로는 sessionId 로 붙는다. 위 seed 면접들의 세션 식별자. */
  const SEED_SESSION = 'sess_0000000000000001';
  const SEED_PREPARING_FAILED_SESSION = 'sess_0000000000000009';

  // 워커가 붙어 있는지 먼저 확인한다. 여기서 실패하면 아래는 전부 무의미하다.
  if (!navigator.serviceWorker.controller) {
    console.error(
      '[check] 서비스 워커가 페이지를 제어하고 있지 않습니다. 새로고침 후 다시 실행하세요.',
    );
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
  check('  └ 실패 step', 'failed', failedRun.data.steps.find((s) => s.key === 'jd_fetch').status);

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
  check(
    'GET /interviews/{id} 준비중',
    'preparing',
    (await call('GET', `/interviews/${ivId}`)).data.status,
  );
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
  check(
    'GET /report (1차)',
    202,
    (await call('GET', `/interviews/${SEED_INTERVIEW}/report`)).status,
  );
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
    (
      await call('POST', `/interviews/${SEED_INTERVIEW}/feedback-disagreements`, {
        persona: 'tech_lead',
        reasonType: 'overly_harsh',
      })
    ).status,
  );
  check('POST /retry', 201, (await call('POST', `/interviews/${SEED_INTERVIEW}/retry`)).status);
  check('GET /interviews/없는id', 404, (await call('GET', '/interviews/nope')).status);
  check('GET /analysis-runs/없는id', 410, (await call('GET', `/analysis-runs/nope`)).status);
  check('미등록 /api 경로', 501, (await call('GET', '/no-such-endpoint')).status);

  // --- 실패 케이스 (장애 주입) --------------------------------------------

  const msw = window.msw;
  if (!msw) {
    check('장애 주입 콘솔 API', '있음', '없음');
  } else {
    msw.scenario('auth-expired');
    const expired = await call('GET', '/me');
    check(
      'auth-expired',
      '401/unauthenticated',
      `${expired.status}/${expired.data?.error?.reason}`,
    );

    msw.scenario('github-token-invalid');
    const gh = await call('GET', '/me/home');
    check(
      'github-token-invalid',
      '403/github_token_invalid',
      `${gh.status}/${gh.data?.error?.reason}`,
    );

    msw.scenario('run-expired');
    check('run-expired', 410, (await call('GET', `/analysis-runs/${runId}/result`)).status);

    msw.scenario('server-error');
    check('server-error', 500, (await call('GET', '/me')).status);

    msw.scenario('offline');
    let networkFailed = false;
    try {
      await fetch('/api/me');
    } catch {
      networkFailed = true;
    }
    check('offline — 네트워크 단계 실패', true, networkFailed);

    msw.clear();
    check('규칙 해제 후 정상', 200, (await call('GET', '/me')).status);

    msw.fault({ path: '/me', status: 500, reason: 'internal_error', times: 1 });
    check('times:1 — 1회차', 500, (await call('GET', '/me')).status);
    check('  └ 2회차', 200, (await call('GET', '/me')).status);
    check('  └ 규칙 자동 삭제', 0, msw.faults().length);
  }

  // --- WebSocket (api-spec.md #18) ----------------------------------------

  const wsUrl = (sessionId) =>
    `${location.origin.replace('http', 'ws')}/api/ws/interviews/${sessionId}`;

  /** 조건이 맞거나 타임아웃까지 메시지를 모은다. */
  const collect = (sessionId, done, timeoutMs = 9000) =>
    new Promise((resolve) => {
      const socket = new WebSocket(wsUrl(sessionId));
      const got = [];
      const finish = (closed) => {
        try {
          socket.close();
        } catch {
          /* 이미 닫힘 */
        }
        resolve({ got, closed });
      };
      socket.onmessage = (event) => {
        got.push(JSON.parse(event.data));
        if (done(got)) finish(null);
      };
      socket.onclose = (event) => resolve({ got, closed: `${event.code}/${event.reason}` });
      setTimeout(() => finish('timeout'), timeoutMs);
    });

  const seen = (got, type) => got.some((m) => m.type === type);

  /**
   * 준비 실패 세션에 붙어도 서버는 오류를 되보내지 않는다.
   * 복구 경로는 GET /interviews/{id} 의 lastError 스냅샷이고, WS 연결은 prepareRetry 를 위한 것이다.
   * 되보내면 화면이 방금 지운 오류가 되살아나 재시도가 끝나도 실패 배너가 남는다(설계 문서 D14).
   */
  const failedSnapshot = await call('GET', `/interviews/${SEED_PREPARING_FAILED}`);
  check('준비 실패 스냅샷 reason', 'question_gen_timeout', failedSnapshot.data.lastError?.reason);
  check('  └ code', 'ERR_QUESTION_GEN_TIMEOUT', failedSnapshot.data.lastError?.code);
  check('  └ recoverable', true, failedSnapshot.data.lastError?.recoverable);

  const onConnect = await collect(SEED_PREPARING_FAILED_SESSION, () => false, 1200);
  check('WS 준비 실패 — 연결 시 무전송', 0, onConnect.got.length);

  /**
   * 재시도는 WS 메시지가 아니라 REST 다(0010 결정).
   * 진행 상황은 계약대로 WS 로 나오므로 소켓을 열어 둔 채 REST 를 호출한다.
   */
  const retried = await new Promise((resolve) => {
    const socket = new WebSocket(wsUrl(SEED_PREPARING_FAILED_SESSION));
    const got = [];
    const finish = () => {
      try {
        socket.close();
      } catch {
        /* 이미 닫힘 */
      }
      resolve(got);
    };
    socket.onmessage = (event) => {
      got.push(JSON.parse(event.data));
      if (seen(got, 'question')) finish();
    };
    socket.onopen = () =>
      setTimeout(
        () => void call('POST', `/interviews/${SEED_PREPARING_FAILED}/prepare/retry`),
        200,
      );
    setTimeout(finish, 6000);
  });
  check(
    'POST /prepare/retry — 복구',
    true,
    seen(retried, 'prepareCompleted') && seen(retried, 'question'),
  );
  // 성공한 3단계는 재실행하지 않는다. compose_question 만 running 으로 온다.
  check(
    '  └ 실패 단계만 재실행',
    'compose_question',
    retried
      .filter((m) => m.status === 'running')
      .map((m) => m.key)
      .join(','),
  );
  check(
    '  └ 준비 실패가 아니면 409',
    'prep_failed',
    (await call('POST', `/interviews/${SEED_INTERVIEW}/prepare/retry`)).data?.error?.reason,
  );

  /**
   * 주입한 준비 실패가 REST 스냅샷에도 남아야 한다.
   * 메시지만 보내면 새로고침 후 preparing 으로 보이고, 시간이 지나면 화면이
   * in_progress 로 보고 질문 없는 진행 화면으로 넘어간다.
   */
  const run2 = await call('POST', '/analysis-runs', {
    postingUrl: 'https://www.wanted.co.kr/wd/3',
  });
  const iv2 = await call('POST', '/interviews', {
    runId: run2.data.runId,
    repositoryIds,
  });
  if (iv2.status !== 201) {
    check('주입 준비 실패 — 면접 생성', 201, `${iv2.status}(${iv2.data?.error?.reason})`);
  } else {
    msw?.scenario('ws-prepare-failed');
    const injected = await collect(iv2.data.sessionId, (got) => seen(got, 'error'), 3000);
    const injectedError = injected.got.find((m) => m.type === 'error');
    check(
      '주입 준비 실패 — 체크리스트',
      4,
      injected.got.filter((m) => m.type === 'prepareStep').length,
    );
    check('  └ 실패 칸', 'compose_question', injected.got.find((m) => m.status === 'failed')?.key);
    check('  └ error.step', 'compose_question', injectedError?.step);
    check('  └ error.code', 'ERR_QUESTION_GEN_TIMEOUT', injectedError?.code);

    const snapshot = await call('GET', `/interviews/${iv2.data.interviewId}`);
    check('  └ REST 스냅샷 status', 'preparing_failed', snapshot.data.status);
    check('  └ REST 스냅샷 lastError.step', 'compose_question', snapshot.data.lastError?.step);

    // HTTP 전역 규칙은 WS 로 새지 않는다. 규칙이 WS 에서 소비되면 HTTP 검증이 망가진다.
    msw?.scenario('auth-expired');
    const notLeaked = await collect(iv2.data.sessionId, (got) => seen(got, 'question'), 6000);
    check(
      '전역 HTTP 규칙이 WS 로 누수되지 않음',
      0,
      notLeaked.got.filter((m) => m.type === 'error').length,
    );
    msw?.clear();
  }

  check('WS 없는 세션', '1008/not_found', (await collect('sess_없음', () => false, 2000)).closed);
  check(
    'WS 종료된 면접',
    '1008/already_ended',
    (await collect(SEED_SESSION, () => false, 2000)).closed,
  );

  /**
   * 정상 진행은 앞서 만든 면접(`iv`)의 세션으로 본다.
   * 같은 run 에 활성 면접이 하나뿐이라 새로 만들면 409 가 된다.
   */
  const sessionId = iv.data.sessionId;
  const prepared = await collect(sessionId, (got) => seen(got, 'question'));
  check('WS 준비 완료', true, seen(prepared.got, 'prepareCompleted'));
  check('  └ 질문 turn', true, (prepared.got.find((m) => m.type === 'question')?.turn ?? 0) >= 1);
  check('  └ skipped 미사용', 0, prepared.got.filter((m) => m.status === 'skipped').length);

  /** 소켓을 열고 한 번 보낸 뒤 조건이 맞을 때까지 모은다. */
  const sendAndCollect = (payload, done, timeoutMs = 6000) =>
    new Promise((resolve) => {
      const socket = new WebSocket(wsUrl(sessionId));
      const got = [];
      const finish = () => {
        try {
          socket.close();
        } catch {
          /* 이미 닫힘 */
        }
        resolve(got);
      };
      socket.onmessage = (event) => {
        got.push(JSON.parse(event.data));
        if (done(got)) finish();
      };
      socket.onopen = () => setTimeout(() => socket.send(JSON.stringify(payload)), 300);
      setTimeout(finish, timeoutMs);
    });

  const tooLong = await sendAndCollect({ type: 'answer', turn: 1, text: 'x'.repeat(2001) }, (got) =>
    seen(got, 'error'),
  );
  const tooLongError = tooLong.find((m) => m.type === 'error');
  check('WS 2000자 초과', 'answer_too_long', tooLongError?.reason);
  check('  └ code', 'ERR_ANSWER_TOO_LONG', tooLongError?.code);
  check('  └ recoverable', true, tooLongError?.recoverable);

  const answered = await sendAndCollect({ type: 'answer', turn: 1, text: '정상 답변' }, (got) =>
    seen(got, 'answerReceived'),
  );
  check('WS 답변 수신', true, seen(answered, 'answerReceived'));

  // 같은 턴을 두 번 보내면 저장이 거부된다. answerReceived 를 보내면 화면이 다음 질문을 영영 기다린다.
  const duplicated = await sendAndCollect(
    { type: 'answer', turn: 1, text: '같은 턴 재전송' },
    (got) => seen(got, 'error'),
  );
  check('WS 같은 턴 재전송', 'answer_rejected', duplicated.find((m) => m.type === 'error')?.reason);
  check(
    '  └ answerReceived 미전송',
    0,
    duplicated.filter((m) => m.type === 'answerReceived').length,
  );

  const detailAfterWs = await call('GET', `/interviews/${ivId}`);
  check(
    '  └ REST 와 정합',
    true,
    detailAfterWs.data.turns.some((t) => t.answer !== null),
  );

  if (msw) msw.clear();

  // Logout comes last: subsequent protected requests must be rejected.
  check('POST /auth/logout', 204, (await call('POST', '/auth/logout')).status);
  check('로그아웃 후 GET /me', 401, (await call('GET', '/me')).status);
  check('중복 POST /auth/logout', 204, (await call('POST', '/auth/logout')).status);
  if (msw) msw.session('authenticated');

  console.table(rows);
  const failed = rows.filter((r) => r.결과 === 'FAIL');
  console.log(`전체 ${rows.length} · PASS ${rows.length - failed.length} · FAIL ${failed.length}`);
  if (failed.length) console.error('실패 항목', failed);
})();
