import { HttpResponse, delay, http, type PathParams } from 'msw';

import { createRequestId } from '@/shared/requestId';
import type {
  CreateInterviewRequest,
  CreateInterviewResponse,
  FeedbackDisagreementRequest,
  InterviewDetailResponse,
  RetryQuestionRequest,
  RetryQuestionResponse,
  ReportGeneratingResponse,
  ReportResponse,
} from '@/types/api';
import {
  abandonInterview,
  createInterview,
  getInterview,
  getRun,
  hasActiveInterviewForRun,
  interviewCurrentTurn,
  interviewLastError,
  interviewRemainingSeconds,
  startInterview,
  interviewRepositoryNames,
  interviewStatus,
  interviewTurns,
  reportReady,
} from '../db';
import { candidatePages } from '../fixtures/analysis';
import { retryPrepare, streamPrepareFrom } from '../ws/prepare';
import { clientsForSession } from '../ws/interview';
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
import { toneWav } from '../fixtures/questionAudio';
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
  http.post<IdParams, RetryQuestionRequest, Res<RetryQuestionResponse>>(
    path('/interviews/:id/question/retry'),
    async ({ params, request }) => {
      const record = getInterview(String(params.id));
      if (!record) return errorResponse(404, 'not_found', '면접을 찾을 수 없어요.');
      const { requestId } = await request.json();
      if (
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requestId ?? '')
      ) {
        return errorResponse(400, 'invalid_request', '요청 ID를 확인해주세요.');
      }
      const saved = record.questionRetryState;
      if (saved?.requestId === requestId) {
        if (saved.status === 'running')
          return errorResponse(409, 'question_retry_in_progress', '질문을 준비하고 있어요.');
        if (saved.status === 'failed')
          return errorResponse(409, 'question_retry_failed', '질문을 만들지 못했어요.');
        const current = record.liveTurns?.at(-1);
        if (current?.turn !== saved.turnNo || current.answer !== null)
          return errorResponse(409, 'question_retry_unavailable', '현재 질문에 사용할 수 없어요.');
        return HttpResponse.json({
          interviewId: record.interviewId,
          sessionId: record.sessionId,
          turnNo: saved.turnNo,
        });
      }
      if ((record.questionRetryCount ?? 0) >= 1)
        return errorResponse(409, 'question_retry_limit', '이어가기 횟수를 사용했어요.');
      const previous = record.liveTurns?.at(-1);
      if (
        interviewStatus(record) !== 'in_progress' ||
        record.questionRetryEligible === false ||
        !previous?.answer ||
        previous.turn >= TOTAL_TURNS
      ) {
        return errorResponse(409, 'question_retry_unavailable', '현재 상태에서 이어갈 수 없어요.');
      }
      const turnNo = previous.turn + 1;
      record.questionRetryCount = 1;
      record.questionRetryState = {
        requestId,
        turnNo,
        status: 'running',
        expiresAt: new Date(Date.now() + 255_000).toISOString(),
      };
      if (record.questionRetryMode === 'running')
        return errorResponse(409, 'question_retry_in_progress', '질문을 준비하고 있어요.');
      await delay(700);
      if (record.questionRetryMode === 'failed') {
        record.questionRetryState.status = 'failed';
        return errorResponse(409, 'question_retry_failed', '질문을 만들지 못했어요.');
      }
      record.liveTurns!.push({ ...structuredClone(completedTurns[turnNo - 1]), answer: null });
      record.sessionId = `sess_retry_${createRequestId()}`;
      record.questionRetryState.status = 'succeeded';
      return HttpResponse.json({
        interviewId: record.interviewId,
        sessionId: record.sessionId,
        turnNo,
      });
    },
  ),

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
        answerMode: record.answerMode ?? 'voice',
        position: record.position,
        companyName: record.companyName,
        repositoryNames: interviewRepositoryNames(record),
        currentTurn: interviewCurrentTurn(record),
        totalTurns: TOTAL_TURNS,
        remainingSeconds: interviewRemainingSeconds(record),
        turns: interviewTurns(record),
        lastError: interviewLastError(record),
        ...(record.questionRetrySupported === false
          ? {}
          : {
              canRetryQuestion:
                record.questionRetryEligible !== false &&
                interviewStatus(record) === 'in_progress' &&
                (record.questionRetryCount ?? 0) < 1 &&
                !!record.liveTurns?.length &&
                record.liveTurns.at(-1)?.answer != null,
              questionRetryCount: record.questionRetryCount ?? 0,
              questionRetryState: record.questionRetryState ?? null,
            }),
      });
    },
  ),

  /**
   * 질문 음성(TTS). spec/shared/decisions/0007 (Proposed).
   * 실제 서버는 생성 중이면 완료까지 기다렸다 응답한다. mock은 짧게 지연만 준다.
   */
  http.get<{ id: string; turn: string }>(
    path('/interviews/:id/turns/:turn/question-audio'),
    async ({ params }) => {
      if (!getInterview(String(params.id))) {
        return errorResponse(404, 'not_found', '면접을 찾을 수 없어요.');
      }
      await delay(200);
      return new HttpResponse(toneWav(1.2), { headers: { 'Content-Type': 'audio/wav' } });
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
      if (record.reportFailed) {
        return errorResponse(409, 'report_unavailable', '리포트 생성에 실패했어요.');
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
        revision: record.reportRevision ?? 1,
        position: record.position,
        positionLabel: reportPositionLabel,
        totalScore: reportTotalScore,
        headline: reportHeadline,
        summary: reportSummary,
        scores: reportScores,
        agentFeedbacks: reportFeedbacks.map((feedback) => ({
          ...feedback,
          disagreementSubmitted:
            record.reportDisagreements?.some(
              (item) =>
                item.persona === feedback.persona && item.revision === (record.reportRevision ?? 1),
            ) ?? false,
        })),
        coverage: reportCoverage,
        turns: completedTurns,
        repositoryNames: reportRepositoryNames,
        completedAt: reportCompletedAt,
      });
    },
  ),

  http.post<IdParams, never, Res<ReportGeneratingResponse>>(
    path('/interviews/:id/report/retry'),
    async ({ params }) => {
      const record = getInterview(String(params.id));
      if (!record) return errorResponse(404, 'not_found', '면접을 찾을 수 없어요.');
      const pending = record.reportRequestedAt !== undefined && !reportReady(record);
      if (interviewStatus(record) !== 'completed' || (!record.reportFailed && !pending)) {
        return errorResponse(409, 'report_unavailable', '다시 생성할 수 없는 리포트예요.');
      }
      if (!pending) record.reportRequestedAt = Date.now();
      record.reportFailed = false;
      return HttpResponse.json<ReportGeneratingResponse>(
        { status: 'generating', retryAfter: 3 },
        { status: 202 },
      );
    },
  ),

  /**
   * 준비 실패 재시도. 0010 결정으로 WS `prepareRetry` 메시지를 대체했다.
   *
   * 진행 상황(`prepareStep` → `prepareCompleted` → 첫 `question`)은 계약대로 WS 로 나간다.
   * 열린 연결이 있으면 지금 흘려보내고, 없으면 다음 연결이 경과 시간 기준으로 이어받는다.
   * 응답 코드·실패 reason 은 계약에 없다. 설계 문서 D15.
   */
  http.post<IdParams, never, Res<undefined>>(
    path('/interviews/:id/prepare/retry'),
    async ({ params }) => {
      const record = getInterview(String(params.id));
      // 계약·BE 모두 없는 면접의 준비 재시도는 404가 아니라 410 session_expired다.
      if (!record) {
        return errorResponse(410, 'session_expired', '면접 세션이 만료됐어요.');
      }
      if (interviewStatus(record) !== 'preparing_failed') {
        return errorResponse(409, 'prep_failed', '준비 실패 상태에서만 다시 시도할 수 있어요.');
      }
      if (hasActiveInterviewForRun(record.runId)) {
        return errorResponse(409, 'session_limit_exceeded', '이미 진행 중인 면접이 있어요.');
      }

      retryPrepare(record);
      await delay(200);
      for (const client of clientsForSession(record.sessionId)) {
        void streamPrepareFrom(client, record);
      }
      return new HttpResponse(null, { status: 202 });
    },
  ),

  /** [면접 시작하기] 클릭. 이 시각부터 제한 시간이 흐른다. 멱등이다. */
  http.post<IdParams, never, Res<undefined>>(path('/interviews/:id/start'), async ({ params }) => {
    const record = getInterview(String(params.id));
    if (!record) {
      return errorResponse(404, 'not_found', '면접을 찾을 수 없어요.');
    }
    if (!startInterview(record)) {
      return errorResponse(409, 'not_ready', '면접을 시작할 수 없는 상태예요.');
    }
    return new HttpResponse(null, { status: 204 });
  }),

  /** 나가기·레포 재선택의 중단. api-spec.md #24, 공통 0009. */
  http.post<IdParams, never, Res<undefined>>(
    path('/interviews/:id/abandon'),
    async ({ params }) => {
      const record = getInterview(String(params.id));
      if (!record) {
        return errorResponse(404, 'not_found', '면접을 찾을 수 없어요.');
      }

      const status = interviewStatus(record);
      if (status !== 'abandoned') {
        if (status !== 'in_progress' && status !== 'preparing_failed') {
          return errorResponse(409, 'already_completed', '이미 끝난 면접이에요.');
        }
        abandonInterview(record);
        // 전용 close code 없이 그 면접의 열린 연결을 닫는다.
        clientsForSession(record.sessionId).forEach((client) => client.close());
      }

      await delay(150);
      return new HttpResponse(null, { status: 204 });
    },
  ),

  http.post<IdParams, never, Res<CreateInterviewResponse>>(
    path('/interviews/:id/retry'),
    async ({ params }) => {
      const record = getInterview(String(params.id));
      if (!record) {
        return errorResponse(404, 'not_found', '면접을 찾을 수 없어요.');
      }

      // 재도전은 completed와 시작 후 중단된 abandoned만 허용한다(공통 0009).
      const status = interviewStatus(record);
      const startedAbandoned = status === 'abandoned' && record.startedAt !== undefined;
      if (status !== 'completed' && !startedAbandoned) {
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

  /** 보고 있던 리포트 버전을 확인해 의견만 접수한다. 점수는 변경하지 않는다. */
  http.post<IdParams, FeedbackDisagreementRequest, Res<undefined>>(
    path('/interviews/:id/feedback-disagreements'),
    async ({ params, request }) => {
      const record = getInterview(String(params.id));
      if (!record) {
        return errorResponse(404, 'not_found', '면접을 찾을 수 없어요.');
      }
      if (interviewStatus(record) !== 'completed' || record.reportFailed || !reportReady(record)) {
        return errorResponse(409, 'report_unavailable', '아직 리포트가 없는 면접이에요.');
      }

      const body = await request.json();
      if (
        !body ||
        !['tech_lead', 'domain_lead', 'hr_manager'].includes(body.persona) ||
        ![
          'factual_error',
          'insufficient_basis',
          'overly_harsh',
          'unclear_intent',
          'other',
        ].includes(body.reasonType) ||
        !Number.isInteger(body.expectedRevision) ||
        body.expectedRevision < 1
      ) {
        return errorResponse(400, 'invalid_request', '의견 유형과 리포트 정보를 확인해주세요.');
      }
      if (
        body.comment !== undefined &&
        (typeof body.comment !== 'string' || body.comment.length > 500)
      ) {
        return errorResponse(400, 'invalid_request', '의견은 500자까지 쓸 수 있어요.');
      }
      if (body.expectedRevision !== (record.reportRevision ?? 1)) {
        return errorResponse(409, 'report_unavailable', '리포트가 변경됐어요.');
      }
      const submitted = record.reportDisagreements ?? [];
      if (
        submitted.some(
          (item) => item.persona === body.persona && item.revision === body.expectedRevision,
        )
      ) {
        return errorResponse(409, 'already_submitted', '이미 의견이 접수됐어요.');
      }
      record.reportDisagreements = [
        ...submitted,
        { revision: body.expectedRevision, persona: body.persona },
      ];

      await delay(200);
      return new HttpResponse(null, { status: 204 });
    },
  ),
];
