import type { JdRequirement } from '@/types/api';

/**
 * 공고에서 추출한 요구사항. `GET /analysis-runs/{runId}/result` 의 `jdRequirements`.
 * 계약상 최대 20개이며 category는 required / preferred / responsibility 3종이다.
 *
 * 레포 카드의 `matchedRequirementIds` 가 여기 있는 id를 가리킨다.
 * 둘이 어긋나면 RepoSelect 화면의 요구사항 매칭 표시가 조용히 비므로 함께 고쳐야 한다.
 */
export const REQ_BACKEND_API = '7a2b0000-0000-4000-8000-00000000000a';
export const REQ_CACHE = '7a2b0000-0000-4000-8000-00000000000b';
export const REQ_MESSAGING = '7a2b0000-0000-4000-8000-00000000000c';
export const REQ_PAYMENT_DOMAIN = '7a2b0000-0000-4000-8000-00000000000d';
export const REQ_PIPELINE = '7a2b0000-0000-4000-8000-00000000000e';
export const REQ_MONITORING = '7a2b0000-0000-4000-8000-00000000000f';

export const jdRequirements: JdRequirement[] = [
  {
    id: REQ_BACKEND_API,
    category: 'required',
    text: 'Java 또는 Kotlin으로 백엔드 API를 설계하고 운영한 경험',
    displayOrder: 1,
  },
  {
    id: REQ_CACHE,
    category: 'required',
    text: 'Redis 등 분산 캐시를 활용해 조회 성능을 개선한 경험',
    displayOrder: 2,
  },
  {
    id: REQ_MESSAGING,
    category: 'preferred',
    text: 'Kafka 등 메시지 큐 기반 비동기 처리 경험',
    displayOrder: 3,
  },
  {
    id: REQ_PAYMENT_DOMAIN,
    category: 'preferred',
    text: '결제·정산 도메인 업무 경험',
    displayOrder: 4,
  },
  {
    id: REQ_PIPELINE,
    category: 'responsibility',
    text: '결제 트랜잭션 처리 파이프라인 개발 및 운영',
    displayOrder: 5,
  },
  {
    id: REQ_MONITORING,
    category: 'responsibility',
    text: 'API 성능 모니터링과 장애 대응',
    displayOrder: 6,
  },
];

export const jdPosition = 'Backend Developer';
export const jdCompanyName = '테스트 기업';
