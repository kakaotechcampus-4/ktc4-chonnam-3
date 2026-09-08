# Backend

카카오테크 캠퍼스 4기 2단계 팀 프로젝트 (전남대 3팀) BE.

설계 문서는 [`becontext.md`](../becontext.md). 폴더 경계·레이어 규칙·에러 규약은 전부 거기서 결정됐다.

## 기술 스택

- FastAPI + Python 3.12
- PostgreSQL 15 (asyncpg + SQLAlchemy 2.0 async, Alembic)
- Redis 7 (세션 · 락 · SSE pub/sub)
- ARQ (비동기 큐)
- uv (의존성) / ruff · mypy / pytest

## 시작하기

```bash
git clone <repo-url>
cd ktc4-chonnam-3/backend
cp .env.example .env      # 값 채우기
docker compose up -d db redis
uv sync
uv run alembic upgrade head
uv run python -m scripts.seed_all
uv run uvicorn app.main:app --reload --port 8000
```

`http://localhost:8000/api` 가 API prefix. 워커는 별도 프로세스로 띄운다.

## 스크립트

| 명령                                                  | 설명              |
| ----------------------------------------------------- | ----------------- |
| `docker compose up -d db redis`                       | DB·Redis만 띄우기 |
| `uv sync`                                             | 의존성 설치       |
| `uv run alembic upgrade head`                         | 마이그레이션      |
| `uv run python -m scripts.seed_all`                   | 도메인 지식 시드  |
| `uv run uvicorn app.main:app --reload --port 8000`    | API               |
| `uv run arq app.workers.arq_app.WorkerSettings`       | 워커              |
| `uv run ruff check . && uv run ruff format --check .` | 린트              |
| `uv run mypy app`                                     | 타입 체크         |
| `uv run pytest`                                       | 테스트            |

## 폴더 구조

```
app/
├─ main.py          # FastAPI 인스턴스, 라우터 등록, 예외 핸들러, lifespan
├─ core/            # 설정·에러·로깅·보안·토큰암복호화·의존성
├─ db/              # engine/session + models/ (테이블별 모듈)
├─ shared/          # CamelModel, enums, 페이지네이션, clock
├─ features/        # 도메인별 API (auth, me, analysis, interview, report) — FE src/features 와 1:1
│  └─ analysis/pipeline/   # job_type 3종 + steps/ 7개
├─ agents/          # ★ Director 하나뿐. DB 세션을 받지 않는다
│  └─ director/     # agent.py + tools.py (Evidence Tool 3종)
├─ llm_tasks/       # 단발 LLM 호출 (Agent 아님). prompt_loader 만 DB 세션을 받는다
├─ integrations/    # 외부 I/O (github, llm, jd, extract). DB 를 모른다
├─ realtime/        # Redis pub/sub, SSE, WS 레지스트리
└─ workers/         # ARQ WorkerSettings + tasks (얇은 껍데기)

docs/               # db-schema, error-reasons, redis-keys, task-01~17
migrations/         # Alembic
scripts/            # 도메인 지식 시드
tests/              # contract(api.ts 대조) / features / agents / llm_tasks
```

호출 방향은 한 방향이다.

```
router → service → { queries | agents | llm_tasks | integrations | realtime }
```

- `router.py` — 요청 검증·응답 직렬화만. 비즈니스 로직·DB 직접 접근 금지.
- `service.py` — 트랜잭션 경계. 여기서만 `commit()`.
- 읽기 쿼리 모음은 **`queries.py`** 다. `repository.py` 라는 이름은 쓰지 않는다 —
  `repositories` 가 GitHub 레포 테이블이라 이름이 겹친다.
- **`agents/` 에는 Director 만 있다.** Evidence 조회는 별도 Agent 가 아니라 Director 의 Tool 이고,
  레포·공고·자소서 분석과 답변 분석·리포트 생성은 단발 LLM 호출이라 `llm_tasks/` 에 있다.
- `llm_tasks/prompt_loader.py` 만 `AsyncSession` 을 받는다. service 가 이걸로 프롬프트를 로드해
  문자열로 주입하므로, `agents/` 와 나머지 task 는 DB 를 모른 채 Eval 에서 단독 실행된다.
- `integrations/speech/` 는 없다 — 스프린트1 은 양방향 텍스트다 (스프린트2 에 STT/TTS 추가).

## API 스펙

API 표면의 유일한 진실은 [`frontend/docs/api-spec.md`](../frontend/docs/api-spec.md) 이고,
응답 타입은 [`frontend/src/types/api.ts`](../frontend/src/types/api.ts) 와 1:1 로 맞춘다
(`tests/contract/` 가 응답 키 집합을 대조한다).

- 에러 봉투와 reason 목록 → [`docs/error-reasons.md`](docs/error-reasons.md)
- Redis 키 → [`docs/redis-keys.md`](docs/redis-keys.md)
- 스키마 결정과 1차/2차 경계 → [`docs/db-schema.md`](docs/db-schema.md)
- 스펙 ↔ 데이터모델 충돌 9건 → [`becontext.md`](../becontext.md) 1장

**FE 와 합의된 변경 (BE 내부명을 그대로 쓴다 — 경계 매핑 레이어 없음)**

| `types/api.ts` 현재                                           | 확정                                                         |
| ------------------------------------------------------------- | ------------------------------------------------------------ |
| `AgentRole = tech_lead \| senior_developer \| manager`        | `tech_lead` / `hr_manager` / `domain_lead`                   |
| `StepKey` 4개                                                 | 7개 (`doc_extract` … `match_score`)                          |
| `jd_unreachable` / `jd_parse_failed` / `github_token_expired` | `jd_fetch_failed` / `jd_extraction_failed` / `token_invalid` |
| WS 오디오 바이너리 + `transcript`                             | 스프린트1 은 텍스트, 스프린트2 에 STT/TTS                    |

## 브랜치 / PR

- 작업 브랜치는 `develop`에서 분기, PR도 `develop`으로.
- 브랜치명 예: `feature/be-xxx`, `fix/be-xxx`.
