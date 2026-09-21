import { HttpResponse, delay, http, type PathParams } from 'msw';

import type {
  CreateInterviewRequest,
  CreateInterviewResponse,
  FeedbackDisagreementRequest,
  InterviewDetailResponse,
  ReportGeneratingResponse,
  ReportResponse,
} from '@/types/api';
import {
  createInterview,
  getInterview,
  getRun,
  hasActiveInterviewForRun,
  interviewCurrentTurn,
  interviewLastError,
  interviewRemainingSeconds,
  interviewRepositoryNames,
  interviewStatus,
  interviewTurns,
  reportReady,
} from '../db';
import { candidatePages } from '../fixtures/analysis';
import {
  TOTAL_TURNS,
  completedTurns,
  reportCompletedAt,
  reportCoverage,
  reportFeedbacks,
  reportHeadline,
  reportPositionLabel,
  reportRepositoryNames,
  reportScores,
  reportSummary,
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
    .map((card) => card.id),
);

export const interviewHandlers = [
  http.post<PathParams, CreateInterviewRequest, Res<CreateInterviewResponse>>(
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

      return HttpResponse.json<CreateInterviewResponse>(
        // 라우트의 :id 는 interviewId, WS 경로는 sessionId 다. 계약상 둘 다 필수다.
        { interviewId: record.interviewId, sessionId: record.sessionId },
        { status: 201 },
      );
    },
  ),

  http.get<IdParams, never, Res<InterviewDetailResponse>>(
    path('/interviews/:id'),
    async ({ params }) => {
      const record = getInterview(String(params.id));
      if (!record) {
        return errorResponse(404, 'not_found', '면접을 찾을 수 없어요.');
      }

      await delay(150);
      return HttpResponse.json<InterviewDetailResponse>({
        id: record.interviewId,
        sessionId: record.sessionId,
        runId: record.runId,
        status: interviewStatus(record),
        // Sprint 1 은 텍스트 답변만 지원한다. enum 값이 하나뿐이다.
        answerMode: 'text',
        position: record.position,
        companyName: record.companyName,
        repositoryNames: interviewRepositoryNames(record),
        currentTurn: interviewCurrentTurn(record),
        totalTurns: TOTAL_TURNS,
        remainingSeconds: interviewRemainingSeconds(record),
        turns: interviewTurns(record),
        lastError: interviewLastError(record),
      });
    },
  ),

  /**
   * 리포트는 lazy generation이다. 첫 조회에서 생성을 시작하고 202를 준다.
   * FE는 retryAfter만큼 기다렸다 다시 조회해야 한다. spec/backend/features/report.md
   */
  http.get<IdParams, never, Res<ReportResponse | ReportGeneratingResponse>>(
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
        return HttpResponse.json<ReportGeneratingResponse>(
          { status: 'generating', retryAfter: 3 },
          { status: 202 },
        );
      }

      await delay(200);
      return HttpResponse.json<ReportResponse>({
        interviewId: record.interviewId,
        position: record.position,
        positionLabel: reportPositionLabel,
        totalScore: reportTotalScore,
        headline: reportHeadline,
        summary: reportSummary,
        scores: reportScores,
        agentFeedbacks: reportFeedbacks,
        coverage: reportCoverage,
        turns: completedTurns,
        repositoryNames: reportRepositoryNames,
        completedAt: reportCompletedAt,
      });
    },
  ),

  http.post<IdParams, never, Res<CreateInterviewResponse>>(
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

      return HttpResponse.json<CreateInterviewResponse>(
        { interviewId: next.interviewId, sessionId: next.sessionId },
        { status: 201 },
      );
    },
  ),

  /**
   * 피드백 이의 제기. 화면은 Sprint 1에서 버튼을 비활성으로 두지만(spec/frontend/features/report.md),
   * 계약과 api 클라이언트에는 이미 있어 핸들러가 없으면 활성화하는 순간 catch-all 501에 걸린다.
   */
  http.post<IdParams, FeedbackDisagreementRequest, Res<undefined>>(
    path('/interviews/:id/feedback-disagreements'),
    async ({ params, request }) => {
      const record = getInterview(String(params.id));
      if (!record) {
        return errorResponse(404, 'not_found', '면접을 찾을 수 없어요.');
      }
      if (interviewStatus(record) !== 'completed') {
        return errorResponse(409, 'report_unavailable', '아직 리포트가 없는 면접이에요.');
      }

      const body = await request.json();
      if (!body?.persona || !body?.reasonType) {
        return errorResponse(400, 'internal_error', 'persona와 reasonType은 필수입니다.');
      }
      if (body.comment && body.comment.length > 500) {
        return errorResponse(400, 'internal_error', '의견은 500자까지 쓸 수 있어요.');
      }

      await delay(200);
      return new HttpResponse(null, { status: 204 });
    },
  ),
];
