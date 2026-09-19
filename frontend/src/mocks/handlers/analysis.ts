import { HttpResponse, delay, http, type PathParams } from 'msw';

import type {
  AnalysisResultResponse,
  AnalysisRunResponse,
  CandidatesAnalyzingResponse,
  CandidatesResponse,
  CreateAnalysisRunRequest,
  CreateAnalysisRunResponse,
  SseCompletedEvent,
  SseFailedEvent,
  SseStepEvent,
  StepKey,
  StepStatus,
} from '@/types/api';
import {
  candidatePageReady,
  createRun,
  getRun,
  runEstimatedSeconds,
  runFailureReason,
  runProgress,
  runStatus,
  runSteps,
} from '../db';
import {
  candidatePages,
  matchedRepoCount,
  mentionedRepoCount,
  resultRepositories,
} from '../fixtures/analysis';
import { jdCompanyName, jdPosition, jdRequirements } from '../fixtures/jd';
import { errorResponse, path, type Res } from '../http';
import { BASE } from '@/shared/api';

/** 계약에 SSE payload 정의가 없어 api-spec.md #13 을 따른다. progress 는 아래 주석 참고. */
type SseEvent = SseStepEvent | SseCompletedEvent | SseFailedEvent;

type RunParams = { runId: string };

/** Sprint 1은 Wanted 공고만 지원한다. spec/backend/features/analysis-run.md */
const SUPPORTED_HOST = 'wanted.co.kr';

const SSE_TICK_MS = 300;

export const analysisHandlers = [
  http.post<PathParams, CreateAnalysisRunRequest, Res<CreateAnalysisRunResponse>>(
    path('/analysis-runs'),
    async ({ request }) => {
      /**
       * Sprint 1 계약에서 이 엔드포인트는 multipart가 아니라 JSON이다.
       * 파일은 POST /documents/preview로 먼저 올리고 documentId만 넘긴다.
       * 아직 multipart로 부르는 코드가 있으면 여기서 바로 드러나야 한다.
       */
      if (!request.headers.get('Content-Type')?.includes('application/json')) {
        return errorResponse(
          501,
          'internal_error',
          'POST /analysis-runs는 JSON { postingUrl, documentId } 를 받습니다. 파일은 POST /documents/preview로 먼저 올리세요.',
        );
      }

      const body = await request.json();

      if (!body?.postingUrl?.trim()) {
        return errorResponse(400, 'posting_url_required', '채용 공고 URL을 입력해주세요.');
      }
      if (!body.postingUrl.includes(SUPPORTED_HOST)) {
        return errorResponse(400, 'unsupported_site', '지금은 원티드 공고만 분석할 수 있어요.');
      }

      await delay(400);
      const { run, reused } = createRun(body.postingUrl, body.documentId ?? null);

      /**
       * 같은 공고로 진행 중인 run이 이미 있으면 409다. 계약의 CreateAnalysisRunResponse에는
       * reused 같은 필드가 없어서, 재사용을 본문 필드가 아니라 상태코드로 알린다.
       * 화면은 details.runId 로 진행 중인 run 화면으로 이동한다. api-spec.md #11.
       */
      if (reused) {
        return errorResponse(409, 'run_in_progress', '이미 분석 중인 공고예요.', {
          details: { runId: run.runId },
        });
      }

      return HttpResponse.json<CreateAnalysisRunResponse>(
        { runId: run.runId },
        { status: 202, headers: { Location: `${BASE}/analysis-runs/${run.runId}` } },
      );
    },
  ),

  http.get<RunParams, never, Res<AnalysisRunResponse>>(
    path('/analysis-runs/:runId'),
    async ({ params }) => {
      const run = getRun(String(params.runId));
      if (!run) {
        return errorResponse(410, 'run_expired', '분석 요청을 찾을 수 없어요.');
      }

      await delay(120);
      return HttpResponse.json<AnalysisRunResponse>({
        runId: run.runId,
        status: runStatus(run),
        steps: runSteps(run),
        progress: runProgress(run),
        failureReason: runFailureReason(run),
        estimatedSeconds: runEstimatedSeconds(run),
      });
    },
  ),

  /**
   * SSE 진행 이벤트.
   *
   * openapi.yaml은 text/event-stream 이라는 것만 정의한다. 아래 payload 형태는
   * frontend/docs/api-spec.md #13 을 따르며 BE 확인이 필요하다(D7).
   * 상태는 db의 경과 시간에서 읽으므로 같은 run을 폴링해도 같은 값이 나온다.
   *
   * progress 이벤트는 내보내지 않는다. 계약에는 있으나 읽는 화면이 프로젝트에 하나도 없어
   * 계약 쪽을 정리하기로 했다(PR #28 리뷰, 커밋 e25d68e). 필요해지면 여기에 추가한다.
   *
   * skipped 도 한 번 전송한다. 보내지 않으면 SSE만 구독한 화면이 그 단계를 pending 으로
   * 남겨 GET /analysis-runs/{runId} 결과와 어긋난다. api-spec.md #13.
   */
  http.get<RunParams, never, undefined>(path('/analysis-runs/:runId/events'), ({ params }) => {
    const run = getRun(String(params.runId));
    if (!run) {
      return errorResponse(410, 'run_expired', '분석 요청을 찾을 수 없어요.');
    }

    const encoder = new TextEncoder();
    const sent = new Map<StepKey, StepStatus>();
    let timer: ReturnType<typeof setInterval> | undefined;
    let closed = false;

    const stream = new ReadableStream({
      start(controller) {
        const send = (event: SseEvent) => {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
        };

        const stop = () => {
          if (closed) return;
          closed = true;
          if (timer) clearInterval(timer);
          controller.close();
        };

        const tick = () => {
          if (closed) return;
          const now = Date.now();

          for (const step of runSteps(run, now)) {
            if (step.status === 'pending') continue;
            if (sent.get(step.key) === step.status) continue;
            sent.set(step.key, step.status);
            send({ type: 'step', key: step.key, status: step.status });
          }

          const status = runStatus(run, now);
          if (status === 'completed') {
            send({ type: 'completed' });
            stop();
          } else if (status === 'failed') {
            send({ type: 'failed', reason: runFailureReason(run, now) ?? 'internal_error' });
            stop();
          }
        };

        tick();
        if (!closed) timer = setInterval(tick, SSE_TICK_MS);
      },
      cancel() {
        closed = true;
        if (timer) clearInterval(timer);
      },
    });

    return new HttpResponse(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
    });
  }),

  http.get<RunParams, never, Res<AnalysisResultResponse>>(
    path('/analysis-runs/:runId/result'),
    async ({ params }) => {
      const run = getRun(String(params.runId));
      if (!run) {
        return errorResponse(410, 'run_expired', '분석 요청을 찾을 수 없어요.');
      }
      if (runStatus(run) === 'running') {
        return errorResponse(409, 'not_ready', '아직 분석이 끝나지 않았어요.', { retryAfter: 3 });
      }

      await delay(200);
      return HttpResponse.json<AnalysisResultResponse>({
        runId: run.runId,
        position: jdPosition,
        companyName: jdCompanyName,
        jdRequirements,
        mentionedRepoCount,
        matchedRepoCount,
        repositories: resultRepositories,
      });
    },
  ),

  /**
   * 후보 더 보기. 미분석 page는 202 analyzing을 주고, 재요청하면 200으로 바뀐다.
   * page 1은 result와 같은 첫 batch이므로 바로 200이다.
   */
  http.get<RunParams, never, Res<CandidatesResponse | CandidatesAnalyzingResponse>>(
    path('/analysis-runs/:runId/candidates'),
    async ({ params, request }) => {
      const run = getRun(String(params.runId));
      if (!run) {
        return errorResponse(410, 'run_expired', '분석 요청을 찾을 수 없어요.');
      }

      // 계약에서 page 는 required 다. 빠뜨린 호출을 기본값으로 덮어 주면 드러나지 않는다.
      const raw = new URL(request.url).searchParams.get('page');
      const page = Number(raw);
      if (raw === null || !Number.isInteger(page) || page < 1) {
        return errorResponse(400, 'internal_error', 'page는 1 이상의 정수여야 하며 필수입니다.');
      }

      const analyzing = HttpResponse.json<CandidatesAnalyzingResponse>(
        { status: 'analyzing', retryAfter: 3 },
        { status: 202 },
      );

      if (runStatus(run) === 'running') return analyzing;
      if (page > 1 && !candidatePageReady(run.runId, page)) return analyzing;

      await delay(200);
      return HttpResponse.json<CandidatesResponse>({
        repositories: candidatePages[page] ?? [],
      });
    },
  ),
];
