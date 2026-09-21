// 1. enum 타입

export type AnalysisStatus = 'syncing' | 'no_repository' | 'no_interview' | 'completed';
export type InterviewStatus =
  'preparing' | 'preparing_failed' | 'in_progress' | 'completed' | 'abandoned';
export type RunStatus = 'running' | 'completed' | 'failed';
export type StepKey =
  | 'doc_extract'
  | 'repo_select'
  | 'repo_detail'
  | 'jd_fetch'
  | 'jd_extract'
  | 'repo_analyze'
  | 'match_score';
export type PrepareStepKey = 'analyze_repo' | 'build_persona' | 'compose_question' | 'set_criteria';
export type StepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
export type AnswerMode = 'text';
export type Persona = 'tech_lead' | 'hr_manager' | 'domain_lead';
export type ScoreKey =
  | 'project_understanding'
  | 'technical_reasoning'
  | 'problem_solving'
  | 'communication'
  | 'contribution_clarity'
  | 'company_job_fit';
export type ReasonType =
  'factual_error' | 'insufficient_basis' | 'overly_harsh' | 'unclear_intent' | 'other';

// 2. 공통 에러 타입

// 네트워크로 오는 본문 그대로. openapi.yaml #/components/schemas/ApiError 와 1:1 이다.
export type ApiErrorBody = {
  error: {
    reason: string;
    message: string;
    retryAfter?: number;
    details: Record<string, unknown>;
  };
};

// 클라이언트가 HTTP 상태코드를 덧붙인 형태. 본문에는 status 가 없다.
export type ApiError = ApiErrorBody & { status: number };

export function isApiError(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null) return false;
  if (!('error' in value)) return false;

  const error = (value as { error?: unknown }).error;
  if (typeof error !== 'object' || error === null) return false;

  const { reason, message } = error as { reason?: unknown; message?: unknown };
  return typeof reason === 'string' && typeof message === 'string';
}

// (전역) GET /me

export type MeResponse = {
  name: string;
  avatarUrl: string | null;
  githubLinked: boolean;
};

// 3 홈 대시보드 GET /me/home

export type LanguageRatio = {
  name: string;
  ratio: number;
};

export type AnalysisPanel = {
  basedOnRepoCount: number;
  languages: LanguageRatio[];
  projectTypes: string[];
  roleSummary: string;
};

export type RecentInterview = {
  id: string;
  position: string;
  companyName: string | null;
  totalScore: number | null;
  completedAt: string | null;
};

export type HomeResponse = {
  name: string;
  githubLinked: boolean;
  repositoryCount: number;
  analysisStatus: AnalysisStatus;
  analysis: AnalysisPanel | null;
  recentInterviews: RecentInterview[];
};

// 1a 마이페이지 GET /me/profile

export type MeProfileResponse = {
  name: string;
  avatarUrl: string;
  loginId: string | null;
  joinedAt: string;
  // 가장 최근 완료 면접의 position. 완료 면접이 없으면 null.
  desiredPosition: string | null;
  github: {
    linked: boolean;
    login: string | null;
    publicRepoCount: number | null;
  };
  interviewSummary: {
    totalCount: number;
    averageScore: number | null;
  };
};

// 1a 마이페이지 GET /me/interviews

export type InterviewSummary = {
  id: string;
  position: string;
  // 회사명이 없는 공고가 있다. openapi.yaml·api-spec.md #10 모두 nullable 이다.
  companyName: string | null;
  techStack: string[];
  careerLevel: string;
  repositoryNames: string[];
  status: InterviewStatus;
  totalScore: number | null;
  startedAt: string | null;
  completedAt: string | null;
};

export type InterviewListResponse = {
  interviews: InterviewSummary[];
  total: number;
  page: number;
  size: number;
  averageScore: number | null;
};

// 4-v2 공고 입력 POST /documents/preview

export type DocumentStatus = 'succeeded' | 'partial' | 'failed';

export type DocumentPreviewResponse = {
  documentId: string;
  extractStatus: DocumentStatus;
};

// 4-v2 공고 입력 POST /analysis-runs

export type CreateAnalysisRunRequest = {
  postingUrl: string;
  // Sprint 1 에서는 포트폴리오만 분석에 반영한다. 자소서 연결은 Sprint 2 설계 때 결정한다.
  documentId?: string;
};

export type CreateAnalysisRunResponse = {
  runId: string;
};

// 4-2-v2 분석 중 GET /analysis-runs/{runId}, /events

export type AnalysisStep = {
  key: StepKey;
  status: StepStatus;
};

export type AnalysisRunResponse = {
  runId: string;
  status: RunStatus;
  // steps 는 항상 StepKey 7개를 모두 포함한다. 실행하지 않은 단계도 skipped 로 온다.
  steps: AnalysisStep[];
  progress: number;
  failureReason: string | null;
  estimatedSeconds: number | null;
};

export type SseStepEvent = {
  type: 'step';
  key: StepKey;
  status: StepStatus;
};

export type SseProgressEvent = {
  type: 'progress';
  value: number;
};

export type SseCompletedEvent = {
  type: 'completed';
};

export type SseFailedEvent = {
  type: 'failed';
  reason: string;
};

// 5a-v2 레포 선택 GET /analysis-runs/{runId}/result

export type JdCategory = 'required' | 'preferred' | 'responsibility';
export type RepoStatus = 'succeeded' | 'partial' | 'failed';
export type CandidateSource = 'rule_filter' | 'portfolio' | 'both';

export type JdRequirement = {
  id: string;
  category: JdCategory;
  text: string;
  displayOrder: number;
};

export type RepositoryItem = {
  id: string;
  name: string;
  fullName: string;
  description: string | null;
  languages: LanguageRatio[];
  topics: string[];
  stars: number;
  forks: number;
  commitCount: number | null;
  userCommitCount: number | null;
  pushedAt: string | null;
  status: RepoStatus;
  errorCode: string | null;
  recommended: boolean;
  candidateSource: CandidateSource;
  recommendReason: string | null;
  matchScore: number | null;
  matchedRequirementIds: string[];
};

// 5a-v2 더 보기 GET /analysis-runs/{runId}/candidates
// 200 이면 repositories 와 같은 카드 스키마, 202 면 아래 analyzing 응답이 온다.

export type CandidatesResponse = {
  repositories: RepositoryItem[];
};

export type CandidatesAnalyzingResponse = {
  status: 'analyzing';
  // 본문 최상위 필드다. 공통 에러 객체의 error.retryAfter 와 위치가 다르다.
  retryAfter: number;
};

export type AnalysisResultResponse = {
  runId: string;
  position: string;
  companyName: string | null;
  jdRequirements: JdRequirement[];
  mentionedRepoCount: number;
  matchedRepoCount: number;
  repositories: RepositoryItem[];
};

// POST /interviews

export type CreateInterviewRequest = {
  runId: string;
  repositoryIds: string[];
};

export type CreateInterviewResponse = {
  sessionId: string;
  interviewId: string;
};

// 5a2/5b-v2 GET /interviews/{id}

export type InterviewTurn = {
  turn: number;
  persona: Persona;
  question: string;
  answer: string | null;
};

// status 가 preparing_failed 일 때만 값이 있다. WS error 이벤트와 필드 구성이 같다.
export type InterviewLastError = {
  reason: string;
  code: string;
  step: PrepareStepKey | null;
  recoverable: boolean;
  occurredAt: string;
};

export type InterviewDetailResponse = {
  id: string;
  sessionId: string;
  // 이 면접을 만든 analysis_jobs 행의 id. 새로고침 후 5a-v2 로 돌아갈 때 쓴다.
  runId: string;
  status: InterviewStatus;
  answerMode: AnswerMode;
  position: string;
  companyName: string | null;
  repositoryNames: string[];
  currentTurn: number;
  totalTurns: number;
  remainingSeconds: number;
  turns: InterviewTurn[];
  lastError: InterviewLastError | null;
};

// 4. WebSocket 메시지 타입

export type WsClientMessage = { type: 'answerStart' } | { type: 'answerEnd' };

export type WsServerMessage =
  | { type: 'prepareStep'; key: PrepareStepKey; status: StepStatus }
  | { type: 'prepareCompleted' }
  | { type: 'transcript'; text: string }
  | { type: 'thinking' }
  | { type: 'evidenceCheck'; repository: string; file: string }
  | { type: 'question'; persona: Persona; text: string; turn: number }
  | { type: 'questionEnd' }
  | { type: 'interviewEnd' }
  | { type: 'error'; reason: string };

// 5c-v2 면접 리포트 GET /interviews/{id}/report

export type ScoreItem = {
  key: ScoreKey;
  label: string;
  score: number;
};

export type AgentFeedback = {
  persona: Persona;
  tags: string[];
  strengths: string[];
  improvements: string[];
  disagreementSubmitted: boolean;
};

export type ReportCoverage = {
  totalRequirements: number;
  coveredRequirements: number;
  uncoveredRequirements: string[];
};

export type ReportResponse = {
  interviewId: string;
  position: string;
  positionLabel: string;
  totalScore: number;
  headline: string;
  summary: string;
  scores: ScoreItem[];
  agentFeedbacks: AgentFeedback[];
  coverage: ReportCoverage;
  turns: InterviewTurn[];
  repositoryNames: string[];
  completedAt: string;
};

// 202 — 리포트 생성 중. retryAfter(초) 간격으로 폴링한다.
export type ReportGeneratingResponse = {
  status: 'generating';
  retryAfter: number;
};

// POST /interviews/{id}/feedback-disagreements

export type FeedbackDisagreementRequest = {
  persona: Persona;
  reasonType: ReasonType;
  comment?: string;
};
