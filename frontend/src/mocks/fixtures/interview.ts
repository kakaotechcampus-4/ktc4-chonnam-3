import type { AgentFeedback, InterviewTurn, ReportCoverage, ScoreItem } from '@/types/api';
import { REQ_MONITORING, REQ_PAYMENT_DOMAIN, jdRequirements } from './jd';

/**
 * 면접 턴 구성은 `spec/backend/features/interview.md`의 Turn 정책을 따른다.
 * 아래 예시는 9턴·첫 HR·기술 6턴·도메인 1턴·HR 2턴이며, 역할별 고정 배분을 뜻하지 않는다.
 * 실제 정책은 기술 목표 6턴·최소 5턴, 도메인·HR 합산 최소 3턴이고 개별 배분은 유동적이다.
 */
export const TOTAL_TURNS = 9;

/** 면접 생성 직후 준비가 끝나면 노출되는 첫 질문. */
export const firstTurn: InterviewTurn = {
  turn: 1,
  persona: 'hr_manager',
  question: '먼저 긴장 푸시고, 선택하신 프로젝트 중 가장 애착이 가는 걸 하나만 소개해주세요.',
  answer: null,
};

/** 이미 종료된 면접(seed)의 전체 턴. 리포트/마이페이지 화면 개발용. */
export const completedTurns: InterviewTurn[] = [
  {
    ...firstTurn,
    answer: 'payment-service가 가장 기억에 남습니다. 결제 실패 재시도를 직접 설계했습니다.',
  },
  {
    turn: 2,
    persona: 'tech_lead',
    question:
      'payment-service의 재시도를 지수 백오프로 구현하셨는데, 최대 재시도 횟수를 3회로 정한 근거가 있나요?',
    answer: 'PG사 타임아웃이 10초라 3회면 30초 안에 끝난다고 판단했습니다.',
  },
  {
    turn: 3,
    persona: 'tech_lead',
    question: '재시도 중 중복 결제가 발생할 수 있는데 멱등성은 어떻게 보장했나요?',
    answer: '요청마다 멱등키를 만들어 Redis에 저장하고 중복이면 기존 결과를 반환했습니다.',
  },
  {
    turn: 4,
    persona: 'tech_lead',
    question: 'Redis가 내려가면 멱등키도 함께 사라지는데, 그 상황은 어떻게 다뤘나요?',
    answer: '그 부분은 DB 유니크 제약으로 2차 방어를 뒀습니다.',
  },
  {
    turn: 5,
    persona: 'tech_lead',
    question: 'project-a에서 캐시 TTL을 600초로 두셨습니다. 다른 값과 비교해본 근거가 있나요?',
    answer: '상품 정보 변경 주기가 10분 내외라고 보고 맞췄습니다.',
  },
  {
    turn: 6,
    persona: 'tech_lead',
    question: '캐시 무효화는 TTL에만 의존했나요, 아니면 쓰기 시점에 직접 만료시켰나요?',
    answer: '상품 수정 API에서 해당 키를 직접 삭제했습니다.',
  },
  {
    turn: 7,
    persona: 'tech_lead',
    question:
      '상품 수정이 여러 서버에서 동시에 일어나면 캐시와 DB가 어긋날 수 있습니다. 그 경우는 어떻게 되나요?',
    answer: '거기까지는 고려하지 못했습니다.',
  },
  {
    turn: 8,
    persona: 'domain_lead',
    question:
      '결제 도메인에서는 정산 담당자가 장애 이후 데이터를 대사(reconciliation)하게 됩니다. 그 흐름까지 고려한 설계가 있었나요?',
    answer: '정산 팀과 협의해 실패 건을 따로 적재하는 테이블을 뒀습니다.',
  },
  {
    turn: 9,
    persona: 'hr_manager',
    question:
      '방금 말씀하신 협의 과정에서 의견이 갈렸던 적이 있나요? 어떻게 정리하셨는지 궁금합니다.',
    answer:
      '정산 팀은 실시간 알림을 원했고 저는 배치를 주장했는데, 비용을 근거로 배치로 합의했습니다.',
  },
];

/**
 * score key/label은 `score_criteria` 시드에서 내려오는 값이다.
 * 점수 6개·0~100 범위·단순 평균은 `spec/backend/features/report.md`의 확정 정책이다.
 * 아래 값은 화면 확인용 예시이며 실제 세부 채점 기준의 검수·적용 결과가 아니다.
 */
export const reportScores: ScoreItem[] = [
  { key: 'project_understanding', label: '프로젝트 이해도', score: 88 },
  { key: 'technical_reasoning', label: '기술적 사고력', score: 79 },
  { key: 'problem_solving', label: '문제 해결력', score: 83 },
  { key: 'communication', label: '커뮤니케이션', score: 80 },
  { key: 'contribution_clarity', label: '기여도 명확성', score: 76 },
  { key: 'company_job_fit', label: '기업·직무 적합성', score: 82 },
];

export const reportFeedbacks: AgentFeedback[] = [
  {
    persona: 'tech_lead',
    tags: ['Architecture', 'Trade-off'],
    strengths: [
      '멱등키와 DB 유니크 제약으로 2중 방어를 설계한 점은 실제 장애 경험에서 나온 판단으로 보입니다.',
    ],
    improvements: [
      '캐시 TTL 600초는 변경 주기 추정에만 근거했고, 다른 값과 비교한 흔적이 없습니다.',
      '다중 서버 동시 쓰기 상황의 캐시 정합성은 답변하지 못했습니다.',
    ],
    disagreementSubmitted: false,
  },
  {
    persona: 'domain_lead',
    tags: ['Payment', 'Reconciliation'],
    strengths: ['실패 건 적재 테이블을 둬서 정산 대사 흐름을 고려한 점이 좋았습니다.'],
    improvements: ['대사 주기와 정합성 기준을 누가 정했는지는 설명이 부족했습니다.'],
    disagreementSubmitted: false,
  },
  {
    persona: 'hr_manager',
    tags: ['Collaboration', 'Decision'],
    strengths: ['이견을 비용이라는 공통 기준으로 정리한 과정을 구체적으로 설명했습니다.'],
    improvements: ['본인의 기여 범위와 팀의 결정을 구분해 말하면 더 명확해집니다.'],
    disagreementSubmitted: false,
  },
];

export const reportTotalScore = 81;

/**
 * 리포트 상단 구성 요소. 계약의 ReportResponse required 필드다.
 * positionLabel은 화면 표기용 한글 라벨, position은 공고 원문 값이다.
 */
export const reportPositionLabel = '백엔드 개발자';
export const reportHeadline = '결제 도메인의 장애 대응 근거가 뚜렷한 지원자입니다';
export const reportSummary =
  '멱등성과 2중 방어처럼 실제 장애를 겪고 내린 판단은 근거가 분명했습니다. ' +
  '반면 캐시 정합성처럼 여러 서버가 얽히는 상황은 아직 설명이 비어 있습니다.';
export const reportCompletedAt = '2026-09-01T15:20:00Z';
export const reportRepositoryNames = ['payment-service', 'project-a'];

/**
 * 면접에서 다뤄진 JD 요구사항 커버리지.
 * uncoveredRequirements 는 화면이 그대로 출력하므로 id가 아니라 text를 담는다.
 */
const uncoveredIds = [REQ_PAYMENT_DOMAIN, REQ_MONITORING];

export const reportCoverage: ReportCoverage = {
  totalRequirements: jdRequirements.length,
  coveredRequirements: jdRequirements.length - uncoveredIds.length,
  uncoveredRequirements: jdRequirements
    .filter((req) => uncoveredIds.includes(req.id))
    .map((req) => req.text),
};
