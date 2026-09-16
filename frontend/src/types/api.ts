// 1. enum 타입

export type AnalysisStatus = 'syncing' | 'no_repository' | 'no_interview' | 'completed';
export type InterviewStatus =
  | 'preparing'
  | 'preparing_failed'
  | 'in_progress'
  | 'completed'
  | 'abandoned';
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
export type StepStatus = 'pending' | 'running' | 'completed' | 'failed';
export type AgentRole = 'tech_lead' | 'hr_manager' | 'domain_lead';
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

export type ApiError = {
  status: number;
  error: {
    reason: string;
    message: string;
    retryAfter?: number;
  };
};

export function isApiError(value: unknown): value is Omit<ApiError, 'status'> {
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
  companyName: string;
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
  companyName: string;
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
export type DocumentKind = 'cover_letter' | 'portfolio';


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
  status: RunStatus;
  reused?: boolean;
};

// 4-2-v2 분석 중 GET /analysis-runs/{runId}, /events

export type AnalysisStep = {
  key: StepKey;
  status: StepStatus;
};

export type AnalysisRunResponse = {
  runId: string;
  status: RunStatus;
  steps: AnalysisStep[];
  failureReason: string | null;
  estimatedSeconds: number | null;
};

export type SseStepEvent = {
  type: 'step';
  key: StepKey;
  status: StepStatus;
};

export type SseCompletedEvent = {
  type: 'completed';
};

export type SseFailedEvent = {
  type: 'failed';
  reason: string;
};

// 5a-v2 레포 선택 GET /analysis-runs/{runId}/result

export type RepositoryItem = {
  id: string;
  name: string;
  languages: string[];
  recommended: boolean;
  recommendReason: string;
  matchScore: number | null;
};

export type AnalysisResultResponse = {
  runId: string;
  position: string;
  jdRequirements: string[];
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
  role: AgentRole;
  question: string;
  answer: string | null;
};

export type InterviewDetailResponse = {
  id: string;
  sessionId: string;
  status: InterviewStatus;
  position: string;
  repositoryNames: string[];
  currentTurn: number;
  totalTurns: number | null;
  remainingSeconds: number;
  turns: InterviewTurn[];
};

// 4. WebSocket 메시지 타입

export type WsClientMessage = { type: 'answerStart' } | { type: 'answerEnd' };

export type WsServerMessage =
  | { type: 'prepareStep'; key: PrepareStepKey; status: StepStatus }
  | { type: 'prepareCompleted' }
  | { type: 'transcript'; text: string }
  | { type: 'thinking' }
  | { type: 'evidenceCheck'; repository: string; file: string }
  | { type: 'question'; role: AgentRole; text: string; turn: number }
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
  role: AgentRole;
  tags: string[];
  strengths: string[];
  improvements: string[];
  disagreementSubmitted: boolean;
};

export type ReportResponse = {
  interviewId: string;
  position: string;
  totalScore: number;
  headline: string;
  summary: string;
  scores: ScoreItem[];
  agentFeedbacks: AgentFeedback[];
  turns: InterviewTurn[];
  repositoryNames: string[];
  completedAt: string;
};

// POST /reports/{id}/feedback-disagreements

export type FeedbackDisagreementRequest = {
  agentRole: AgentRole;
  reasonType: ReasonType;
  comment?: string;
};
