/**
 * Sprint 1 FIX 계약 타입.
 *
 * 원본: `spec/shared/contracts/openapi.yaml` (feature/spec-ai-docs 브랜치)
 * 보조: `spec/backend/features/{analysis-run,documents,interview,report}.md`
 *
 * `src/types/api.ts`(이관 전 FE 문서 기준)와 충돌하는 항목이 있다.
 * `spec/shared/contracts/README.md`에 따라 충돌 시 openapi.yaml이 우선이므로
 * 새 계약 표면은 이 파일을 쓴다. 기존 타입은 이관 합의 전까지 그대로 둔다.
 * 충돌 목록은 `spec/frontend/designs/2026-09-14-msw-mock-layer.md` 참고.
 */

// 공통

export type ContractError = {
  error: {
    reason: string;
    message: string;
    details?: Record<string, unknown>;
    retryAfter?: number;
  };
};

// 문서 preview — POST /documents/preview

export type DocumentExtractStatus = 'succeeded' | 'partial' | 'failed';

export type DocumentPreviewResponse = {
  documentId: string;
  status: DocumentExtractStatus;
  fileName: string;
  sizeBytes: number;
  extractedGithubUrls: string[];
  truncated?: boolean;
  failureReason?: string | null;
};

// 분석 run — POST /analysis-runs

export type CreateAnalysisRunBody = {
  postingUrl: string;
  documentId?: string | null;
};

export type RunStatus = 'running' | 'completed' | 'failed';

export type CreateAnalysisRunResult = {
  runId: string;
  status: RunStatus;
  reused?: boolean;
};

// 분석 진행 — GET /analysis-runs/{runId}

export type ContractStepKey =
  | 'doc_extract'
  | 'repo_select'
  | 'repo_detail'
  | 'jd_fetch'
  | 'jd_extract'
  | 'repo_analyze'
  | 'match_score';

export type ContractStepStatus = 'pending' | 'running' | 'succeeded' | 'failed';

export type ContractStep = {
  key: ContractStepKey;
  status: ContractStepStatus;
};

export type AnalysisRunStatusResponse = {
  runId: string;
  status: RunStatus;
  progress: number;
  steps: ContractStep[];
  failureReason?: string | null;
};

// SSE — GET /analysis-runs/{runId}/events
// openapi.yaml은 text/event-stream 이라고만 정의한다. 아래 payload 형태는
// frontend/docs/api-spec.md의 기존 정의에 새 enum을 반영한 것으로 BE 확인이 필요하다.

export type ContractSseEvent =
  | { type: 'step'; key: ContractStepKey; status: ContractStepStatus }
  | { type: 'completed' }
  | { type: 'failed'; reason: string };

// 분석 결과 — GET /analysis-runs/{runId}/result

export type RepositoryCardStatus = 'succeeded' | 'partial' | 'failed';
export type CandidateSource = 'rule_filter' | 'portfolio' | 'both';

export type RepositoryCard = {
  repositoryId: string;
  fullName: string;
  name: string;
  description?: string | null;
  languages?: { name: string; ratio: number }[];
  topics?: string[];
  stars?: number;
  forks?: number;
  commitCount?: number | null;
  userCommitCount?: number | null;
  pushedAt?: string | null;
  status: RepositoryCardStatus;
  errorCode?: string | null;
  recommended: boolean;
  candidateSource?: CandidateSource;
  recommendReason?: string | null;
  matchScore?: number | null;
  matchedRequirementIds?: string[];
};

export type FailedRepository = {
  repositoryId: string;
  errorCode: string;
};

export type AnalysisRunResultResponse = {
  runId: string;
  status: RunStatus;
  analyzedCount: number;
  failedCount: number;
  failedRepositories: FailedRepository[];
  repositories: RepositoryCard[];
};

// 후보 더 보기 — GET /analysis-runs/{runId}/candidates?page=N

export type CandidatePageResponse = {
  runId: string;
  page: number;
  repositories: RepositoryCard[];
};

export type AnalyzingResponse = {
  status: 'analyzing';
  retryAfter: number;
};

// 면접 — POST /interviews, GET /interviews/{id}

export type Persona = 'tech_lead' | 'hr_manager' | 'domain_lead';

export type ContractInterviewStatus =
  'preparing' | 'preparing_failed' | 'in_progress' | 'completed' | 'abandoned';

export type CreateInterviewBody = {
  runId: string;
  repositoryIds: string[];
};

export type CreateInterviewResult = {
  interviewId: string;
  sessionId?: string | null;
};

export type ContractTurn = {
  turn: number;
  persona: Persona;
  question: string;
  answer?: string | null;
};

export type InterviewDetail = {
  id: string;
  sessionId?: string | null;
  status: ContractInterviewStatus;
  currentTurn: number;
  totalTurns: number;
  remainingSeconds?: number;
  turns: ContractTurn[];
};

// 리포트 — GET /interviews/{id}/report

export type GeneratingResponse = {
  status: 'generating';
  retryAfter: number;
};

export type ContractScore = {
  key: string;
  label: string;
  score: number;
};

export type ContractAgentFeedback = {
  persona: Persona;
  tags?: string[];
  strengths: string[];
  improvements: string[];
};

export type ContractReport = {
  interviewId: string;
  totalScore: number;
  scores: ContractScore[];
  agentFeedbacks: ContractAgentFeedback[];
  turns: ContractTurn[];
};
