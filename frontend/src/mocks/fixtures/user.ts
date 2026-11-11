import { INTERVIEW_TOTAL_TURNS } from '@/shared/interview';
import type {
  HomeResponse,
  InterviewListResponse,
  MeProfileResponse,
  MeResponse,
} from '@/types/api';

/**
 * 응답은 모두 `spec/shared/contracts/openapi.yaml`의 스키마를 따른다.
 * 이 파일의 4개 경로(`/me`, `/me/profile`, `/me/home`, `/me/interviews`)는 전부 계약에 있다.
 */
export const me: MeResponse = {
  name: '김개발',
  avatarUrl: 'https://avatars.githubusercontent.com/u/12345',
  githubLinked: true,
};

export const meUnlinked: MeResponse = {
  name: '김개발',
  avatarUrl: null,
  githubLinked: false,
};

const recentInterviews = [
  {
    id: 'a3d51c20-1001-4c00-9a00-000000000001',
    position: 'Backend Developer',
    companyName: '테스트 기업',
    totalScore: 81,
    completedAt: '2026-09-01T15:20:00Z',
  },
  {
    id: 'a3d51c20-1002-4c00-9a00-000000000002',
    position: 'Server Engineer',
    companyName: '테스트 기업',
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
    companyName: '테스트 기업',
    techStack: ['Python', 'FastAPI'],
    careerLevel: '신입',
    repositoryNames: ['payment-service', 'project-a'],
    status: 'completed',
    totalScore: 81,
    startedAt: '2026-09-01T15:00:00Z',
    completedAt: '2026-09-01T15:20:00Z',
    answeredTurns: 9,
    reportAvailable: true,
  },
  {
    id: 'a3d51c20-1002-4c00-9a00-000000000002',
    position: 'Server Engineer',
    companyName: '테스트 기업',
    techStack: ['Python', 'FastAPI'],
    careerLevel: '신입',
    repositoryNames: ['payment-service'],
    status: 'completed',
    totalScore: 74,
    startedAt: '2026-08-21T09:44:00Z',
    completedAt: '2026-08-21T10:05:00Z',
    answeredTurns: 9,
    reportAvailable: true,
  },
  {
    // 시간이 끝나 5턴에서 끝난 면접. 리포트는 있고 평균 점수에는 들어가지 않는다(#246).
    id: 'a3d51c20-1007-4c00-9a00-000000000007',
    position: 'Backend Developer',
    companyName: '테스트 기업',
    techStack: ['Python', 'FastAPI'],
    careerLevel: '신입',
    repositoryNames: ['project-a'],
    status: 'completed',
    totalScore: 88,
    startedAt: '2026-08-28T11:00:00Z',
    completedAt: '2026-08-28T11:15:00Z',
    answeredTurns: 5,
    reportAvailable: true,
  },
  {
    // 시간이 끝나 2턴에서 끝난 면접. 진행이 짧아 리포트를 만들 수 없다(#246).
    // 상태 문구가 가장 긴 행에 긴 기술 스택·레포 이름을 둬 이력 카드 넘침을 확인한다.
    id: 'a3d51c20-1008-4c00-9a00-000000000008',
    position: 'Backend Developer',
    companyName: '테스트 기업',
    techStack: [
      'GraphQL',
      'MongoDB',
      'MySQL',
      'React',
      'Node.js',
      'TypeScript',
      'AWS',
      'Docker',
      'Spring Boot',
      'Kubernetes',
      'Next.js',
    ],
    careerLevel: '신입',
    repositoryNames: ['2025_Capstone-Design', 'notification-worker'],
    status: 'completed',
    totalScore: null,
    startedAt: '2026-08-25T09:00:00Z',
    completedAt: '2026-08-25T09:15:00Z',
    answeredTurns: 2,
    reportAvailable: false,
  },
  {
    id: 'a3d51c20-1003-4c00-9a00-000000000003',
    position: 'Backend Developer',
    companyName: '테스트 기업',
    techStack: ['Python', 'FastAPI'],
    careerLevel: '신입',
    repositoryNames: ['notification-worker'],
    status: 'abandoned',
    totalScore: null,
    startedAt: '2026-08-14T13:02:00Z',
    completedAt: null,
    answeredTurns: 3,
    reportAvailable: false,
  },
  {
    id: 'a3d51c20-1004-4c00-9a00-000000000004',
    position: 'Platform Engineer',
    companyName: '테스트 기업',
    techStack: ['Python', 'FastAPI'],
    careerLevel: '신입',
    repositoryNames: ['infra-terraform', 'batch-pipeline'],
    status: 'in_progress',
    totalScore: null,
    startedAt: '2026-09-12T20:11:00Z',
    completedAt: null,
    answeredTurns: 5,
    reportAvailable: false,
  },
  {
    // 준비 단계에서 버린 면접. 첫 질문 전이라 startedAt이 없고 목록에서 빠진다.
    id: 'a3d51c20-1006-4c00-9a00-000000000006',
    position: 'Backend Developer',
    companyName: '테스트 기업',
    techStack: ['Python', 'FastAPI'],
    careerLevel: '신입',
    repositoryNames: ['payment-service'],
    status: 'abandoned',
    totalScore: null,
    startedAt: null,
    completedAt: null,
    answeredTurns: 0,
    reportAvailable: false,
  },
];

/**
 * `/me/interviews` 대상: completed와 시작 후 중단된 abandoned(공통 0009).
 * 정렬은 coalesce(completedAt, startedAt) 최신순이다.
 */
const listedInterviews = allInterviews
  .filter(
    (item) =>
      item.status === 'completed' || (item.status === 'abandoned' && item.startedAt !== null),
  )
  .sort((a, b) =>
    (b.completedAt ?? b.startedAt ?? '').localeCompare(a.completedAt ?? a.startedAt ?? ''),
  );

/** 완료 면접 점수의 평균. 마이페이지 프로필과 면접 목록이 같은 값을 봐야 한다. */
const scoredInterviews = allInterviews.filter(
  // 평균은 9턴을 모두 답한 면접만 센다. 시간이 끝나 일찍 끝난 면접은 뺀다(#246).
  (item) => item.totalScore !== null && item.answeredTurns === INTERVIEW_TOTAL_TURNS,
);
const averageScore =
  scoredInterviews.reduce((sum, item) => sum + (item.totalScore ?? 0), 0) / scoredInterviews.length;

/**
 * `desiredPosition`은 가장 최근 완료 면접의 position이다. 완료 면접이 없으면 null.
 * 목록 fixture에서 파생시켜 두 화면이 어긋나지 않게 한다.
 */
const latestCompleted = allInterviews
  .filter((item) => item.status === 'completed' && item.completedAt !== null)
  .sort((a, b) => (a.completedAt! < b.completedAt! ? 1 : -1))[0];

export const meProfile: MeProfileResponse = {
  name: me.name,
  avatarUrl: 'https://avatars.githubusercontent.com/u/12345',
  loginId: 'kimdev',
  joinedAt: '2026-06-02T04:11:00Z',
  desiredPosition: latestCompleted?.position ?? null,
  github: {
    linked: true,
    login: 'kimdev',
    publicRepoCount: 9,
  },
  interviewSummary: {
    totalCount: allInterviews.filter((item) => item.status === 'completed').length,
    averageScore,
  },
};

export function interviewPage(page: number, size: number): InterviewListResponse {
  const start = (page - 1) * size;
  return {
    interviews: listedInterviews.slice(start, start + size),
    total: listedInterviews.length,
    averageScore,
    page,
    size,
  };
}
