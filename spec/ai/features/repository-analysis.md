# 저장소 분석

상태: Sprint 1 FIX 기준. Wanted LLM 비호출·L1 요약 의미는 0006, 후보 실패와 L2 관찰 범위는 0008에서 Accepted. 저장·version·준비 상태 등 구현 세부는 Proposed.

이 문서는 Public GitHub 저장소의 수집, 기본 분석, 정밀 분석, 추천 입력을 정의한다. 공통 AI 경계는 [계약](../contracts.md), [아키텍처](../architecture.md), [검증](../verification.md), [기준 결정](../decisions/0001-ai-baseline.md)을 함께 따른다. 충돌 시 `spec/shared/contracts/openapi.yaml`과 `spec/backend/`가 우선한다.

## 범위와 금지

- Sprint 1은 로그인 사용자가 접근할 수 있는 Public 저장소만 처리한다. Private 저장소는 필드가 있어도 수집, 분석, 추천, 면접 선택 대상이 아니다.
- 분석은 확인한 GitHub 원문과 메타데이터의 범위만 설명한다. 코드의 존재를 사용자의 작성, 기여, 운영 성능 또는 배포 성공으로 바꾸어 말하지 않는다.
- 공고는 Wanted URL이 필수다. 공고 없이 진행하거나 다른 사이트의 내용을 추측하지 않는다.
- 선택 문서는 선택 입력이다. Sprint 1에서는 추출한 GitHub URL만 후보 신호로 사용하고 Claim을 만들지 않는다.
- [0002 결정](../decisions/0002-sprint1-vector-search.md)에 따라 Sprint 1에는 embedding/vector 검색을 도입하지 않는다. pgvector extension 선설치 없이 기존 분석·추천 경로를 구현하며, BE 반영 확인과 Sprint 2 도입 여부·모델·차원·chunk·migration은 별도 대기로 남긴다.

근거: [분석 Run](../../backend/features/analysis-run.md), [면접](../../backend/features/interview.md), [문서](../../backend/features/documents.md), [백엔드 DB 기준](../../../backend/docs/db-schema.md), [AI 검토 사항](../../../ForAI.md).

## 분석 단계

| 수준 | 대상과 시점 | 최소 입력 | 결과와 제한 |
| --- | --- | --- | --- |
| `L0-a` | GitHub 연동 직후 전체 Public 저장소 | 저장소 식별자, 공개/접근 상태, fork/archive 여부, 크기, 주 언어, 활동 메타데이터 | lightweight filter와 `base_rank`. 제외 대상도 사유와 함께 저장한다. LLM을 호출하지 않는다. |
| `L0-b` | 분석할 candidate batch | 저장소 식별자, README, languages, head SHA, commit 수, 사용자 commit 수 | L1과 추천에 사용할 상세 원문. 조회 실패와 내용 없음은 구분한다. |
| `L1` | candidate batch의 기본 분석 | L0-b 결과, `repo_shallow` prompt 문자열과 version | 프로젝트 유형, 확인된 기술, 요약과 분석 한계. `architecture_summary`는 만들지 않는다. |
| `L2` | 면접 대상으로 확정된 저장소 중 primary 1~2개 | 고정 head SHA의 허용 원문, L1 결과, `repo_deep` prompt 문자열과 version | 아키텍처 관찰과 `notable_areas` 1~5개. 각 항목은 실제 파일 또는 디렉터리 path와 확인 범위를 포함한다. |

사용자는 한 면접에서 저장소 1~5개를 선택할 수 있다. `interview_prep`은 그중 primary 저장소 1~2개를 정하고 L2를 준비한다. 모든 선택 저장소를 균등하게 질문하기보다 primary 저장소에서 재조회 가능한 근거를 확보하는 것이 우선이다.

`L0-a`, `L0-b`, `L1`, `L2`는 분석의 깊이이며 API `StepKey`가 아니다. 외부 진행 상태는 다음 7개 key를 그대로 사용한다.

```text
doc_extract -> repo_select -> repo_detail -> jd_fetch -> jd_extract -> repo_analyze -> match_score
```

### 단계 순서 보류

상태: Proposed, BE 파이프라인 검토 필요. 공통 API에 새로운 상태값을 추가하는 뜻은 아니다.

첫 candidate batch 규칙은 JD 신호를 사용할 수 있다고 되어 있으나, 고정된 표시 순서에서는 `repo_select`가 `jd_fetch`와 `jd_extract`보다 먼저다. 구현자는 이 모순을 숨기기 위해 step key를 임의로 재배열하거나 아직 없는 JD 신호를 생성하면 안 된다. 다음 중 하나를 백엔드 계약 결정으로 확정한 뒤 구현한다.

- 실제 JD 확보를 먼저 수행하되 외부 7개 key의 의미와 진행률 규칙을 별도로 정의한다.
- 첫 batch의 `jd_signal` 몫을 사용하지 않고, JD 확보 뒤 후속 page/ranking에만 적용한다.
- 7개 step의 순서 자체를 계약 migration으로 변경한다.

결정 전 테스트는 현재 불일치를 명시적으로 보류하고, JD 신호를 사용했다고 보고하지 않는다.

## Wanted 요구사항

Wanted의 구조화 필드를 원문으로 사용한다. `jd_requirements.requirement_type`은 다음 값만 사용한다.

- `required`
- `preferred`
- `unknown`

이 계약에서 `responsibility`를 새 enum 값으로 만들지 않는다. 담당 업무를 별도로 보존해야 하면 기존 Wanted 원문 위치와 데이터 모델 안에서 표현하며, schema 변경은 백엔드 승인을 받는다. `tech_tags`는 Wanted `skill_tags`에서 가져오며 LLM이 누락된 태그를 추측해 채우지 않는다.

[0006 결정](../decisions/0006-task-llm-usage-policy.md)에 따라 Sprint 1 Wanted-only 분류는 구조화 필드를 규칙으로 변환하며 LLM을 호출하지 않는다. `jd_extract` 단계와 검증·저장은 유지하고 수집/추출 실패를 LLM 추측으로 메우지 않는다. `jd_extract_v1`은 기존 prompt version 목록에 남기며 deterministic 변환 version·출처 기록의 실제 저장 방식은 AI·BE 검토사항이다. prompt version을 다른 종류의 버전 필드로 재정의하거나 비호출 작업을 LLM 실행으로 기록하지 않는다.

근거: [DB 스키마의 Wanted 결정](../../../backend/docs/db-schema.md), [현재 JD task 경계](../../../backend/app/llm_tasks/jd_extract.py), [Prompt seed 요구](../../../backend/docs/task-03-seed.md).

## L1 배치 출력 검증

상태: Proposed. `repo_shallow_v1`의 구체 JSON Schema는 [AI 계약](../contracts.md) 승인 뒤 고정한다.

0006에서 승인한 L1 요약 의미는 프로젝트의 기능·역할과 확인 한계다. README·commit 수로 사용자의 개인 기여를 추정하지 않는다. `role_summary`의 필드명·저장/API 매핑은 BE와 별도 합의하며, 기존 개인 역할 필드를 임의로 프로젝트 요약으로 재해석하지 않는다. L1/L2의 기존 LLM 사용 방향은 유지한다.

배치 요청의 각 항목에는 내부 순서가 아닌 안정적인 repository 식별자를 넣는다. 출력 검증은 다음을 지킨다.

1. 요청한 식별자와 결과 식별자를 대조한다.
2. 알 수 없는 식별자, 중복 식별자, 누락 식별자, 항목별 schema 오류를 각각 기록한다.
3. 유효한 항목은 보존하고 잘못된 항목만 `failed`로 처리한다. 한 항목의 오류로 전체 batch 결과를 폐기하지 않는다.
4. 모델 출력의 배열 순서를 repository 대응 근거로 사용하지 않는다.
5. 깨진 전체 JSON은 공통 LLM 규칙에 따라 한 번만 재시도한다. 두 번째 실패 결과는 downstream에 전달하지 않는다.
6. 허용된 저장 위치에 raw output, 실제 model 문자열, prompt version, token 사용량과 latency를 남긴다. 비밀키나 GitHub token은 남기지 않는다.

[0008 결정](../decisions/0008-ai-candidate-policy.md)에 따라 전체 parse 실패, 항목의 schema 실패와 안정 식별자·근거·범위를 어긴 semantic 실패를 구분한다. invalid 항목을 빈 성공이나 추측한 기본값으로 보충하지 않으며 유효 항목은 보존한다. semantic 실패의 실제 재호출과 attempt 계산은 이 정책이 정하지 않는다.

`repo_shallow_v1`과 `repo_deep_v1`은 서로 다른 prompt version이다. 모델이나 의미 있는 출력 계약을 바꿔 기존 결과를 재사용할 수 없게 되면 해당 task의 prompt version을 올린다.

## 캐시와 재사용

`repo_analyses`의 재사용 identity는 다음 UNIQUE 계약을 따른다.

```text
(repository_id, analysis_level, head_sha, prompt_version)
```

`model`은 결과에 저장하지만 UNIQUE에는 넣지 않는다. 따라서 provider, model 또는 출력 의미가 바뀌어 캐시를 분리해야 할 때는 prompt version을 올려야 한다. 분석 대상 SHA와 다르면 캐시를 사용하지 않는다. 이미 준비한 면접은 `snapshot_head_sha`를 유지하므로, 원격 기본 branch에 새 push가 생겼다는 이유만으로 면접 중 분석과 근거를 교체하지 않는다. 별도의 전체 저장소 snapshot·복원 기능은 만들지 않는다.

L2의 `notable_areas`가 없거나 path가 해당 분석의 고정 SHA에서 확인되지 않으면 L2 준비 성공으로 처리하지 않는다. 실패와 검증 한계를 남기고 해당 항목을 Evidence Retriever의 출발점으로 넘기지 않는다. 분석 run의 partial과 필수 L2가 미완료인 면접의 `preparing_failed`를 구분한다. 유효한 일부 항목만으로 준비 성공을 허용할 조건은 AI·BE 검토 대상이다.

0008에 따라 L2 관찰은 고정 SHA의 실제 source와 읽은 내용이 주장을 뒷받침할 때만 사용한다. source는 유효하지만 언어·도구 기능이나 읽은 범위가 부족하면 확인 가능한 관찰과 한계를 함께 남기며, 읽지 않은 경로의 동작·아키텍처를 추론하지 않는다. 사용 가능한 관찰과 제한되거나 무효인 관찰은 구분하되 지원 언어·parser 목록, 정확한 필드와 일부 결과의 준비 성공 여부는 계속 AI·BE 검토 대상이다.

근거: [기획 결정](../../../report.md), [AI L1 task 골격](../../../ai/src/devon_ai/llm_tasks/repo_shallow.py), [AI L2 task 골격](../../../ai/src/devon_ai/llm_tasks/repo_deep.py). 기존 BE task 파일은 연결 경계로 남으며 수집·저장은 BE가 맡는다.

## 추천

추천은 JD와 유효한 L1 결과를 비교한 설명 가능한 결과다. API에는 최대 5개만 AI 추천으로 표시하고, 사용자가 선택할 수 있는 저장소도 최대 5개다.

- `matchScore`, 추천 여부, 추천 이유, 연결한 requirement 식별자를 같은 결과로 관리한다.
- 추천 이유는 실제 JD requirement와 분석에서 확인한 저장소 정보만 사용한다.
- 분석 대기 또는 실패를 낮은 적합도로 변환하지 않는다.
- match score 공식과 scale은 아직 고정되어 있지 않다. 임의의 `0`, 기본 점수 또는 근거 없는 백분율을 저장하거나 반환하지 않는다.
- 공개 RepositoryCard의 `matchScore`는 optional/nullable다. 산식이 아직 없으면 미계산 상태를 이 계약 범위에서 표현할 수 있다. FE가 필수 정렬·표시에 사용하는 조건과 내부 저장 정책은 BE·FE와 맞추고, 존재하지 않는 점수를 만들어 성공시키지 않는다. 리포트의 필수 number 계약과 혼동하지 않는다.
- vector 검색이 없어도 추천, L2 준비, 제한된 Evidence 조회가 동작해야 한다.

## 실패와 검증

- 저장소별 L0-b/L1 일부 성공은 DB `analysis_jobs.status='partial'`로 남긴다. API 상태는 `failed`로 매핑하되 성공 결과와 `failedRepositories`는 조회할 수 있어야 한다.
- Wanted fetch 실패, Wanted extract 실패, GitHub 접근 실패, LLM timeout, LLM parse 실패를 같은 오류로 합치지 않는다.
- 테스트는 GitHub, Wanted, LLM을 mock하고 PostgreSQL의 JSONB, 배열, CHECK, UNIQUE, INDEX를 실제 기준으로 검증한다.
- 최소 검증은 batch 식별자 대응, parse/schema/semantic 실패 구분, 부분 성공 보존, cache hit/miss, head SHA 변경, prompt version 변경, notable area path·주장 범위 검증, optional document 없음/실패, 비공개 저장소 차단, 추천 근거 추적을 포함한다.
- 실제 모델 품질 평가는 단위 테스트와 구분하고 model, prompt version, 데이터셋 version, token, latency를 함께 기록한다.

현재 AI 원본은 `ai/src/devon_ai/`의 docstring 중심 skeleton이며 실제 분석 함수는 없다. `ai/tests/`와 BE의 설치 연결 smoke test는 패키지 구조를 검사할 뿐 L1/L2 동작을 검증하지 않는다. 파일의 설명을 이미 존재하는 callable 또는 분석 성공 근거로 인용하지 않는다.
