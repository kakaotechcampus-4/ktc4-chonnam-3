# AI 테스트와 검증

검증 대상·수용 기준의 원본은 [AI 검증 기준](../../spec/ai/verification.md)이다. 패키지 구조 검사는 [승인된 설계](../../spec/ai/designs/2026-09-12-ai-package-structure.md), 모델 평가자료는 [ADR 0007](../../spec/ai/decisions/0007-evaluation-design-policy.md)과 [ADR 0009](../../spec/ai/decisions/0009-ai-evaluation-method.md)를 따른다.

## 결과 상태

모든 검사는 `통과`, `실패`, `보류`, `미실행`, `범위 밖`으로 구분한다. 빈 테스트 수집, import 성공, README 명령 예시, 정적 형식 검사만으로 AI 기능·모델 품질·서비스 흐름이 통과했다고 기록하지 않는다.

패키지 구조·설치 검사 외에 task-02~03 계약·레포 검증·fake callable과 BE의 HTTP 호출·설정·prompt loader/seed 검사가 있다. 외부 HTTP/DB 응답을 대체한 검사와 실제 환경 검사를 구분한다. DB·Redis·API·worker·실제 모델 평가는 별도 근거가 없는 한 미실행이다.

2026-09-23 task-01~03 검증: 양쪽 locked sync·Ruff·format·mypy 통과, AI `pytest -q` **90 passed**. 후속 로컬 PostgreSQL 15.19 검증 13개를 추가하고 `TEST_POSTGRES_URL`을 주입한 BE 전체 검사는 **133 passed**다. sdist/wheel 빌드와 별도 venv 설치 후 저장소 밖 11개 모듈 import도 통과했다. wheel 15개 entry에는 runtime·py.typed·metadata만 포함된다. 실제 OpenAI 호출은 키 미설정으로 미실행이다. PostgreSQL 검증은 별도 임시 DB에서 prompt 스키마·loader·seed만 확인했으며 현재 브랜치의 전체 migration·서비스 DB 연결 완료를 의미하지 않는다. 상세 로컬 결과는 Git 제외 `ai/report/foundation-verification-results.md`에, 재사용할 코드 경계는 [구현 인계](../../spec/ai/designs/2026-09-23-ai-foundation.md)에 기록했다.

실제 DB 검사는 [test_prompt_postgres.py](../../backend/tests/llm_tasks/test_prompt_postgres.py)에서 수행한다. 실행 방법과 격리 범위는 [BE 테스트 안내](../../backend/docs/testing.md#실제-postgresql-프롬프트-검증)를 따른다. `TEST_POSTGRES_URL`이 없으면 해당 13개 검사는 skip되므로, 기존 단위 검사 통과를 실제 DB 검증으로 보고하지 않는다.

2026-09-23 [Director 첫 구현](../../spec/ai/designs/2026-09-23-director-question-path.md) 후
최종 검증: AI **137 passed**(Director 47개 포함), 실제 PostgreSQL URL을 주입한 BE
**147 passed**(Director HTTP 연결 14개·PostgreSQL 13개 포함). 양쪽 Ruff·format·mypy 통과.
Director JSON Schema는 별도 검사 환경에서 정상 1개·오류 4개 입력을 검증했고, 공유 계약 검사도
schema 2개·부분 OpenAPI·양성/음성 fixture 7개를 통과했다. schema 검사 도구는 AI runtime 의존성에
추가하지 않았다. 모델 응답과 의미 검토는 테스트 대역이며 실제 provider·검토 품질·DB/WS 면접 연결은 미검증이다.

2026-09-23 PR #56 리뷰 수정 후 `develop`의 BE setup(`b444c64`)을 함께 검증했다.
양쪽 `uv sync --locked --python 3.12`와 Ruff·format·mypy가 통과했고, AI **138 passed**
(Director 47개), 실제 PostgreSQL URL을 주입한 BE **231 passed**, skip 0개
(Director HTTP 연결 15개·PostgreSQL 13개)다. Director schema v2는 정상 1개·오류 5개,
공유 계약 검사는 schema 2개·부분 OpenAPI·fixture 7개를 통과했다. JSON 깊이 64/65,
영구 HTTP 오류·quota·Retry-After·오류 본문 중단·공유 호출 대기와 attempts를 회귀 검증했다.
로컬 PostgreSQL 15.19의 임시 테스트 schema가 모두 삭제됐음을 확인하고 서버를 종료했다.
Linux 실행은 WSL 미설치 및 Docker 엔진 미기동으로 미실행이다. Windows에서 명시적 깊이
상한과 파서 RecursionError 처리를 각각 확인했지만 Linux 검증 통과로 간주하지 않는다.
실제 모델·독립 검토 품질·전체 migration 및 서비스 E2E는 여전히 미실행이다.

## 기능별 검증 위치

작업의 선행 관계는 [구현 작업 지도](pipeline.md)를 따른다. 현재 존재하는 구조 검사는 [test_package.py](../tests/test_package.py), [test_import_boundaries.py](../tests/test_import_boundaries.py), BE의 [설치 연결 검사](../../backend/tests/agents/test_ai_package_imports.py)다.

아래 task-02/03 및 task-10 기본 생성 경로 테스트는 구현되어 있다. 나머지 task-04~13 경로는 **추가 예정**이며 존재·수집을 별도로 확인한다. task-02의 `ai/tests/test_repository_contracts.py`는 L1/L2 계약 검증이며 실제 분석 함수 검사가 아니다. BE 호출 경계는 `backend/tests/integrations/test_llm_client.py`, Director 연결은 `test_director_boundary.py`, 설정은 `tests/core/test_llm_config.py`, prompt는 `tests/llm_tasks/test_prompt_loader.py`·`test_prompt_seed.py`에서 검사한다.

| 작업 | 검증 위치, 저장소 루트 기준 | 주요 검증 경계 |
| --- | --- | --- |
| [02 계약](task-02-contracts.md) | `ai/tests/test_contracts.py` | 검토 fixture와 실제 채택 계약의 구분, 필드·참조·변환 |
| [03 호출 경계](task-03-llm-boundary.md) | `ai/tests/test_llm_boundary.py` | fake client, parse/schema/호출 실패, attempt·metadata |
| [04 L1](task-04-repo-shallow.md) | `ai/tests/llm_tasks/test_repo_shallow.py` | 안정 ID·부분 성공·cache 입력·요약 의미 |
| [05 L2](task-05-repo-deep.md) | `ai/tests/llm_tasks/test_repo_deep.py` | 고정 SHA·notable area·path·부분 실패 |
| [06 준비 입력](task-06-context-preparation.md) | `backend/tests/features/interview/test_prepare_context.py` | BE 입력 구성·선택·준비 불변 조건 |
| [07 도메인](task-07-domain-frames.md) | `ai/tests/agents/director/test_domain_frames.py` | 주입 frame·fallback·목적·가정형 표현 |
| [08 Evidence](task-08-evidence-tools.md) | `ai/tests/agents/director/test_evidence_tools.py` | 조회 조건·실행 상태·범위·원문 연결 |
| [09 답변](task-09-answer-analysis.md) | `ai/tests/llm_tasks/test_answer_analysis.py` | 세 축·평가 가능 여부·보완·원문 보존 |
| [10 Director](task-10-director.md) | `ai/tests/agents/director/test_director.py`, `backend/tests/integrations/test_director_boundary.py` | 준비된 목적의 생성·참조·독립 검토·실패·상한; 턴 정책·서비스 연결은 후속 |
| [11 리포트](task-11-report.md) | `ai/tests/llm_tasks/test_report.py` | 서술·Persona 관찰·Turn/Evidence 연결·점수 분리 |
| [12 평가](task-12-evaluation.md) | `ai/tests/test_eval_data_boundaries.py` | source group·입력/정답 분리·결과 기록·채점기 대조 |
| [13 BE 연결](task-13-backend-integration.md) | `backend/tests/agents/test_ai_integration.py`, 해당 `backend/tests/features/` | AI 결과 수용·저장·큐·전송·복구; 설치 smoke와 별도 |

제안 fixture는 검토 중인 schema를 production 계약으로 확정하는 수단이 아니다. fixture 검토와 정책 단위 검사는 미합의 BE 연결과 독립적으로 준비할 수 있지만, 실제 DTO·저장·공개 응답을 검사하는 테스트는 해당 계약의 채택 근거를 확인한다. 실제 모델 실행에서는 동일 사례라도 mock 검사와 별도 결과를 기록한다.

## AI 패키지 검사

`ai/`에서 실행한다.

```text
uv sync --locked --python 3.12
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src
uv run --locked pytest
uv build
```

현재 Windows checkout의 로컬 uv를 사용할 때는 저장소 루트에서 실행한다.

```powershell
$repoRoot = (Get-Location).Path
$uv = Join-Path $repoRoot '.claude/scratch/tools/uv-bootstrap/Scripts/uv.exe'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $repoRoot '.claude/scratch/python'
$env:UV_CACHE_DIR = Join-Path $repoRoot '.claude/scratch/uv-cache'
& $uv --directory ai sync --locked --python 3.12
& $uv --directory ai run --locked ruff check .
& $uv --directory ai run --locked ruff format --check .
& $uv --directory ai run --locked mypy src
& $uv --directory ai run --locked pytest
& $uv --directory ai build
```

`ai/tests/`는 설치된 모듈 import, `py.typed`, import 부작용과 역의존 금지를 검사한다. wheel은 별도 격리 환경에 일반 설치하고 저장소 밖 작업 디렉터리에서 모든 모듈 import와 배포 파일 목록을 확인한다. 이 결과는 실제 AI 반환값이나 서비스 연결을 증명하지 않는다.

## BE 설치 연결 검사

`backend/`에서 실행한다.

```text
uv sync --locked --python 3.12
uv run --locked pytest tests/agents/test_ai_package_imports.py
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy app
uv run --locked pytest
```

BE smoke test는 editable 설치와 실제 `devon_ai` package 경로를 확인한다. service/facade 호출, 모델 결과, DB 저장, API·worker 기동은 기능 구현 후 별도 통합 테스트가 필요하다.

기존 `.claude/scripts/lint_changed.py`는 AI 전용 lint를 건너뛴다. 자동 hook 통과를 AI 검사 완료로 간주하지 말고 위 Ruff·mypy·pytest 명령을 직접 실행한다. 보호 규칙이나 hook을 우회·해제하지 않는다.

## Mock-first 흐름

1. 작업 계약의 FIX·Accepted 승인 범위와 Proposed·PENDING 항목을 확인하고 AI·BE가 입력·출력·실패·저장 책임을 맞춘다.
2. 외부 호출 없는 순수 계약 검사와 정상·실패 fixture를 먼저 만든다. DB 검증은 PostgreSQL을 사용하며 SQLite로 대체하지 않는다.
3. fake tool 또는 mock client로 기능을 구현하고 깨진 JSON, 근거·권한·ref 불일치, 잘못된 상태가 downstream으로 전달되지 않는지 검사한다.
4. BE service/pipeline 연결에서 저장·재시도·중복·현재 상태를 검증한다. GitHub·Wanted·LLM은 mock한다.
5. provider와 실제 model ID, prompt version, budget, 검수 자료가 확인된 기능만 실제 모델 평가로 넘긴다. 단위 테스트에 유료 호출을 섞지 않는다.

## 평가자료와 모델 실행

평가자료·실행 체계를 구현할 때는 [task-12](task-12-evaluation.md)의 단계별 작업과 결정 대기 조건을 적용한다. 이 문서는 공통 실행 안내이며 실제 dataset과 평가 harness의 존재를 선언하지 않는다.

`evals/inputs/`와 `evals/expectations/`는 작업 위치만 준비되어 있으며 실제 JSON, dataset, 운영 schema, loader, harness는 아직 없다. 향후 합성 로컬 JSON은 같은 `case_id`와 `version`의 입력/기대 쌍으로 읽고 mismatch, duplicate, orphan을 거부한다. 모델에는 입력 파일의 실행 payload만 보내며 식별·분류·split·source group 제어 정보와 기대값·검수·control 정보는 prompt, retrieval query, tool input에서 제외한다. 같은 원본의 파생 사례는 같은 source group으로 유지하고 development와 holdout에 나누지 않는다.

검수자 불일치는 양쪽 근거를 가진 `pending`으로 보존한다. 전체 사례 수·coverage와 독립 검수가 끝난 판정 가능 사례의 품질 분모를 구분하고 제외 수와 이유를 함께 보고한다. grader는 허용·금지·모호·유효하지 않은 참조·tool 실패 control에서 false accept와 false reject를 종류별로 확인한다. 실제 검수자와 조정 결과, control 사례, 수치 기준은 아직 정하지 않았다.

baseline과 candidate는 같은 사례·source group에서 한 요인씩 바꾸고 task 실패, 품질, 비용, 지연을 함께 비교한다. 권한·참조·parser·tool·source 부재 실패를 검색 방법 결함과 구분한다. 승인 범위 안의 방법 비교와 범위 확대 제안 실험은 분리하며, 후자의 실패 사례도 버리지 않되 실제 확장 실험은 사전 승인 뒤에만 실행한다.

실제 사용자 자료와 공개하지 않은 holdout 정답을 저장소에 commit하지 않는다. 임시 평가 출력은 Git 제외 경로인 `ai/report/`에 둔다. 모델 평가를 실행하지 않았으면 `미실행`으로 기록하며 mock 통과로 대체하지 않는다.

실제 평가 결과에는 dataset/source group version, 실제 provider/model ID, prompt version, 실행 횟수와 attempt, 성공·실패, token, latency, 비용을 가능한 범위에서 남긴다. token이나 비용을 받지 못했으면 0으로 추정하지 않는다. 비밀키와 실제 사용자 원문은 PR이나 공개 로그에 남기지 않는다.

## 작업 인계

다음 담당자가 재현할 수 있도록 아래를 남긴다.

- 변경 파일과 적용한 FIX 또는 승인 계약, 계속 Proposed·PENDING인 항목
- 실제 실행한 명령과 각 결과 상태, 실행하지 않은 서비스·모델 검사의 범위
- 사용한 fixture, dataset/source group, model·prompt version
- 정상·실패·부분 성공·재실행 결과와 남은 결정·검토 담당
- 외부 도구 미설치나 환경 제한으로 미실행한 항목

실행하지 않은 검사를 완료로 쓰지 않고, 기존 실패와 현재 변경에서 생긴 실패를 구분한다.

각 task의 완료 체크에는 해당 테스트의 생성 여부, 수집 개수, 명령·결과, 합의한 계약 범위와 남은 AI-L ID를 함께 남긴다. `task-13`의 저장·WS·worker 통합 검사나 실제 모델 품질 검사가 보류라면 패키지 단위 검사가 통과해도 서비스 전체 완료를 선언하지 않는다.
