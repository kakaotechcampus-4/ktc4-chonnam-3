# 레이어 규칙 · 네이밍 · 직렬화

## 1. 폴더 경계

FE `src/features/{auth,home,analysis,interview,report,mypage}` 와 같은 경계를 쓴다. 같은 이름의
폴더가 양쪽에 있으면 "이 화면 API 가 어디 있냐" 를 물어볼 일이 없어진다.
FE 의 `home` + `mypage` → BE `me` 하나로 합친다 (둘 다 `/me/*`).

호출 방향은 한 방향이다.

```
router → service → { queries | agents | llm_tasks | integrations | realtime }
```

| 계층 | 책임 |
|---|---|
| `features/*/router.py` | 요청 검증·응답 직렬화만. 비즈니스 로직 금지, DB 직접 접근 금지 |
| `features/*/service.py` | 트랜잭션 경계. **여기서만 `commit()`** |
| `features/*/queries.py` | 읽기 쿼리 모음 |
| `agents/` | Director 하나. LLM 호출 + Tool 루프. **DB 세션을 받지 않는다** — 계약 객체만 주고받아야 Eval 에서 DB 없이 돈다 |
| `llm_tasks/` | 단발 LLM 호출. `prompt_loader.py` 만 `AsyncSession` 을 받고, service 가 그것으로 로드해 문자열로 주입한다 |
| `integrations/` | 외부 네트워크. **DB 를 모른다** |
| `workers/` | `features/*/pipeline/` 을 호출하는 얇은 껍데기. 로직을 여기 쓰지 않는다 — 같은 로직을 API 에서도 호출해야 한다(재시도) |

### `repository.py` 를 쓰지 않는 이유 ⚠

일반적인 FastAPI 구조는 데이터 접근 계층을 `repository.py` 로 부른다. **이 프로젝트에서는
금지한다.** `repositories` 가 GitHub 레포 테이블이고 용어사전이 "레포 원본" 으로 못박았다.
`RepositoryRepository` 같은 이름이 나오면 회의에서 바로 오해가 생긴다.

| 뜻 | 코드 이름 |
|---|---|
| GitHub 레포 | `repository`, `repositories`, `Repository` |
| 읽기 쿼리 모음 | **`queries.py`** |

### Agent 는 Director 하나뿐이다

Evidence 조회는 별도 Agent 가 아니라 **Director 의 Tool** 이고, 레포·공고·자소서 분석과
답변 분석·리포트 생성은 단발 LLM 호출로 충분하다 → `llm_tasks/`.

이 분리가 실질적으로 쓰이는 지점은 병렬 작업이다. `agents/` 와 `llm_tasks/` 가 `features/` 에서
떨어져 있어서 AI 담당이 API 완성을 기다리지 않고 시작할 수 있다.

## 2. 금지 목록

| 금지 | 이유 |
|---|---|
| `router.py` 에서 `db.execute()` | 테스트가 HTTP 를 거쳐야만 가능해진다 |
| `agents/` 에 `AsyncSession` 주입 | Eval 독립 실행 불가 |
| `integrations/` 에서 모델 import | 외부 API 형태가 DB 로 새어 들어온다 |
| 프롬프트 문자열 하드코딩 | `prompt_versions` 테이블이 존재하는 이유가 사라진다 |
| 루브릭·주제·페르소나를 코드 상수로 | 배포 없이 못 고친다 → 최대 리스크 개선 사이클이 배포 주기에 묶인다 |
| 모델 ID(`claude-opus-5` 등)를 코드 상수로 | `prompt_versions.model` / `repo_analyses.model` / `interview_sessions.model` 이 존재하는 이유가 "어느 모델로 만든 결과인지 회귀 비교" 다. **DB 행이 모델을 결정하고 코드는 읽어 쓴다** |
| `os.environ` 을 `core/config.py` 밖에서 읽기 | 환경변수 단일 진입점이 깨진다 |
| `except Exception: pass` | 4-3-v2 화면이 `error_code` 없이 뜬다 |
| `HTTPException` 직접 raise | FastAPI 기본 `{"detail": ...}` 이 새어나가 FE 파싱이 깨진다 |
| `turn_evidences` INSERT 생략 | 서비스의 핵심 주장("근거 기반 질문")이 증명 불가 |

## 3. 계층별 표기

| 계층 | 표기 | 예 |
|---|---|---|
| DB 테이블·컬럼 | snake_case | `interview_turns`, `turn_no` |
| SQLAlchemy 모델 | PascalCase 단수 | `InterviewTurn` |
| Python 변수·함수 | snake_case | `turn_no` |
| Pydantic 필드 | snake_case (내부) → **alias camelCase** (직렬화) | `turn_no` → `turnNo` |
| API 경로 | kebab-case 복수 | `/analysis-runs` |
| enum 값 | **DB 정의 snake_case 문자열 그대로** | `probe_depth` |

⚠ **enum 값을 한글로 바꾸지 않는다.** 한글 라벨은 FE 소유다. 예외 하나 — `report.scores[].label` 은
api-spec 이 응답에 한글(`"프로젝트 이해도"`)을 요구한다. 이건 `score_criteria.label_ko` 에서
**DB 가 주는 값**이므로 "코드가 번역했다" 가 아니다.

## 4. 직렬화 — `CamelModel` 하나로 강제

`app/shared/schema.py`

```python
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,     # 요청은 snake_case 도 허용
        from_attributes=True,      # ORM 객체 → 스키마
    )
```

api-spec 공통 규약이 요구하는 4가지를 코드로 지킨다.

| 규약 | 지키는 방법 |
|---|---|
| 필드 생략 금지 | **`response_model_exclude_none` / `exclude_unset` 을 절대 쓰지 않는다** (FastAPI 기본값 유지) |
| 배열 빈 값은 `[]`, null 금지 | 리스트 필드에 `Optional[list[...]]` 금지 → `list[...] = []` |
| 객체 빈 값 `null` 허용 | 명시된 필드만 `X \| None` — `analysis`, `totalScore`, `completedAt`, `matchScore`, `answer`, `totalTurns`, `failureReason`, `estimatedSeconds` |
| 날짜 ISO 8601 | `datetime` + UTC. `TIMESTAMPTZ` 이므로 `Z` 접미사로 나간다 |

에러 봉투만 예외로 `retryAfter` 를 생략한다(api-spec 이 optional 로 명시)
→ `model_dump(exclude_none=True)` 를 **에러 핸들러 안에서만** 쓴다.

## 5. `types/api.ts` 대조 테스트 — 스펙 드리프트 방어

`tests/contract/` 에 FE 타입에서 옮겨 적은 기대 키 집합을 두고 실제 응답 키와 비교한다.

```python
HOME_KEYS = {"name","githubLinked","repositoryCount","analysisStatus","analysis","recentInterviews"}

async def test_home_response_shape(client):
    body = (await client.get("/api/me/home")).json()
    assert set(body) == HOME_KEYS            # 누락도 잡고, 몰래 추가한 필드도 잡는다
```

이게 없으면 BE 가 필드를 하나 빼먹었을 때 FE 연동 시점까지 안 드러난다.

FE 와 합의된 타입 변경(`AgentRole`·`StepKey`·`failureReason`)은
[api-spec.md](api-spec.md) 의 합의 표를 기준으로 한다.
