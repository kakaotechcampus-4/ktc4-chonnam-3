import { HttpResponse, delay, http, type PathParams } from 'msw';

import type {
  ContractReport,
  CreateInterviewBody,
  CreateInterviewResult,
  GeneratingResponse,
  InterviewDetail,
} from '@/types/contract';
import {
  createInterview,
  getInterview,
  getRun,
  hasActiveInterviewForRun,
  interviewCurrentTurn,
  interviewRemainingSeconds,
  interviewStatus,
  interviewTurns,
  reportReady,
} from '../db';
import { candidatePages } from '../fixtures/analysis';
import {
  TOTAL_TURNS,
  completedTurns,
  reportFeedbacks,
  reportScores,
  reportTotalScore,
} from '../fixtures/interview';
import { errorResponse, path, type Res } from '../http';

type IdParams = { id: string };

const MAX_REPOSITORIES = 5;

/** 선택 가능 조건: L1 분석이 succeeded인 후보만. spec/backend/features/analysis-run.md */
const selectableRepositoryIds = new Set(
  Object.values(candidatePages)
    .flat()
    .filter((card) => card.status === 'succeeded')
    .map((card) => card.repositoryId),
);

export const interviewHandlers = [
  http.post<PathParams, CreateInterviewBody, Res<CreateInterviewResult>>(
    path('/interviews'),
    async ({ request }) => {
      const body = await request.json();
      const repositoryIds = body?.repositoryIds ?? [];

      if (repositoryIds.length === 0) {
        return errorResponse(400, 'no_repository_selected', '레포지토리를 1개 이상 선택해주세요.');
      }
      if (repositoryIds.length > MAX_REPOSITORIES) {
        return errorResponse(
          400,
          'too_many_repositories',
          `레포지토리는 최대 ${MAX_REPOSITORIES}개까지 선택할 수 있어요.`,
        );
      }

      // run을 찾을 수 없으면 선택한 repo가 현재 run에 속할 수 없다.
      const run = getRun(body?.runId ?? '');
      if (!run) {
        return errorResponse(400, 'invalid_repository', '선택할 수 없는 레포지토리입니다.', {
          details: { runId: body?.runId ?? null },
        });
      }

      const invalid = repositoryIds.filter((id) => !selectableRepositoryIds.has(id));
      if (invalid.length > 0) {
        return errorResponse(400, 'invalid_repository', '선택할 수 없는 레포지토리입니다.', {
          details: { repositoryIds: invalid },
        });
      }
      if (hasActiveInterviewForRun(run.runId)) {
        return errorResponse(409, 'session_limit_exceeded', '이미 진행 중인 면접이 있어요.');
      }

      await delay(400);
      const record = createInterview(run.runId, repositoryIds);

      return HttpResponse.json<CreateInterviewResult>(
        // sessionId 유지 여부는 PENDING_FE다. 결정 전까지 FE는 이 값에 의존하지 않는다.
        { interviewId: record.interviewId, sessionId: record.sessionId },
        { status: 201 },
      );
    },
  ),

  http.get<IdParams, never, Res<InterviewDetail>>(path('/interviews/:id'), async ({ params }) => {
    const record = getInterview(String(params.id));
    if (!record) {
      return errorResponse(404, 'not_found', '면접을 찾을 수 없어요.');
    }

    await delay(150);
    return HttpResponse.json<InterviewDetail>({
      id: record.interviewId,
      sessionId: record.sessionId,
      status: interviewStatus(record),
      currentTurn: interviewCurrentTurn(record),
      totalTurns: TOTAL_TURNS,
      remainingSeconds: interviewRemainingSeconds(record),
      turns: interviewTurns(record),
    });
  }),

  /**
   * 리포트는 lazy generation이다. 첫 조회에서 생성을 시작하고 202를 준다.
   * FE는 retryAfter만큼 기다렸다 다시 조회해야 한다. spec/backend/features/report.md
   */
  http.get<IdParams, never, Res<ContractReport | GeneratingResponse>>(
    path('/interviews/:id/report'),
    async ({ params }) => {
      const record = getInterview(String(params.id));
      if (!record) {
        return errorResponse(404, 'not_found', '면접을 찾을 수 없어요.');
      }
      if (interviewStatus(record) !== 'completed') {
        return errorResponse(409, 'report_unavailable', '아직 리포트를 만들 수 없는 면접이에요.');
      }
      if (!reportReady(record)) {
        return HttpResponse.json<GeneratingResponse>(
          { status: 'generating', retryAfter: 3 },
          { status: 202 },
        );
      }

      await delay(200);
      return HttpResponse.json<ContractReport>({
        interviewId: record.interviewId,
        totalScore: reportTotalScore,
        scores: reportScores,
        agentFeedbacks: reportFeedbacks,
        turns: completedTurns,
      });
    },
  ),

  http.post<IdParams, never, Res<CreateInterviewResult>>(
    path('/interviews/:id/retry'),
    async ({ params }) => {
      const record = getInterview(String(params.id));
      if (!record) {
        return errorResponse(404, 'not_found', '면접을 찾을 수 없어요.');
      }

      const status = interviewStatus(record);
      if (status !== 'completed' && status !== 'abandoned') {
        return errorResponse(409, 'original_not_completed', '끝난 면접만 다시 볼 수 있어요.');
      }
      if (hasActiveInterviewForRun(record.runId)) {
        return errorResponse(409, 'session_limit_exceeded', '이미 진행 중인 면접이 있어요.');
      }

      await delay(400);
      const next = createInterview(record.runId, record.repositoryIds);

      return HttpResponse.json<CreateInterviewResult>(
        { interviewId: next.interviewId, sessionId: next.sessionId },
        { status: 201 },
      );
    },
  ),
];
