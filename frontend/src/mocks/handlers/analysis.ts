import { HttpResponse, delay, http, type PathParams } from 'msw';

import type {
  AnalysisRunResultResponse,
  AnalysisRunStatusResponse,
  AnalyzingResponse,
  CandidatePageResponse,
  ContractSseEvent,
  ContractStepKey,
  ContractStepStatus,
  CreateAnalysisRunBody,
  CreateAnalysisRunResult,
} from '@/types/contract';
import { candidatePageReady, createRun, getRun, runProgress, runStatus, runSteps } from '../db';
import { candidatePages, failedRepositories, resultRepositories } from '../fixtures/analysis';
import { errorResponse, path, type Res } from '../http';

type RunParams = { runId: string };

/** Sprint 1은 Wanted 공고만 지원한다. spec/backend/features/analysis-run.md */
const SUPPORTED_HOST = 'wanted.co.kr';

const SSE_TICK_MS = 300;

export const analysisHandlers = [
  http.post<PathParams, CreateAnalysisRunBody, Res<CreateAnalysisRunResult>>(
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

      return HttpResponse.json<CreateAnalysisRunResult>(
        { runId: run.runId, status: runStatus(run), reused },
        { status: 202 },
      );
    },
  ),

  http.get<RunParams, never, Res<AnalysisRunStatusResponse>>(
    path('/analysis-runs/:runId'),
    async ({ params }) => {
      const run = getRun(String(params.runId));
      if (!run) {
        return errorResponse(404, 'not_found', '분석 요청을 찾을 수 없어요.');
      }

      await delay(120);
      return HttpResponse.json<AnalysisRunStatusResponse>({
        runId: run.runId,
        status: runStatus(run),
        progress: runProgress(run),
        steps: runSteps(run),
        failureReason: null,
      });
    },
  ),

  /**
   * SSE 진행 이벤트.
   *
   * openapi.yaml은 text/event-stream 이라는 것만 정의한다. 아래 payload 형태는
   * frontend/docs/api-spec.md의 기존 정의에 Sprint 1 enum을 반영한 것으로 BE 확인이 필요하다.
   * 상태는 db의 경과 시간에서 읽으므로 같은 run을 폴링해도 같은 값이 나온다.
   */
  http.get<RunParams, never, undefined>(path('/analysis-runs/:runId/events'), ({ params }) => {
    const run = getRun(String(params.runId));
    if (!run) {
      return errorResponse(404, 'not_found', '분석 요청을 찾을 수 없어요.');
    }

    const encoder = new TextEncoder();
    const sent = new Map<ContractStepKey, ContractStepStatus>();
    let timer: ReturnType<typeof setInterval> | undefined;
    let closed = false;

    const stream = new ReadableStream({
      start(controller) {
        const send = (event: ContractSseEvent) => {
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

          if (runStatus(run, now) === 'completed') {
            send({ type: 'completed' });
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

  http.get<RunParams, never, Res<AnalysisRunResultResponse>>(
    path('/analysis-runs/:runId/result'),
    async ({ params }) => {
      const run = getRun(String(params.runId));
      if (!run) {
        return errorResponse(404, 'not_found', '분석 요청을 찾을 수 없어요.');
      }
      if (runStatus(run) !== 'completed') {
        return errorResponse(409, 'not_ready', '아직 분석이 끝나지 않았어요.', { retryAfter: 3 });
      }

      await delay(200);
      return HttpResponse.json<AnalysisRunResultResponse>({
        runId: run.runId,
        status: 'completed',
        analyzedCount: resultRepositories.length - failedRepositories.length,
        failedCount: failedRepositories.length,
        failedRepositories,
        repositories: resultRepositories,
      });
    },
  ),

  /**
   * 후보 더 보기. 미분석 page는 202 analyzing을 주고, 재요청하면 200으로 바뀐다.
   * page 1은 result와 같은 첫 batch이므로 바로 200이다.
   */
  http.get<RunParams, never, Res<CandidatePageResponse | AnalyzingResponse>>(
    path('/analysis-runs/:runId/candidates'),
    async ({ params, request }) => {
      const run = getRun(String(params.runId));
      if (!run) {
        return errorResponse(404, 'not_found', '분석 요청을 찾을 수 없어요.');
      }

      const page = Number(new URL(request.url).searchParams.get('page') ?? 1);
      if (!Number.isInteger(page) || page < 1) {
        return errorResponse(400, 'internal_error', 'page는 1 이상의 정수여야 합니다.');
      }

      const analyzing = HttpResponse.json<AnalyzingResponse>(
        { status: 'analyzing', retryAfter: 3 },
        { status: 202 },
      );

      if (runStatus(run) !== 'completed') return analyzing;
      if (page > 1 && !candidatePageReady(run.runId, page)) return analyzing;

      await delay(200);
      return HttpResponse.json<CandidatePageResponse>({
        runId: run.runId,
        page,
        repositories: candidatePages[page] ?? [],
      });
    },
  ),
];
