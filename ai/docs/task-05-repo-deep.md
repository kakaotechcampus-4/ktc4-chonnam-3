# task-05 - L2 저장소 정밀 분석

> 상태: 구현 가이드. `repo_deep` runtime과 L2 callable은 아직 구현되지 않았다.
> 선행: [전체 순서](pipeline.md), [task-02 내부 계약](task-02-contracts.md), [task-03 LLM 경계](task-03-llm-boundary.md), [task-04 L1 분석](task-04-repo-shallow.md)

## 목표

BE가 선택한 primary 저장소의 고정 SHA와 허용 원문만 사용해 L2 아키텍처 관찰 후보를 만든다. `notable_areas`의 실제 path와 확인 범위를 검증하고, 부분 결과를 면접 준비 성공으로 승격하는 조건은 별도 결정에 맡긴다.

## 근거

- [저장소 분석](../../spec/ai/features/repository-analysis.md)의 `분석 단계`, `캐시와 재사용`, `실패와 검증`
- [AI 작업 Context](../../spec/ai/features/job-context.md)의 `Context Builder 입력`, `Evidence 최소화와 보호`, `멱등성과 stale 결과`
- [AI 내부 계약](../../spec/ai/contracts.md)의 `task별 structured output 범위`, `Evidence와 ToolResult 제안`
- [0001 기준선](../../spec/ai/decisions/0001-ai-baseline.md), [0002 vector 미도입](../../spec/ai/decisions/0002-sprint1-vector-search.md), [0006 작업별 LLM 정책](../../spec/ai/decisions/0006-task-llm-usage-policy.md)
- [0008 AI 후보 검증·선택 정책](../../spec/ai/decisions/0008-ai-candidate-policy.md)의 L2 관찰 근거 범위
- [잔여 결정 목록](../../later.md)의 `AI-L06 L2 부분 결과의 준비 성공·지원 범위 계약`, `AI-L08 제한 검색의 실행 범위와 운영 계약`
- [근거 검색](../../spec/ai/features/evidence-retrieval.md)의 Sprint 1 허용 경로와 ref 제한

## 선행 조건

- 고정 SHA, 단일 파일 path, 유효·무효 notable area와 부분 결과 fixture는 실제 GitHub·모델 없이 구현할 수 있다.
- L2 입력·출력의 정확한 필드는 AI-L02에서 채택된 범위만 사용하며 Proposed 구조를 새 schema로 먼저 고정하지 않는다.
- L2는 기존 LLM 사용 방향을 유지하지만 실제 provider 연결은 AI-L01, 실행 budget은 AI-L04 결정 뒤 수행한다.
- 일부 notable area가 무효일 때 준비 성공으로 볼지는 AI-L06 전 확정하지 않는다.
- 사용 가능·제한·무효 관찰의 의미 정책은 Accepted이며 readiness·repo 상태 매핑과 지원 기능 목록만 AI-L06에 남는다.
- directory path의 열거 깊이·개수·byte/token/time 상한은 AI-L08 결정 전 production 조회로 연결하지 않는다.

## 대상 파일과 책임

- [ai/src/devon_ai/llm_tasks/repo_deep.py](../src/devon_ai/llm_tasks/repo_deep.py): 주입된 L1·허용 원문으로 단발 L2 후보를 만들고 순수 의미 검증을 수행한다.
- [backend/app/llm_tasks/repo_deep.py](../../backend/app/llm_tasks/repo_deep.py): prompt/provider/저장 orchestration을 맡는 BE adapter다.
- [backend/app/features/analysis/pipeline/deep_analysis.py](../../backend/app/features/analysis/pipeline/deep_analysis.py): 선택·primary 범위 확인, 고정 ref 입력과 L2 저장을 소유한다.
- [backend/app/features/interview/prepare.py](../../backend/app/features/interview/prepare.py): 검증된 L2 결과의 준비 상태와 pre-analysis evidence 전개를 소유한다.
- `ai/tests/llm_tasks/test_repo_deep.py` (추가 예정, 현재 없음): 고정 ref, path, 분석 범위와 부분 결과 fixture를 둔다.

## 작업

- [ ] service가 검증한 선택 저장소와 primary 범위만 입력으로 받고 AI가 selection을 바꾸지 않게 한다.
- [ ] 분석 대상 `head_sha`와 면접의 `snapshot_head_sha`를 명시적으로 대조한다.
- [ ] 원격 기본 branch 최신값이나 서비스 코드 commit으로 고정 ref를 대체하지 않는다.
- [ ] 현재 고정 SHA에서 허용된 L1 결과와 파일 원문만 L2 입력으로 사용한다.
- [ ] architecture 관찰, 확인한 기술, notable area와 분석 범위를 원문 확인 수준에 맞게 제한한다.
- [ ] 고정 SHA의 실제 source가 주장을 뒷받침하면 사용 가능, source는 유효하지만 해석이 부족하면 확인 가능한 관찰과 한계를 함께 남긴다.
- [ ] 잘못된 ref/path, 읽지 않은 source, 읽은 범위를 넘은 언어 동작·아키텍처 추론은 무효로 분리한다.
- [ ] L2 후보의 parse/schema/semantic 실패를 구분하고 무효 관찰을 빈 성공·추측값·ad hoc repair로 바꾸지 않는다.
- [ ] notable area는 기존 1~5개 범위를 유지하고 각 항목을 실제 파일 또는 디렉터리 path에 연결한다.
- [ ] 존재하지 않는 path, 다른 SHA의 path, 허용 범위 밖 path와 근거 없는 함수·줄 위치를 거부한다.
- [ ] 단일 파일 path는 승인된 source access 결과로 검증하고 읽은 범위와 미확인 부분을 남긴다.
- [ ] directory path는 AI-L08 상한 승인 전 자동 재귀·전체 tree·global keyword search로 확장하지 않는다.
- [ ] 사용 가능·제한·무효 notable area를 분리하되 subset을 준비 성공으로 처리하지 않고 AI-L06 판정 입력으로 넘긴다.
- [ ] notable area가 없거나 검증된 path가 없으면 L2 준비 성공이나 Evidence 출발점으로 사용하지 않는다.
- [ ] run의 일반 partial과 필수 L2 미완료로 인한 `preparing_failed` 후보를 구분한다.
- [ ] cache는 분석 level, 고정 SHA, prompt version이 맞는 결과만 재사용하고 진행 중 면접의 ref를 바꾸지 않는다.
- [ ] Sprint 1에 embedding/vector, Private repo, 전체 snapshot 복원 또는 범위 자동 확대를 추가하지 않는다.

## 검증

- [ ] 올바른 고정 SHA와 stale/다른 SHA 입력을 대조해 잘못된 ref가 결과에 섞이지 않는지 확인한다.
- [ ] 실제 파일, 실제 디렉터리, 없는 path, 범위 밖 path와 path traversal 후보 fixture를 검사한다.
- [ ] notable area 없음, 전부 무효, 제한 관찰, 일부 사용 가능, 모두 사용 가능 결과를 분리해 readiness 결정을 대신하지 않는지 확인한다.
- [ ] 지원 기능이 확인되지 않은 언어 source에서 실행 동작이나 아키텍처를 추론하지 않는지 검사한다.
- [ ] 구조는 맞지만 ref/path·source 범위를 위반한 후보를 semantic 실패로 거절하는지 검사한다.
- [ ] 허용된 1~5개 범위, 중복 path와 분석 한계 표현을 검사한다.
- [ ] directory fixture가 운영 상한 없이 재귀 조회나 global search를 시작하지 않는지 확인한다.
- [ ] 계획 테스트를 추가한 뒤 [테스트 안내](testing.md)의 단위·type·import boundary 검사를 실행한다.
- [ ] BE 통합에서는 고정 SHA 조회, durable 저장, 준비 상태와 evidence 전개를 따로 검증하고 mock을 실제 GitHub/model 성공으로 보고하지 않는다.

## 완료 조건

- [ ] 모든 채택된 L2 관찰이 고정 SHA, 실제 path와 확인 범위로 추적된다.
- [ ] 무효 path와 부분 결과가 승인 없이 면접 준비 완료 또는 evidence로 승격되지 않는다.
- [ ] directory 조회 상한, readiness 기준과 저장 계약의 미결정을 숨기지 않는다.
- [ ] 실제 provider·GitHub·BE 준비 흐름 검증 전 L2 production 완료로 보고하지 않는다.

## 결정 대기와 재개 조건

- ADR 0008의 사용 가능·제한·무효 관찰 fixture는 즉시 구현한다. AI-L06에서 지원 언어·parser·읽기 capability와 부분 관찰의 readiness, repo 상태/`preparing_failed` 매핑을 기록하면 준비 완료 연결을 재개한다.
- AI-L08 전에는 고정 ref의 단일 파일 검증과 directory 무확장 정책을 진행한다. AI·BE가 파일 열거 방식, 주변 범위·깊이·개수·byte/token/time 상한을 승인하면 directory 조회를 재개한다.
- AI-L02·L04·L18의 계약, budget, 원문 보존 결정이 필요한 부분만 대기하며 고정 SHA/path 정책 fixture 검증은 계속한다.
