# AI 패키지 레이어와 소유권

이 문서는 개발 경로 안내다. 서비스 요구사항과 계약의 원본은 [AI 아키텍처](../../spec/ai/architecture.md), [AI 기능 명세](../../spec/ai/features/), [공통 계약](../../spec/shared/contracts/README.md)이다. 패키지 배치는 [승인된 설계](../../spec/ai/designs/2026-09-12-ai-package-structure.md)를 따른다.

구체적인 작업 순서와 task별 담당 파일·결정 대기 지점은 [구현 작업 지도](pipeline.md)를 따른다. Context 준비와 도메인 frame은 협업·정책 단위이며 별도 AI 모듈이나 Agent를 추가하라는 뜻이 아니다.

## 의존 방향

```text
FE -> BE REST / SSE / text WS
BE API or ARQ worker -> service / pipeline
service -> queries / prompt loader / external I/O adapter
service -> devon_ai
devon_ai -> injected values and tools -> candidate result
service -> permission and state check -> DB commit -> notification
```

의존은 `backend -> devon_ai` 단방향이다. `devon_ai`는 `app.*`, FastAPI, SQLAlchemy, Redis, ARQ, 구체 provider SDK를 직접 import하지 않는다. GitHub·Wanted·LLM transport, API key와 모델 설정, DB·Redis 저장, 권한·상태·트랜잭션은 BE가 소유한다.

`AsyncSession`은 Director나 일반 LLM task에 넘기지 않는다. BE service가 prompt와 설정, 검증된 데이터를 읽어 문자열·값으로 주입한다. 모델 호출 중 DB transaction을 장시간 유지하지 않고 결과 저장 직전에 현재 상태를 다시 확인한다.

## 소스 소유권

| AI 원본 (`ai/src/devon_ai/`) | 책임 | BE 연결·I/O (`backend/app/`) |
| --- | --- | --- |
| `contracts.py` | 향후 채택할 내부 입력·출력 경계 | `agents/contracts.py`, service/schema 변환 |
| `agents/director/agent.py` | 질문·행동 후보를 만드는 단일 Director | service/Controller의 상태·Turn·Persona 확정 |
| `agents/director/tools.py` | 주입된 도구의 요청·결과 해석 경계 | 실제 조회·권한·ref/path·budget 검증 adapter |
| `llm_tasks/repo_shallow.py` | L1 후보 결과 | GitHub 수집·저장, pipeline |
| `llm_tasks/repo_deep.py` | L2 후보 결과 | primary repo·고정 ref·저장, pipeline |
| `llm_tasks/answer_analysis.py` | 답변 해석·판정 후보 | 질문 범위·근거·상태 검증과 저장 |
| `llm_tasks/report.py` | 리포트 서술 후보 | 확정 문답·근거 로드, 점수·profile 집계·worker·저장 |

기존 `backend/app/agents/`와 `backend/app/llm_tasks/`의 해당 파일은 연결 계층의 예정 위치로 남긴다. AI와 BE에 같은 로직을 이중 구현하지 않는다. 현재 양쪽 모두 callable 기능이 없는 docstring 스켈레톤이므로 없는 함수·타입을 API처럼 호출하지 않는다.

## 기능별 경로

| 맡은 작업 | 명세 | 구현 위치 또는 선행 작업 |
| --- | --- | --- |
| L1/L2 분석 | [레포 분석](../../spec/ai/features/repository-analysis.md) | AI `llm_tasks/repo_shallow.py`, `repo_deep.py`; 수집·저장은 BE |
| 공고·추천 | [레포 분석의 Wanted·추천](../../spec/ai/features/repository-analysis.md) | BE `llm_tasks/jd_extract.py`, analysis pipeline; Sprint 1 Wanted 변환은 LLM 비호출 |
| 작업·면접 Context | [Context 구성](../../spec/ai/features/job-context.md) | BE `features/interview/prepare.py`, pipeline/service |
| Director·질문 | [면접 진행](../../spec/ai/features/interviewer.md) | AI `contracts.py`, `agents/director/agent.py`; 상태 확정은 BE service |
| 답변 해석·판정 | [답변 평가](../../spec/ai/features/answer-evaluation.md) | AI `llm_tasks/answer_analysis.py` |
| 코드 근거·충돌 | [Evidence](../../spec/ai/features/evidence-retrieval.md) | AI `agents/director/tools.py`; 실제 조회·권한·저장은 BE |
| 도메인 질문 | [도메인 프레임](../../spec/ai/features/domain-frames.md) | BE `domain_question_frames` seed, 주입된 frame을 사용하는 Director |
| 피드백·요약 | [리포트와 프로필](../../spec/ai/features/report-profile.md) | AI `llm_tasks/report.py`; profile 확정 집계·worker·저장은 BE |
| 음성 등 후속 기능 | [확장 경계](../../spec/ai/features/extensions.md) | Sprint 2 검토 후 별도 작업 |

## 계약 상태

- 기존 `report.md`와 `spec/`의 FIX 및 후속 [Accepted 결정](../../spec/ai/decisions/README.md)의 승인 범위를 구현 기준으로 사용한다. 출처 충돌은 [source audit](../../spec/ai/source-audit.md)와 [baseline 결정](../../spec/ai/decisions/0001-ai-baseline.md)을 확인한다. 부분 결정의 승인 범위를 저장·API 계약 전체로 확대하지 않는다.
- [내부 계약](../../spec/ai/contracts.md)의 새 DTO·enum·Protocol·JSON 구조는 Proposed다. AI-L02는 PENDING이며 패키지 구조 승인이 타입 채택 승인은 아니다. AI·BE가 fixture·변환·저장 책임을 합의하기 전에는 구현 계약으로 확정하지 않는다.
- 공통 API·DB 의미 변경은 [공통 계약 이관 상태](../../spec/shared/contracts/migration.md)를 확인하고 관련 팀 결정 없이 확정하지 않는다.
- `5.5 Luna`는 프로젝트 모델 선택 표기다. 실제 provider와 호출 가능한 model ID가 확인되기 전에는 mock client로 작업한다.
- prompt, domain frame, model ID, 평가 기준을 함수 내부 상수에 넣지 않고 정해진 BE config·seed·loader 경로에서 주입한다.
- 별도 AI server, port, worker, container, network contract를 추가하지 않는다.
