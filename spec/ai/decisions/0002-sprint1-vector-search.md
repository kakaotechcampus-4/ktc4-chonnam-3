# 0002 Sprint 1 vector 검색 미도입

- 상태: Accepted, AI의 Sprint 1 검색 전략에 한함
- 날짜: 2026-09-12
- 관련 PR: 없음
- 검토자: 현재 사용자 승인
- 연결 항목: [later.md의 AI-L20](../../../later.md)

## 맥락

[ForAI 1](../../../ForAI.md)과 [공통 계약 이관표](../../shared/contracts/migration.md)는 실제 vector 검색 필요 여부를 AI 파트 검토로 남겼다. 기존 Sprint 1 범위는 README, repository metadata, languages, commit metadata, L2 notable area 주변 파일을 이용하며 vector 없이 동작해야 한다.

현재 도입 필요성을 입증한 실제 검색 품질·비용·지연 측정 결과는 없다. 사용자는 Sprint 1 미도입, extension 선설치 없음, 실제 실패 사례를 통한 Sprint 2 재평가 방향을 승인했다.

## 결정

1. Sprint 1 AI 기능에는 embedding 생성·vector 검색을 도입하지 않는다. repo 추천, L2 준비, 면접 질문·답변 검증, 리포트·프로필에 vector 의존성을 추가하지 않는다.
2. pgvector extension만 미리 설치하는 방안도 채택하지 않는다. 이 방향을 BE 전달사항으로 기록하며, 이 문서가 migration 적용·배포 확인을 대신하지 않는다.
3. 기존 제한 검색 범위를 유지한다. 전체 tree scan·global code search·Private repo 조회로 대체하거나 확장하지 않는다.
4. 실제 제한 검색에서 필요한 근거를 찾지 못한 사례와 분석 부족·도구 실패를 구분해 기록한다. 입력/ref, 확인한 범위, 기대 근거, 질문·평가에 미친 영향, 가능한 범위의 비용·지연을 함께 검토한다.
5. Sprint 2에서 이 기록을 바탕으로 vector가 필요한 문제인지 재평가한다. 재평가는 도입 확정이나 자동 구현 승인이 아니다.

## 대안과 선택 이유

- Sprint 1에 vector를 도입하는 안: 현재 측정 결과만으로 필요성을 입증할 수 없으며 기존 필수 범위가 아니다.
- extension만 선설치하는 안: 실제 소비 기능·embedding 설계가 정해지지 않은 상태에서 도입하는 근거가 부족하다.
- Sprint 1 미도입 후 재평가하는 안: 현 범위 안에서 동작을 검증하고, 실제 실패 원인을 바탕으로 후속 투자 여부를 정할 수 있어 채택한다.

이 선택은 기존 검색 품질이 충분하다는 성능 결론이 아니다. 품질은 실제 사례로 별도 검증한다.

## BE 전달사항과 반영 상태

- 전달할 내용: Sprint 1 pgvector extension·vector 전용 column/index·embedding job·별도 vector store를 선행 요구사항으로 추가하지 않는다.
- 영향 문서: `ForAI.md` 1장, `spec/shared/contracts/migration.md`, `spec/backend/architecture.md`, `backend/docs/db-schema.md`의 pgvector 보류 항목.
- 상태: AI 결정 기록 완료. BE 담당자 전달·확인, 공유/BE 문서 갱신과 실제 migration 검토는 대기다. 실제 담당자의 승인이나 전달 완료를 추정하지 않는다.
- 기존 문서의 `PENDING_AI`는 이 결정 이전의 검토 요청 기록이다. 현재 AI 구현의 Sprint 1 검색 전략은 이 결정을 따르되, BE·공유 계약의 상태를 자동으로 `FIX` 처리하지 않는다.
- 이미 존재하는 DB extension·데이터·인덱스를 자동 삭제하거나 rollback하라는 지시는 아니다. 실제 환경과 migration은 BE가 확인한다.

## 남은 결정

- Sprint 2 vector 도입 여부와 필요한 task, 도입을 판단할 품질·비용·지연 기준.
- embedding model, dimension, chunk 단위, 재색인 기준, pgvector 또는 별도 저장소, schema·index·migration.
- full tree/global search 확장 여부와 시점. vector 선택과 별개로 검토한다.
- AI-L08의 추가 조회 조건·`unverified` 세부 정책, 파일 열거·byte/token/time 상한.

위 항목은 미정으로 유지한다. 이번 승인으로 다른 AI-L 항목을 완료 처리하지 않는다.

## 검증과 변경

구현 시 embedding 호출·vector store 없이 Sprint 1 경로를 검증하고, 제한 검색 실패가 자동 범위 확장으로 이어지지 않는지 확인한다. BE는 migration에 vector 선설치가 없는지 별도로 검토한다. 이 문서 작성은 테스트·모델 평가·배포 완료를 뜻하지 않는다.

방향을 바꾸려면 실제 실패 사례와 비교 결과를 근거로 후속 결정을 남기고 BE·공유 계약 영향을 검토한다.

## 대체 관계

[0001 AI 구현 기준선](0001-ai-baseline.md)의 pgvector 관련 보류 중 Sprint 1 도입 여부만 후속 결정으로 대체한다(부분 Superseded). 0001의 다른 기준과 과거 기록은 유지하며, Sprint 2 검색 세부는 계속 [later.md](../../../later.md)에서 추적한다.
