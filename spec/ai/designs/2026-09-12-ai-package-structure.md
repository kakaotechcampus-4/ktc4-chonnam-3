# AI Python 패키지와 프로젝트 구조

- 작성일: 2026-09-12
- 상태: **Accepted**. 현재 사용자가 방향과 아래 상세 구조·변경·검증 범위를 승인했다. 실제 구현·검증 결과는 별도로 기록한다.
- 대상: 프로젝트 구조와 개발·설치 기반. AI 서비스 기능 구현이나 배포 완료를 뜻하지 않는다.
- 원본: [루트 지침](../../../CLAUDE.md), [AI 아키텍처](../architecture.md), [BE 아키텍처](../../backend/architecture.md), [미결정 목록](../../../later.md).

## 1. 목적과 승인 경계

AI 담당자가 `ai/`에서 코드를 개발하고 DB·모델 연결 없이 구조를 검사할 수 있도록 설치 가능한 Python 패키지를 만든다. 서비스 실행 주체는 기존 FastAPI API와 ARQ worker이며 별도 AI 서버·포트·컨테이너·네트워크 계약은 추가하지 않는다.

사용자는 기존 `backend/app/` 중심 코드 배치 지침의 변경을 포함하여 이 방향을 승인했다. 이는 AI·BE 패키징 경계 변경에 대한 현재 사용자 승인이지, 다른 팀 검수·운영 반영이 이미 끝났다는 의미는 아니다.

이번 구조 생성은 다음까지 포함한다.

- AI 패키지, 모듈별 책임 안내, 설치·lint·type·구조 테스트 기반.
- 기존 BE 개발 환경에서 로컬 AI 패키지를 설치하고 import할 수 있는 연결.
- 기존 API·worker 이미지가 같은 AI 패키지를 포함하도록 빌드 경로 정합성 확보.
- 현재 코드 위치를 설명하는 AI·BE 문서의 제한적 갱신.

다음은 포함하지 않는다.

- 실제 Director loop, L1/L2 분석, 답변 판정, 근거 조회, 리포트 생성 로직.
- [내부 계약](../contracts.md)의 Proposed 필드·enum·Protocol 인수·저장 구조 채택.
- 실제 provider/API model ID, timeout/token/도구 budget, 재시도 담당 계층 선정.
- 운영 prompt·domain frame seed, 점수 공식, 실제 사용자 자료·평가 데이터셋 구축.
- API·DB·Redis·ARQ 상태 전이, 인증·WS·SSE 계약 변경, FE 코드 변경.
- 새 CI 체계·배포 환경 구축, 기존 계약 검사 도구의 무관한 결함 수정, 커밋·푸시·PR.

## 2. 확인한 현재 상태

검토 기준은 `feature/spec-ai-docs`, HEAD `8dabd55`의 작업 트리다. 기존 사용자 변경과 미커밋 AI 문서를 보존한다.

- `ai/`에는 `CLAUDE.md`, `README.md`만 있다.
- `backend/`의 Python 파일 125개는 AST 검사에서 모두 빈 파일 또는 모듈 docstring만 있었다. 실제 AI 함수·클래스나 호출 import graph를 이전하는 작업은 아니다.
- BE는 Python 3.12 이상, uv, Ruff, mypy, pytest를 사용하도록 선언되어 있다. `backend/uv.lock`은 아직 없다.
- 확인한 Windows 실행 환경은 Python 3.10.9이며 uv·Docker 명령을 찾지 못했다. 구현 검증은 별도 Python 3.12 환경에서 수행해야 하며, 현재 Anaconda 환경을 덮어쓰거나 Python 요구 버전을 낮추지 않는다.
- Docker는 현재 `backend/`만 build context로 사용한다. 이 상태에서 `../ai` 의존성만 추가하면 이미지 빌드에 필요한 패키지가 빠진다.
- 기존 FE는 `/api`를 통해 BE를 소비한다. 이 설계 때문에 FE의 AI 직접 호출이나 신규 endpoint가 필요하지 않다.

## 3. 생성할 구조

배포 패키지명은 `devon-ai`, Python import 이름은 `devon_ai`로 구분한다. 서비스 코드는 `src` 아래에 두고 테스트·평가용 자료·문서를 설치 대상에서 분리한다.

```text
ai/
  CLAUDE.md                       # 기존 파일, 코드 위치·검증 안내 갱신 대상
  README.md                       # 작업 경로, 책임, 실행 명령
  pyproject.toml                  # 패키지·개발 도구 설정
  uv.lock                         # 실제 dependency resolution으로 생성
  ruff.toml                       # BE와 같은 Python/스타일 기준
  src/
    devon_ai/
      __init__.py
      py.typed
      contracts.py                # 계약 채택 전, 책임·승인 경계만 안내
      agents/
        __init__.py
        director/
          __init__.py
          agent.py                # 유일한 Director의 향후 구현 위치
          tools.py                # Director 측 도구 사용 경계
      llm_tasks/
        __init__.py
        repo_shallow.py
        repo_deep.py
        answer_analysis.py
        report.py
  tests/
    test_package.py               # 설치·모듈 import·부작용 검사
    test_import_boundaries.py     # BE 및 인프라 역의존 금지 검사
  evals/
    README.md                     # 0007 적용, 실제 자료·harness 미구현 표시
    inputs/
      .gitkeep
    expectations/
      .gitkeep
```

모듈은 읽을 명세와 담당 책임을 명시한 import 가능한 골격으로 생성한다. 기능을 구현한 것처럼 보이는 빈 성공 반환 함수, 임시 모델 응답, 임의 schema·숫자 기본값은 만들지 않는다. `contracts.py`에도 아직 승인되지 않은 DTO나 추상 인터페이스를 선언하지 않는다.

별도 `gateway`, `controller`, `worker`, `context_builder`, `question_generator` 패키지는 만들지 않는다. 필요 기능은 아래 책임 경계에 따라 향후 구현하고, 독립 모듈이 실제 복잡성을 줄일 때만 나눈다. 논리적 역할마다 Agent나 LLM 호출을 추가하지 않는다.

## 4. 책임과 데이터 흐름

```text
FE -> 기존 BE REST / analysis SSE / interview text WS
BE API 또는 ARQ worker -> service / pipeline
service -> queries / prompt_loader / 외부 I/O adapter
service -> backend의 AI 연결 모듈 -> devon_ai
devon_ai -> 주입된 값과 도구를 이용한 후보 결과
service -> 현재 권한·상태 검증 -> DB 저장 -> 알림
```

위 흐름은 후속 기능 구현의 목표다. 이번 구조 테스트는 설치와 import만 증명하며 실제 질문·답변 처리가 연결되었다고 보고하지 않는다.

| 영역 | 소유 책임 | 이번 구조 생성에서의 처리 |
| --- | --- | --- |
| `devon_ai.agents.director.agent` | 질문·행동 후보를 생성하는 단일 Director | 모듈과 책임 안내만 생성 |
| `devon_ai.agents.director.tools` | 주입된 제한 도구의 사용 요청과 결과 해석 | 실제 조회·Protocol·budget 미구현 |
| `devon_ai.llm_tasks` | L1/L2, 답변 분석, 리포트 서술 후보 | 네 모듈만 생성, 모델 호출 없음 |
| `devon_ai.contracts` | 향후 승인된 내부 입력·출력 타입 | AI-L02를 명시하고 타입 채택 보류 |
| BE service/Controller | 권한·현재 Turn·상태·중복·트랜잭션·commit | 기존 소유권 유지, 기능 수정 없음 |
| BE integrations | GitHub·Wanted·LLM 등 구체 외부 I/O | API key·model 설정·transport는 BE에 유지 |
| BE prompt loader/queries | DB 조회와 운영 prompt·설정 로드 | `AsyncSession`을 AI 패키지에 넘기지 않음 |
| BE worker/pipeline/realtime | 작업 등록·순서·진행·저장·알림 | 작업·큐·프로토콜 추가 없음 |

Wanted 구조화 필드 변환과 Sprint 1 프로필 확정 집계는 [0006](../decisions/0006-task-llm-usage-policy.md)에 따라 LLM을 호출하지 않는다. 기존 BE의 해당 step/job 책임·예정 위치를 유지하며 `devon_ai.llm_tasks`에 중복 생성하지 않는다. 기존 일곱 prompt version 목록과 여섯 ARQ job은 삭제하거나 재정의하지 않는다.

[0002~0007의 승인 정책](../decisions/README.md)은 유지한다. Sprint 1 vector 검색·선설치는 없고, 근거 부족·조회 실패를 감점으로 바꾸지 않는다. 답변의 충분성·정확성·기여를 구분하며 도메인 질문은 Director의 관점으로 유지한다. 이 원칙은 각 모듈 안내에서 관련 기능 명세로 연결하되 스켈레톤에 실제 구현했다고 표시하지 않는다.

AI 라이브러리는 `app.*`, FastAPI, SQLAlchemy, Redis, ARQ, 구체 provider SDK에 의존하지 않는다. import 시 환경변수·자격증명 읽기, 모델·네트워크·DB 연결을 시작하지 않는다. 실제 서비스 설정과 조회·저장은 BE가 맡고, 필요한 값을 주입하는 정확한 계약은 AI-L02에서 검토한다.

## 5. 기존 backend 경로와 공존

기존 파일은 삭제·이동하지 않는다. AI 소스의 원본 위치는 새 `ai/src/devon_ai`이며 기존 BE 파일은 앞으로 service와 AI 패키지를 잇는 얇은 연결 계층으로 사용한다.

| 기존 BE 경로 | AI 구현 원본 위치 |
| --- | --- |
| `backend/app/agents/contracts.py` | `ai/src/devon_ai/contracts.py` |
| `backend/app/agents/director/agent.py` | `ai/src/devon_ai/agents/director/agent.py` |
| `backend/app/agents/director/tools.py` | Director 측 책임은 `ai/src/devon_ai/agents/director/tools.py`; 실제 권한·외부 조회 adapter는 BE |
| `backend/app/llm_tasks/repo_shallow.py` | `ai/src/devon_ai/llm_tasks/repo_shallow.py` |
| `backend/app/llm_tasks/repo_deep.py` | `ai/src/devon_ai/llm_tasks/repo_deep.py` |
| `backend/app/llm_tasks/answer_analysis.py` | `ai/src/devon_ai/llm_tasks/answer_analysis.py` |
| `backend/app/llm_tasks/report.py` | `ai/src/devon_ai/llm_tasks/report.py` |

현재 함수·타입이 없으므로 이번에는 위 BE 파일에 연결 책임과 새 위치를 안내한다. 존재하지 않는 심벌의 재수출, 임의 facade 인수, `sys.path` 조작, 소스 복사·junction을 만들지 않는다. 실제 facade는 해당 기능의 계약이 승인되고 구현될 때 추가한다.

`prompt_loader.py`, `jd_extract.py`, `profile_summary.py`, Sprint 2의 `doc_claims.py`와 `conflict.py`는 자동 이동하지 않는다. 이전 docstring과 FIX의 차이는 새 AI 코드에 복사하지 않는다. `answer_vs_code`의 Sprint 1 저장 책임도 BE에 남는다.

## 6. 설치와 이미지 구성

Python 하한은 BE와 같은 3.12다. AI 골격의 런타임 의존성은 비워 두고, 개발 도구는 BE와 같은 Ruff·mypy·pytest를 사용한다. 새 AI 모델 SDK나 벡터 라이브러리를 설치하지 않는다. 패키징 backend는 Hatchling을 사용하고 wheel에는 `src/devon_ai`, 타입 표시, 표준 패키지 metadata만 포함한다. [Python 패키징 안내](https://packaging.python.org/en/latest/tutorials/packaging-projects/#choosing-a-build-backend)

AI와 BE는 각자 `pyproject.toml`, `uv.lock`, `.venv`를 가진다. 루트 uv workspace로 전체 저장소를 전환하지 않는다. BE의 `project.dependencies`에 `devon-ai`를 선언하고 `tool.uv.sources`의 상대 경로 `../ai`로 연결한다. 로컬 개발에서는 editable 설치를 사용하고, 패키지 배포 검사는 일반 wheel 설치도 확인한다. 이 상대 경로 source는 uv 설정이며 일반 pip가 자동 해석한다고 안내하지 않는다. [uv dependency sources](https://docs.astral.sh/uv/concepts/projects/dependencies/#path)

각 lock은 해당 프로젝트 실행 환경을 고정한다. BE가 AI의 개발 도구나 `ai/uv.lock`을 사용하는 구조는 아니다. AI 런타임 의존성이나 패키지 metadata가 바뀌면 AI·BE 양쪽 lock의 갱신 필요성을 검사한다. 최초 lock은 실제 resolver로 생성하고 기존 BE 의존성을 임의 삭제하거나 별도 일괄 업그레이드하지 않는다. 생성된 lock을 손으로 작성하지 않는다.

기존 두 실행 서비스의 이미지 구성은 다음 범위에서만 맞춘다.

- `backend/docker-compose.yml`: API·worker의 build context를 저장소 루트로, Dockerfile 경로를 `backend/Dockerfile`로 설정한다. DB·Redis·포트·환경변수 전달·worker 명령은 유지한다.
- `backend/Dockerfile`: 컨테이너 내부도 `/srv/backend`, `/srv/ai` 형제 구조로 배치한다. AI의 `pyproject.toml`, metadata가 참조하는 `README.md`, `src/`를 설치 전에 복사한다. BE 작업 디렉터리에서 로컬 AI 의존성을 설치하고 기존 API·worker 실행 경로를 유지한다.
- 이미지 설치는 개발 도구와 editable 경로 의존을 제외한 방식으로 검사한다. AI 평가자료는 복사하거나 설치하지 않는다. [uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/)
- 루트 `.dockerignore`: 확대된 context에서 실제 `.env`·비밀키·`.git`·가상환경·FE·context 자료·평가자료·임시 로그를 제외한다. Dockerfile은 필요한 BE 파일과 AI 패키지 파일을 명시적으로 복사한다.

AI 패키지는 외부 index에 게시하지 않는다. 패키지 build/install 검사는 개발 기반 검증이며 기존 `app.main:app`나 `WorkerSettings`의 실제 동작을 보장하지 않는다.

`src` layout의 목적은 작업 디렉터리에 우연히 존재하는 소스가 아니라 설치된 패키지를 검증하는 데 있다. 테스트용 `PYTHONPATH`로 설치 누락을 가리지 않는다. [Python Packaging Guide](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)

## 7. 평가자료와 실패 처리

`evals/`는 [0007](../decisions/0007-evaluation-design-policy.md)의 작업 위치만 준비한다. `inputs`는 모델에 제공 가능한 자료, `expectations`는 기대·금지 결과와 검수 메모의 예정 위치다. 이 구조 생성 단계에서는 실제 JSON schema·사례·정답·표본 수·split을 생성하지 않았다. 후속 [0009](../decisions/0009-ai-evaluation-method.md)는 합성 로컬 입력/기대 JSON 쌍과 loader·검수·grader·통제 비교 방법만 승인했다. 실제 JSON과 harness는 여전히 없으며 운영 자료의 source group·사용 이력 저장 형식은 AI-L18/AI-L19 대상이다.

기대 정답·검수 메모는 모델 입력·검색 범위 및 배포 패키지에서 제외해야 한다. 폴더를 나누는 것만으로 접근 격리나 holdout 독립성이 검증되었다고 주장하지 않는다. 실제 loader/harness 구현 시 입력 허용 목록과 source group 누출 검사를 추가해야 한다.

향후 실제 자료의 접근권한·보존·저장 방식은 AI-L18/AI-L19를 따른다. 이 구조를 근거로 실제 사용자 자료나 미사용 holdout 정답을 공개 저장소에 커밋하지 않는다. 임시 결과는 기존 Git 제외 경로인 `ai/report/`를 사용한다.

모듈 import·설치 실패는 검증 실패로 보고하며 빈 성공으로 대체하지 않는다. 모델 오류의 자동 1회 재시도 원칙은 유지하지만 SDK·task·worker 중 누가 이를 담당하는지와 의미 검증 재계획은 이번에 구현하지 않는다. 미확정 작업을 `NotImplementedError` API로 공개하거나 실제 기능처럼 테스트하지 않는다.

## 8. 문서와 편집 범위

구현 시 새 파일 외 변경 대상은 다음으로 제한한다.

- `backend/pyproject.toml`, `backend/Dockerfile`, `backend/docker-compose.yml`, 최초 `backend/uv.lock`, 루트 `.dockerignore`.
- 5절의 BE 모듈 안내와 `backend/tests/agents/test_ai_package_imports.py`의 설치 연결 smoke test.
- `ai/README.md`, `backend/README.md`, `spec/ai/architecture.md`, `spec/ai/contracts.md`, `spec/ai/verification.md`, `spec/backend/architecture.md`의 현재 코드 위치·검증 안내. 필요한 기능/task 문서에서도 같은 경로 안내만 맞춘다.
- `ai/CLAUDE.md`의 작업 디렉터리·검증 라우팅은 갱신 대상이지만 보호 파일이므로 자동 편집 대상에서 제외한다. 담당자 반영용 문안은 "AI 소스와 단독 검증은 ai, 서비스 실행과 통합 검증은 backend. 현재 명령은 ai/README.md와 spec/ai/verification.md 참조. backend 파일 수정 시 backend/CLAUDE.md도 확인"이다. 보호 규칙을 해제하거나 다른 도구로 우회하지 않으며 반영 여부를 결과에 구분한다.

현재 AI 전용 lint를 미확정으로 보고하는 `.claude/scripts/lint_changed.py`와 관련 테스트는 이번에 변경하지 않는다. AI 검증 명령을 직접 실행하고, 기존 자동 lint hook이 AI 파일을 검사하지 않는다는 제한을 문서에 명시한다. 새 자동화 연결은 별도 작업이다.

`context/*`, `ForAI.md`, `report.md`, 공유 API/DB 계약, 기존 ADR·감사 기록, 운영진 CODEOWNERS·보호 workflow는 수정하지 않는다. 과거 기록은 당시 상태로 유지하고 새 설계를 연결한다. 기존 미결정 항목은 구조 생성만으로 완료 처리하지 않는다.

## 9. 구조 생성의 완료 조건

| 검사 | 통과 근거 | 증명하지 않는 것 |
| --- | --- | --- |
| AI 개발 환경 | Python 3.12에서 uv lock/sync와 lint·format·mypy·pytest 실행 | 서비스 기능 완성 |
| 패키지 배포 형태 | wheel build 및 새 격리 환경의 일반 설치, 저장소 밖 작업 디렉터리에서 모든 AI 모듈 import | 실제 AI 결과 품질 |
| import 부작용 | 자격증명·네트워크·DB 없이 package import, 금지 외부 모듈 미로딩 확인 | 향후 task 호출의 모든 안전성 |
| 의존 방향 | AST 기반 구조 검사로 AI의 `app.*`·인프라·provider 직접 import 금지 확인 | 임의 동적 import까지 막는 보안 경계 |
| 배포 내용 | wheel에 AI source·타입 표시·표준 metadata만 포함, tests/evals/기대 정답 제외 | 평가자료 접근통제 완료 |
| BE 설치 연결 | BE 환경에서 설치한 `devon_ai` import, 실제 package 경로/배포 metadata 확인 | service/facade 함수 연결 완료 |
| 컨테이너 경로 | Compose 설정 검증, 이미지 build, 이미지에서 `devon_ai` import | API·worker 기동이나 운영 배포 성공 |
| 문서 정합성 | 현재 위치·미구현 상태·책임 경계와 링크 확인, 기존 사용자 파일 변경 범위 확인 | 모델 평가·FE/BE 전체 계약 일치 |

AI의 기본 검증 명령은 `ai/`에서 `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest`, `uv build`로 제공한다. lock 최초 생성은 이 명령들의 선행 작업이다. BE의 기존 검증 명령도 실행하고 기존 실패와 이번 변경으로 생긴 실패를 구분한다.

Docker 같은 실행 도구가 없으면 구성의 정적 확인과 실제 이미지 검사를 구분하여 후자는 미실행으로 보고한다. 미실행 항목이 있는 상태를 전체 구조 검증 통과라고 표현하지 않는다. 모델 호출, DB/Redis 접속, API·worker 기동, 실제 모델 평가는 이번 완료 조건 밖이다.

## 10. 승인과 실행

사용자가 상세 설계 검토 후 구현 계획 작성과 실제 프로젝트 구조 생성을 승인했다. 실행 계획은 `.claude/scratch/plans/`에 기록하며 이 문서가 해당 구현의 기준이다. 승인은 실제 모델·서비스 검증 완료가 아니다.

구조 구현 중 기존 파일의 사용자 변경이나 이 설계에 없는 계약 변경이 필요하면 해당 부분만 재검토한다. 코드 배치 승인으로 `later.md`의 모델·schema·점수·운영 정책까지 승인된 것으로 확대하지 않는다.
