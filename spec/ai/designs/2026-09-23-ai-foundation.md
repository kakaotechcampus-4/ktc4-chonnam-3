# AI task-01~03 구현과 후속 작업 연결

기준: `develop` 4282322. 2026-09-23 사용자 요청으로 task-03까지 구현한다.
정책 근거는 ADR 0010·0011·0014·0015·0018·0019와 [내부 계약](../contracts.md)이다.
이 문서는 기존 필드의 Python 표현과 호출 연결을 기록하며 DB migration이나 공개 API를 추가하지 않는다.

## 구현 경계

| 범위 | 담당 코드 | 연결 책임 |
| --- | --- | --- |
| 패키지 | `ai/pyproject.toml`, `ai/uv.lock` | Python 3.12+, stdlib 계약, BE에서 editable 설치 |
| 내부 계약 | `ai/src/devon_ai/contracts.py` | Question/Contract, AnswerAnalysis, DirectorDecision, Context, Evidence/ToolResult, L1/L2 입력·결과와 순수 검증 |
| 호출 계약 | 같은 `contracts.py` | PromptSpec, CallLimits, ModelRequest, ModelResult, CallFailure, AttemptMetadata, ModelCall |
| 설정 | `backend/app/core/config.py` | 호출 시 환경을 읽고 비밀키·모델·실행 상한을 주입 |
| 프롬프트 | `backend/app/llm_tasks/prompt_loader.py` | 기존 prompt_versions에서 task의 활성 행 하나를 읽어 PromptSpec 반환 |
| 모델 호출 | `backend/app/integrations/llm/client.py` | OpenAI Responses HTTP, JSON·schema·의미 검증, 재시도 및 metadata |
| 초기 seed | `backend/scripts/seed_prompt_versions.py` | 검수된 7개 task/version을 transaction 안에서 멱등 등록 |
| Turn 저장 변환 | `backend/app/agents/contracts.py` | 검증된 모델 결과만 해당 question_contract/analysis/decision의 평면 JSONB로 변환 |

AI에는 DB session, 환경변수, httpx, OpenAI SDK를 전달하지 않는다. BE가 callable과 값만 주입한다.
새 AI 서버·gateway 모듈·클래스 없이 기존 소유 경계를 사용한다. 이미 사용하는 httpx로 transport를
구현하므로 사용하지 않던 anthropic 의존성을 제거했다.

## 타입과 검증

내부 DTO는 frozen dataclass, 문자열 Literal, tuple로 표현한다. 필수값을 기본값으로 채우지 않는다.
`basis_refs`는 `{kind, id}`이며 참조 ID는 BE가 발급·권한 확인한 문자열이다. 필드 외 추가 키를
일괄 거부하는 새 정책은 넣지 않는다. 기존 평면 JSONB의 다섯 질문 기준 필드와 분석·판단 필드를
유지하며 각 저장값에 schema_version/status/result/error를 덧씌우지 않는다.

| 값 | 생산자 → 소비자 | 확정한 내부 표현 |
| --- | --- | --- |
| Context·L0/L2 source 입력 | BE의 권한·수집 검사 → AI task | 원문·고정 ref·실제 수집 범위, 모델 해석과 분리 |
| Question/Contract | 생성 task 및 검토 → BE 전달·저장 | Contract 5개 필드, required_points `{key, description}`, basis_refs `{kind, id}` |
| AnswerAnalysis | 답변 분석 task → BE T3 저장 | 기존 10개 최상위 필드, contribution_scope 안에 `{scope, answer_quotes}` |
| DirectorDecision | Director 후보 → Controller·BE T4 저장 | 기존 6개 필드, ask/retrieve/finish의 허용 상태 검사 |
| Evidence/ToolResult | BE 수집·도구 → AI 판단 | 기존 위치·출처, ToolResult 5개 필드·4개 상태, 부분 오류의 유효 items 보존 |
| L1/L2 결과 | 레포 분석 task → BE 저장 adapter | project_role_summary는 프로젝트 요약이며 개인 role_summary 필드에 자동 매핑하지 않음 |

`decode`는 구조가 맞는 후보를 만들고, `validate_*`는 참조 범위까지 검사한 `ContractChecked`를
반환한다. `to_data`는 이 검증 완료 값만 JSON 값으로 변환한다. BE `to_turn_jsonb`는 성공한
ModelResult 안의 검증 완료 값과 대상 컬럼을 함께 확인하며 실패·raw 후보·다른 컬럼 타입을 거부한다.
이는 DB 쓰기 자체가 아니므로 최초 분석 보존·현재 Turn 확인·transaction은 서비스가 책임진다.

구조 검사와 의미 검사는 분리한다. 모델이 출력한 ID·SHA·path·인용이 입력의 허용 범위에 맞는지
순수 validator가 검사하며, 실제 DB 존재·소유권은 BE 책임이다. 타입 검사는 질문의 자연어 품질이나
사실성을 자동으로 보증하지 않는다. 각 feature가 필요한 검토·평가를 수행한다.

L1은 배열 순서가 아닌 repository_id로 결합한다. 유효 항목을 보존하고 식별 가능한 schema 오류만
재요청 후보로 돌려준다. 누락·중복·미등록 ID·SHA 불일치는 semantic 오류다. L2는 고정 SHA와
전달한 파일·읽은 범위 안의 위치만 허용한다. 실제 요약 생성·파일 수집은 task-04/05에서 구현한다.

## 호출 계약 사용

BE가 활성 PromptSpec과 CallLimits를 준비하고, AI task는 ModelRequest를 구성한다. request의
payload에는 해당 작업 입력만 넣는다. 평가 정답·control metadata는 넣지 않는다. schema_name,
schema_version은 호출 추적용이며 DB 결과에 공통 바깥 객체를 추가하지 않는다. task별 JSON Schema는
각 task가 작성한다. Python 타입에서 모든 schema를 자동 생성하는 프레임워크는 도입하지 않는다.

```python
from functools import partial

from app.core.config import get_settings
from app.integrations.llm.client import CallBudget, call_model
from app.llm_tasks.prompt_loader import load_active_prompt

settings = get_settings()
prompt = await load_active_prompt(db_session, "repo_shallow")
# DB 조회 transaction은 서비스에서 종료한 뒤 모델을 호출한다.
model_call = partial(
    call_model,
    api_key=settings.openai_api_key,
    http_client=http_client,
    budget=CallBudget(),  # 한 논리 작업마다 새 객체. 부분 배치 재요청에는 같은 객체.
)
# AI task에 model_call, prompt, settings.call_limits()와 검증된 입력을 주입한다.
# task가 ModelRequest와 validator를 준비하면:
# result = await model_call(request, validator)
```

각 시도의 timeout, 출력 token 상한, 입력·응답 byte 상한을 명시해야 한다. 네 설정값에는 운영 기본값을
지어 넣지 않는다. `.env.example`의 빈 값을 배포 환경에서 채운다. 입력 byte는 prompt·JSON Schema를
포함한 HTTP 요청 본문 전체이며 응답 byte는 HTTP 본문 전체다. 각 상한은 양수, timeout은 유한값이다.
예산 소진은 실패이며 출력 자르기·추측한 기본값·provider fallback으로 성공을 만들지 않는다.

timeout/provider/parse/schema는 최초 요청 포함 최대 2회, semantic/budget은 즉시 종료한다.
첫 배치에서 유효 항목이 있으면 부분 결과를 받은 task가 실패한 ID만 다시 요청하고 같은 CallBudget을
사용한다. 내부 transport 재시도는 없다. 호출자가 넣는 http_client에도 별도 재시도를 설정하지 않는다.
`parse_shallow_batch`의 결과에는 `succeeded`와 `failed`가 함께 있을 수 있다. 바깥 ModelResult의
성공은 배치 결과를 검증해 전달했다는 뜻이며 모든 레포가 성공했다는 뜻이 아니다. task는 각 실패의
stage와 식별자를 확인하고 입력에 대응하는 repository_id가 있는 schema 항목만 재요청한다.
ID가 없는 오류를 특정 레포로 추측해서 연결하지 않는다. 원래의 성공 항목과 semantic 실패는 그대로 보존한다.
후속 ARQ job은 `max_tries=1`로 연결해야 하며 task-13의 실제 worker 검증 전에는 재시작까지 포함한
영구적인 중복 호출 방지를 보장하지 않는다. CallBudget은 프로세스 안의 한 작업에만 유효하다.

provider 거부·불완전 응답·깨진 JSON·중복 JSON key·NaN/Infinity를 정상 데이터로 통과시키지 않는다.
실제 응답 model과 response ID, prompt/schema version, 시도별 latency·token·오류를 기록한다.
token 미수집은 None이며 0으로 바꾸지 않는다. raw output은 AttemptMetadata에 보존하되 repr/log에는
노출하지 않는다. DB 영구 보관·권한·보존 기간 적용은 해당 서비스 연결 시 검증한다.

## 프롬프트와 DB

loader는 활성 행이 없거나 여러 개면 실패하며 설정 기본 모델·임시 prompt로 대체하지 않는다.
seed 입력은 `repo_shallow_v1`, `repo_deep_v1`, `jd_extract_v1`, `answer_analysis_v1`,
`director_v1`, `report_v1`, `profile_summary_v1` 일곱 PromptSpec이다. `settings.llm_default_model`은
seed를 구성할 때 주입하고, 실제 호출 모델은 조회된 행의 model을 사용한다.

같은 task/version의 본문·모델을 조용히 덮어쓰지 않는다. 서로 다르면 충돌로 실패한다. 재실행은
중복 행을 만들지 않으며 task별 transaction lock으로 동시 seed를 직렬화한다. 호출자가
`async with session.begin():` 안에서 전체 seed를 실행하고 commit/rollback을 소유한다.
검수된 운영 prompt 원문은 이번 기반 코드에 임의 작성하지 않는다. seed 함수만 호출했다고
DB에 운영 prompt가 이미 준비됐다고 볼 수 없다. DB task의 prompt_versions 테이블과 제약이 필요하다.

## 후속 담당자가 시작할 작업

- 레포 분석: 이 계약과 주입 callable을 사용해 task-04 L1, task-05 L2를 구현한다. 테스트는 수집된
  fixture만으로 시작할 수 있다. 실제 E2E에는 BE GitHub 수집·DB 저장·worker 연결도 필요하다.
- JD 분석: Wanted adapter와 `build_requirement_drafts`의 기존 결정적 경로를 이어간다. 현재 JD 추출은
  LLM 0회이며 이 호출 계층·jd_extract prompt가 준비될 때까지 개발을 기다릴 이유가 없다.
- Director: 기반 계약을 소비하되 실제 agent loop·Controller·Tool 실행은 task-08~10·13 범위다.
- 운영 연결: 계정 접근, PostgreSQL seed/조회, task별 prompt 품질·token/비용·지연, metadata 영구 저장,
  ARQ·API·WS는 각 후속 기능에서 실제 환경으로 검증한다.

검증 결과와 실행 명령은 [테스트 안내](../../../ai/docs/testing.md) 및 Git 제외 `ai/report/`에 기록한다.
OpenAI 키가 없어 실제 provider 호출은 미실행이다. 로컬 PostgreSQL 15.19를 별도 임시 DB로 실행해
prompt loader/seed의 멱등성·불변성·유일성·rollback·동시 잠금 13개 검사를 통과했다. 기존 DB branch
`c731c5b`의 prompt_versions DDL을 테스트 schema에 적용했으며 전체 migration·서비스 DB 배포를
검증한 것은 아니다. [실행 방법](../../../backend/docs/testing.md#실제-postgresql-프롬프트-검증)을 따른다.

Transport 형식은 OpenAI 공식 [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)와
[모델 문서](https://developers.openai.com/api/docs/models/gpt-5.6-luna)를 확인했다. 실제 계정에서 모델을
호출할 수 있는지와 각 task의 출력 품질은 문서 확인과 별도의 검증이다.
