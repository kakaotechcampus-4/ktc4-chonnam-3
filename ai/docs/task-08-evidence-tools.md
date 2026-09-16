# task-08 - 제한 Evidence Tool

상태: 구현 가이드. 추가 조회·결과 해석 정책은 승인됐지만 Tool runtime과 실제 I/O는 아직 구현되지 않았다.

## 목표

- Director가 사용하는 Tool 요청과 결과 해석을 [AI tools 모듈](../src/devon_ai/agents/director/tools.py)에 구현한다.
- 추가 조회의 세 조건과 네 결과 분류를 결정적 정책으로 검증한다.
- 실제 권한 검사·GitHub I/O·DB 저장은 BE adapter 책임으로 유지한다.
- Sprint 1 제한 검색을 지키고 vector·전체 tree·global search로 확장하지 않는다.

## 근거

- [Evidence Retriever의 입력·Tool 경계와 결과 상태](../../spec/ai/features/evidence-retrieval.md)
- [0003 추가 근거 조회와 결과 해석 결정](../../spec/ai/decisions/0003-evidence-lookup-policy.md)
- [0008 AI 후보 검증·선택 정책](../../spec/ai/decisions/0008-ai-candidate-policy.md)의 Evidence 후보 우선순위
- [0009 AI 평가 방법과 비교 실험](../../spec/ai/decisions/0009-ai-evaluation-method.md)의 검색 실패 원인 분리·통제 비교
- [0002 Sprint 1 vector 검색 미도입 결정](../../spec/ai/decisions/0002-sprint1-vector-search.md)
- [AI 내부 계약의 Evidence·ToolResult 제안](../../spec/ai/contracts.md)
- [작업 Context의 Evidence 최소화와 보호](../../spec/ai/features/job-context.md)
- [잔여 결정 목록의 AI-L02·AI-L04·AI-L08·AI-L12](../../later.md)

## 선행 조건

- [전체 AI pipeline](pipeline.md), [task-02 내부 계약](task-02-contracts.md), [task-05 L2 분석](task-05-repo-deep.md)을 확인한다.
- [task-06 Context 준비](task-06-context-preparation.md)가 선택 repo와 고정 `snapshot_head_sha`를 검증해 주입해야 한다.
- 승인된 정책 로직과 단일 파일/ref/권한 fixture는 운영 상한 합의 전에도 진행할 수 있다.
- 실제 Tool 연결은 AI-L02·AI-L04·AI-L08의 계약과 운영값이 정해진 뒤 진행한다.

## 대상 파일과 책임

- [AI Evidence tools](../src/devon_ai/agents/director/tools.py): 요청 판단과 반환 의미를 소유하며 현재 docstring뿐이다.
- [AI 계약 자리](../src/devon_ai/contracts.py): 채택 후 Tool 요청·결과 타입을 두며 현재 미구현이다.
- [BE Tool adapter](../../backend/app/agents/director/tools.py): 권한·repo/ref/path 재검증과 실제 I/O를 소유한다.
- [BE GitHub client](../../backend/app/integrations/github/client.py): 승인된 adapter가 사용할 외부 접근 경계다.
- [BE 면접 준비](../../backend/app/features/interview/prepare.py): 사전 L2 Evidence와 Tool 산출물을 구분한다.
- service/queries는 durable Evidence·Turn usage·`answer_vs_code` 저장과 중복 방지를 소유한다.

## 작업

- [ ] 기존 근거만으로 주장을 확인할 수 없는지를 첫 번째 조회 조건으로 검사한다.
- [ ] 확인 결과가 현재 질문·후속 질문·평가에 영향을 주는지를 두 번째 조건으로 검사한다.
- [ ] 선택 repo의 고정 SHA·허용 경로에서 확인 가능한지를 세 번째 조건으로 검사한다.
- [ ] 세 조건이 모두 참일 때만 Tool 요청 후보를 만들고 각 조건이 거짓인 미조회 사유를 남긴다.
- [ ] 조회가 필요하면 관련 기존 Evidence·수집 원문, 정확히 알려진 파일, BE가 사전 검증한 인접 후보 순으로 제안한다.
- [ ] 같은 단계에서는 주장 종류에 직접 맞는 source와 더 좁고 명확한 확인 범위를 우선한다.
- [ ] 요청의 repo/ref/path를 신뢰하지 않고 BE가 Context와 다시 대조하도록 한다.
- [ ] traversal, 외부 URL·redirect, 다른 사용자 repo, 원격 최신 branch ref를 거절한다.
- [ ] `read_file`은 허용된 단일 파일, `list_commits`는 고정 ref와 일관된 metadata로 제한한다.
- [ ] `search_code` 이름을 전체 GitHub 검색이나 전역 keyword search 허가로 해석하지 않는다.
- [ ] README, metadata, languages, commit metadata, notable area 주변이라는 Sprint 1 범위를 유지한다.
- [ ] notable area가 디렉터리면 합의된 열거 방식 없이 `read_file`하거나 재귀 탐색하지 않는다.
- [ ] AI가 인접 후보를 새로 열거하지 않고 BE가 supplied allowed scope로 준 후보만 사용한다.
- [ ] 미조회와 정상 조회 후 미발견을 분리한다.
- [ ] 정상 미발견은 `unverified`, 분석 부족과 Tool 장애는 감점 없는 검증 불가로 해석한다.
- [ ] 실제 코드 불일치는 버전·조건을 확인할 중립 후속 질문이 필요한 충돌 후보로 둔다.
- [ ] `found`도 주장 사실성·개인 기여를 자동 확정하지 않고 원문과 관계를 별도 판단한다.
- [ ] repo, git ref, 실제 path/metadata 위치, 원문, 조회 방법, 한계를 보존한다.
- [ ] 원문에 없는 함수명·줄 번호·인용문을 생성하지 않는다.
- [ ] `question_basis`와 `evaluation_basis`를 구분하고 같은 근거의 두 용도를 허용한다.
- [ ] 코드 실행·수정, Private repo 조회, embedding/vector 저장소 의존성을 추가하지 않는다.
- [ ] 숫자 상한 미정을 무제한 조회로 바꾸지 않고 실제 I/O는 차단된 상태로 둔다.

## 검증

- 예정 테스트: `ai/tests/agents/director/test_evidence_tools.py` (추가 예정, 현재 없음).
- [ ] 세 조건 모두 참인 사례와 조건별 하나씩 거짓인 세 사례를 대조한다.
- [ ] 이미 있는 직접 근거, 정확한 파일, 사전 검증된 인접 후보의 우선순위와 source 적합성을 검사한다.
- [ ] 미조회, `not_found`, `insufficient_analysis`, `tool_error`, 실제 불일치를 구분한다.
- [ ] 잘못된 ref, 무관한 유사 파일, 다른 사용자 repo, traversal, 외부 지시 README를 거절한다.
- [ ] path가 같아도 ref가 다르면 같은 Evidence로 채택하지 않는지 검사한다.
- [ ] Tool 성공과 claim 지지, commit 존재와 개인 기여가 분리되는지 검사한다.
- [ ] 실패 결과가 거짓 주장·벌점·자동 `resolution`으로 바뀌지 않는지 검사한다.
- [ ] mock adapter 성공은 실제 GitHub 권한·rate limit·저장 통합 검증을 대신하지 않는다.
- [ ] 검색 비교에서는 권한 거부, 잘못된 ref, parser 실패, Tool 실패, source 부재를 검색 방법 결함과 분리한다.
- [ ] baseline과 candidate는 task-12의 같은 사례·source group에서 한 요인만 바꾸고 범위 확대 실험은 사전 승인 뒤 수행한다.

## 완료 조건

- [ ] 조회 요청 판단과 네 결과 의미가 승인된 정책대로 재현된다.
- [ ] 후보 우선순위가 불필요한 새 조회나 허용 범위 자동 확장 없이 재현된다.
- [ ] 허용 repo/ref/path 밖의 요청이 AI와 BE 경계에서 차단된다.
- [ ] 출처 위치·원문·한계를 검증하지 않은 결과가 질문이나 평가 근거가 되지 않는다.
- [ ] 실제 I/O·저장·중복 방지와 정책 로직의 소유권이 분리된다.
- [ ] vector·전체 tree·global search·임의 운영 상한이 추가되지 않는다.
- [ ] ADR 0009의 비교 방법 적용을 검색 범위·vector·인프라 채택이나 출시 승인으로 해석하지 않는다.

## 결정 대기와 재개 조건

- AI-L08: 디렉터리 열거·인접 후보 생성, 실제 Tool I/O, 주변 범위·깊이·개수와 byte/token/time 상한이 합의되면 제한 검색을 연결한다.
- AI-L02: Tool 요청·결과·Evidence의 필드, enum, null, version, 저장 참조가 채택되면 타입과 serializer를 고정한다.
- AI-L04: 호출 budget·timeout·재시도 주체와 소진 처리가 정해지면 runtime loop를 연결한다.
- AI-L12: Evidence/conflict의 중복 키와 transaction·재실행 정책이 정해지면 durable 저장 완료를 검증한다.
- Sprint 2 검색 확장은 실제 실패 기록과 별도 결정 전에는 이 작업에 포함하지 않는다.
- AI-L20·AI-L26: 통제 비교 결과가 있어도 후속 검색 범위·vector·모델 전략은 별도 승인 뒤에만 재개한다.
