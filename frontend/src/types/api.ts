// 1. enum 타입

export type AnalysisStatus = 'no_repository' | 'no_interview' | 'completed';
export type InterviewStatus = 'in_progress' | 'completed' | 'abandoned';
export type RunStatus = 'running' | 'completed' | 'failed';
export type StepKey = 'fetch_repos' | 'extract_jd' | 'match_score' | 'prepare_result';
export type PrepareStepKey = 'analyze_repo' | 'build_persona' | 'compose_question' | 'set_criteria';
export type StepStatus = 'pending' | 'running' | 'completed';
export type AgentRole = 'tech_lead' | 'senior_developer' | 'manager';
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
  error: {
    reason: string;
    message: string;
    retryAfter?: number;
  };
};

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

// 7 마이페이지 GET /me/interviews

export type InterviewSummary = {
  id: string;
  position: string;
  repositoryNames: string[];
  status: InterviewStatus;
  totalScore: number | null;
  startedAt: string;
  completedAt: string | null;
};

export type InterviewListResponse = {
  interviews: InterviewSummary[];
  total: number;
  page: number;
  size: number;
};

// 4-v2 공고 입력 POST /analysis-runs

export type CreateAnalysisRunRequest = {
  jobUrl: string;
  coverLetter?: File;
  portfolioFile?: File;
  portfolioUrl?: string;
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
