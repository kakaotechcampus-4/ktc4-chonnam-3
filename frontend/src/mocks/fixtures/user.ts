import type { HomeResponse, InterviewListResponse, MeResponse } from '@/types/api';

/**
 * `GET /me`는 `spec/shared/contracts/me-response.schema.json`으로 이관된 계약이다.
 * `GET /me/home`, `GET /me/interviews`, `POST /auth/logout`은 아직 이관 전이라
 * `frontend/docs/api-spec.md`와 `src/types/api.ts`를 기준으로 둔다.
 */
export const me: MeResponse = {
  name: '김개발',
  githubLinked: true,
};

export const meUnlinked: MeResponse = {
  name: '김개발',
  githubLinked: false,
};

const recentInterviews = [
  {
    id: 'a3d51c20-1001-4c00-9a00-000000000001',
    position: 'Backend Developer',
    totalScore: 81,
    completedAt: '2026-09-01T15:20:00Z',
  },
  {
    id: 'a3d51c20-1002-4c00-9a00-000000000002',
    position: 'Server Engineer',
    totalScore: 74,
    completedAt: '2026-08-21T10:05:00Z',
  },
];

const homeCompleted: HomeResponse = {
  name: '김개발',
  githubLinked: true,
  repositoryCount: 9,
  analysisStatus: 'completed',
  analysis: {
    basedOnRepoCount: 2,
    languages: [
      { name: 'Java', ratio: 42 },
      { name: 'TypeScript', ratio: 31 },
      { name: 'Python', ratio: 27 },
    ],
    projectTypes: ['백엔드 API 서버', '결제·트랜잭션'],
    roleSummary:
      '2개 레포의 README와 커밋 이력을 종합하면 백엔드 API 설계와 DB·캐시 최적화를 가장 자주 맡았습니다.',
  },
  recentInterviews,
};

const homeNoInterview: HomeResponse = {
  ...homeCompleted,
  analysisStatus: 'no_interview',
  analysis: null,
  recentInterviews: [],
};

const homeNoRepository: HomeResponse = {
  ...homeCompleted,
  repositoryCount: 0,
  analysisStatus: 'no_repository',
  analysis: null,
  recentInterviews: [],
};

/** localStorage `msw.home` 또는 `?scenario=` 로 전환한다. 기본값은 completed. */
export const homeScenarios: Record<string, HomeResponse> = {
  completed: homeCompleted,
  no_interview: homeNoInterview,
  no_repository: homeNoRepository,
};

const allInterviews: InterviewListResponse['interviews'] = [
  {
    id: 'a3d51c20-1001-4c00-9a00-000000000001',
    position: 'Backend Developer',
    repositoryNames: ['payment-service', 'project-a'],
    status: 'completed',
    totalScore: 81,
    startedAt: '2026-09-01T15:00:00Z',
    completedAt: '2026-09-01T15:20:00Z',
  },
  {
    id: 'a3d51c20-1002-4c00-9a00-000000000002',
    position: 'Server Engineer',
    repositoryNames: ['payment-service'],
    status: 'completed',
    totalScore: 74,
    startedAt: '2026-08-21T09:44:00Z',
    completedAt: '2026-08-21T10:05:00Z',
  },
  {
    id: 'a3d51c20-1003-4c00-9a00-000000000003',
    position: 'Backend Developer',
    repositoryNames: ['notification-worker'],
    status: 'abandoned',
    totalScore: null,
    startedAt: '2026-08-14T13:02:00Z',
    completedAt: null,
  },
  {
    id: 'a3d51c20-1004-4c00-9a00-000000000004',
    position: 'Platform Engineer',
    repositoryNames: ['infra-terraform', 'batch-pipeline'],
    status: 'in_progress',
    totalScore: null,
    startedAt: '2026-09-12T20:11:00Z',
    completedAt: null,
  },
];

export function interviewPage(page: number, size: number): InterviewListResponse {
  const start = (page - 1) * size;
  return {
    interviews: allInterviews.slice(start, start + size),
    total: allInterviews.length,
    page,
    size,
  };
}
