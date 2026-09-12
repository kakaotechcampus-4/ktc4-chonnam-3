# task-04 - L1 저장소 기본 분석

> 상태: 구현 가이드. `repo_shallow` runtime과 L1 callable은 아직 구현되지 않았다.
> 선행: [전체 순서](pipeline.md), [task-02 내부 계약](task-02-contracts.md), [task-03 LLM 경계](task-03-llm-boundary.md)

## 목표

검증된 L0-b 입력을 안정적인 repository 식별자로 대응하여 L1 프로젝트 요약 후보를 만든다. 유효한 batch 항목은 보존하고 실패 항목만 분리하며, 개인 기여 추정 없이 캐시 재사용 조건을 지킨다.

## 근거

- [저장소 분석](../../spec/ai/features/repository-analysis.md)의 `L1 배치 출력 검증`, `캐시와 재사용`, `실패와 검증`
- [AI 내부 계약](../../spec/ai/contracts.md)의 `task별 structured output 범위`, `Model Gateway와 실패`
- [AI 작업 Context](../../spec/ai/features/job-context.md)의 `Context Builder 입력`, `멱등성과 stale 결과`
- [0006 작업별 LLM 정책](../../spec/ai/decisions/0006-task-llm-usage-policy.md)의 `L1 요약과 저장 매핑`
- [0008 AI 후보 검증·선택 정책](../../spec/ai/decisions/0008-ai-candidate-policy.md)의 구조화 후보 실패
- [0001 기준선](../../spec/ai/decisions/0001-ai-baseline.md), [0002 vector 미도입](../../spec/ai/decisions/0002-sprint1-vector-search.md)
- [잔여 결정 목록](../../later.md)의 `AI-L03 변환·요약 version과 저장 매핑`, `AI-L04 실행 상한과 재시도 책임`

## 선행 조건

- 비식별 batch fixture, 안정 ID 대응, 부분 실패 분리와 캐시 판정은 실제 모델·저장 없이 구현할 수 있다.
- `repo_shallow_v1`의 정확한 schema는 AI-L02 채택 범위만 사용한다. 문서 후보 필드를 새 DTO로 먼저 고정하지 않는다.
- L1의 LLM 사용 방향과 프로젝트 기능·역할 요약 의미는 Accepted다. 실제 provider 연결은 AI-L01 뒤 수행한다.
- `role_summary` 이름과 DB/API 저장 매핑, deterministic metadata는 AI-L03의 AI·BE 합의 전 연결하지 않는다.
- 실패 item 재호출의 총 attempt와 batch budget은 AI-L04 결정 전 production 정책으로 만들지 않는다.

## 대상 파일과 책임

- [ai/src/devon_ai/llm_tasks/repo_shallow.py](../src/devon_ai/llm_tasks/repo_shallow.py): 주입된 prompt/model 경계로 단발 L1 후보 생성과 순수 결과 검증을 맡는다.
- [backend/app/llm_tasks/repo_shallow.py](../../backend/app/llm_tasks/repo_shallow.py): BE 입력·출력 adapter이며 prompt 로드, provider I/O, orchestration, 저장은 BE 책임으로 유지한다.
- [backend/app/features/analysis/pipeline/steps/repo_analyze.py](../../backend/app/features/analysis/pipeline/steps/repo_analyze.py): cache 조회, batch 실행, 부분 상태와 durable 저장을 소유한다.
- `ai/tests/llm_tasks/test_repo_shallow.py` (추가 예정, 현재 없음): 순수 L1 fixture와 batch 검증을 둔다.
- 추천 점수, JD 선행 순서, DB migration, 공개 RepositoryCard serialization은 이 작업에 포함하지 않는다.

## 작업

- [ ] 입력 batch의 각 항목에 service가 검증한 안정적인 repository 식별자와 대상 `head_sha`가 있는지 검사한다.
- [ ] 배열 순서가 아니라 repository 식별자로 요청과 결과를 일대일 대응한다.
- [ ] 알 수 없는 ID, 중복 ID, 누락 ID와 항목별 계약 오류를 서로 구분한다.
- [ ] 유효한 결과는 보존하고 잘못된 항목만 failed 후보로 분리한다.
- [ ] 전체 parse 실패, 읽을 수 있으나 구조를 어긴 schema 실패, 다른 repo/ref나 의미 범위를 어긴 semantic 실패를 구분한다.
- [ ] invalid 항목을 빈 성공·추측한 기본값·누락값 보충·ad hoc repair로 살리지 않는다.
- [ ] L1은 프로젝트 목적·주요 기능·확인한 기술과 분석 한계를 설명하고 L2 아키텍처 관찰을 생성하지 않는다.
- [ ] README 주장과 코드·metadata에서 확인된 사실을 구분하며 근거 없는 내용을 보충하지 않는다.
- [ ] README와 commit 수를 사용자 작성·개인 역할·기여량의 근거로 사용하지 않는다.
- [ ] 개인 기여가 확인되지 않으면 추측한 기본값이나 빈칸을 성공 값처럼 만들지 않는다.
- [ ] cache identity `(repository_id, analysis_level, head_sha, prompt_version)`를 그대로 검사한다.
- [ ] `model`은 결과 metadata로 다루되 cache identity에 추가하지 않는다.
- [ ] head SHA 또는 의미 있는 prompt 계약이 바뀌면 cache miss가 되며, model/출력 의미 변경 시 prompt version 갱신을 요구한다.
- [ ] Sprint 1에서 embedding, vector store, 전체 tree scan 또는 global search 의존성을 추가하지 않는다.
- [ ] raw output 보존이 필요하면 AI-L18 승인 경계로 넘기고 일반 로그에 사용자 자료를 출력하지 않는다.

## 검증

- [ ] 정상 batch, 결과 순서 변경, 일부 누락, 중복·미등록 ID, 한 항목 오류 fixture를 검사한다.
- [ ] 한 항목 실패가 다른 유효 결과를 폐기하거나 전체 성공으로 숨기지 않는지 확인한다.
- [ ] 같은 SHA/version cache hit와 head SHA·prompt version 변경 cache miss를 확인한다.
- [ ] 프로젝트 요약이 개인 기여를 생성하지 않고 확인 한계를 보존하는지 금지 결과 fixture로 검사한다.
- [ ] timeout과 parse/schema/semantic 실패가 task-03의 fake 경계에서 구분되는지 확인한다.
- [ ] 유효 항목과 semantic 실패 항목이 함께 있어도 유효 항목만 보존하고 실패 항목에 default를 만들지 않는지 확인한다.
- [ ] 계획 테스트를 추가한 뒤 [테스트 안내](testing.md)의 단위·type·import boundary 검사를 실행한다.
- [ ] BE 저장 연결 검사는 PostgreSQL 기준으로 별도 수행하고 mock 성공을 cache·partial 상태 저장 완료로 보고하지 않는다.

## 완료 조건

- [ ] 안정 ID batch 대응, 부분 성공 보존, 캐시 판정이 결정론적 fixture로 검증된다.
- [ ] L1 결과가 프로젝트 설명과 개인 기여를 명확히 구분한다.
- [ ] 채택되지 않은 출력 필드·저장 매핑·retry budget을 구현하지 않는다.
- [ ] 실제 provider, BE durable 저장과 분석 API 조회가 검증되기 전 L1 production 완료로 보고하지 않는다.

## 결정 대기와 재개 조건

- AI-L03의 Accepted 의미 정책에 따라 개인 기여 없는 프로젝트 요약 검사는 즉시 진행한다. AI·BE가 필드명, 저장/API 매핑과 version·출처 metadata를 기록하면 durable 저장 연결을 재개한다.
- ADR 0008의 실패 분류와 fail-closed batch 검사는 즉시 구현한다. AI-L04에서 실패 item·semantic 실패의 재호출 여부, 총 attempt, 관리 계층과 소진 처리가 승인되면 production 재시도를 재개한다.
- AI-L02가 일부 출력만 채택하면 그 범위만 구현한다. 미승인 저장 매핑이 순수 batch 검증을 막지는 않는다.
