# AI Python 패키지

서비스 요구사항의 원본은 [`spec/ai/`](../spec/ai/), AI 소스의 원본은 [`src/devon_ai/`](src/devon_ai/)다. [승인된 패키지 설계](../spec/ai/designs/2026-09-12-ai-package-structure.md)에 따라 기존 backend API와 ARQ worker가 로컬 `devon-ai` 패키지를 import한다. 별도 AI 서버는 없다.

task-01~03의 패키지 기반, 내부 계약·순수 검증, 주입 호출 계약과 BE의 OpenAI 호출·설정·프롬프트 로딩을 구현했다. 사용법과 남은 연결은 [기반 구현 인계](../spec/ai/designs/2026-09-23-ai-foundation.md)를 따른다. [Director 첫 구현](../spec/ai/designs/2026-09-23-director-question-path.md)은 준비된 목적의 질문 생성·독립 검토·검증까지다. 목적 자동 선정·도구 실행·레포 분석·리포트 생성, DB/worker/API 통합과 실제 모델 품질 검증은 후속 범위다.

## 프로젝트 구조

```text
ai/
  pyproject.toml, uv.lock, ruff.toml
  src/devon_ai/
    __init__.py, py.typed, contracts.py
    agents/director/
      agent.py, tools.py
    llm_tasks/
      repo_shallow.py, repo_deep.py, answer_analysis.py, report.py
  tests/
    test_package.py, test_import_boundaries.py
    test_contracts.py, test_repository_contracts.py, test_llm_boundary.py
  evals/
    README.md, inputs/, expectations/
  docs/
    task-01-setup.md
    task-02-contracts.md, task-03-llm-boundary.md
    task-04-repo-shallow.md, task-05-repo-deep.md
    task-06-context-preparation.md, task-07-domain-frames.md
    task-08-evidence-tools.md, task-09-answer-analysis.md
    task-10-director.md, task-11-report.md
    task-12-evaluation.md, task-13-backend-integration.md
    pipeline.md, layer-rules.md, testing.md
```

배포명은 `devon-ai`, import 이름은 `devon_ai`다. `src/devon_ai/`만 런타임 패키지에 포함하고 테스트·평가자료는 배포물에서 제외한다. 임시 실행 결과는 Git 제외 경로인 `ai/report/`에 둔다. `evals/`에는 아직 실제 사례, 검수 정답, loader, harness가 없다.

## 개발 문서

| 문서 | 내용 |
| --- | --- |
| [pipeline.md](docs/pipeline.md) | 전체 작업 순서, 기능·소스 지도, BE 소유권, 구현·검수 인계 |
| [layer-rules.md](docs/layer-rules.md) | AI·BE 소유권, 기능별 소스 경로, FIX·Proposed 경계 |
| [testing.md](docs/testing.md) | 검증 명령, mock-first 흐름, 평가·미실행·인계 기준 |

### 기능별 작업 지침

먼저 작업 지도를 읽고 해당 task를 선택한다. 문서 생성은 기능 구현 완료가 아니다. 각 task의 채택 범위와 남은 구현·검수 조건을 확인하며, 독립적인 정책·fixture 검토와 실제 서비스 연결을 구분한다.

| 작업 | 구현·검토 대상 |
| --- | --- |
| [01 셋업](docs/task-01-setup.md) | Python·uv, 설치·구조 검증 |
| [02 내부 계약](docs/task-02-contracts.md) | 입력·출력·저장 변환의 채택 조건과 fixture |
| [03 LLM 경계](docs/task-03-llm-boundary.md) | 주입된 호출 경계, 실패·재시도·metadata |
| [04 L1 분석](docs/task-04-repo-shallow.md) | 식별자 기반 배치, 부분 실패, 프로젝트 요약 |
| [05 L2 분석](docs/task-05-repo-deep.md) | 고정 SHA, notable areas, 유효한 코드 위치 |
| [06 Context 준비](docs/task-06-context-preparation.md) | BE가 주입할 입력과 면접 준비 조건 |
| [07 도메인 프레임](docs/task-07-domain-frames.md) | 주입된 frame 사용 정책과 개발용 후보 검수 |
| [08 Evidence 도구](docs/task-08-evidence-tools.md) | 추가 조회 판단, 도구 요청·결과 해석 |
| [09 답변 분석](docs/task-09-answer-analysis.md) | 충분성·정확성·기여, 근거·후속 보완 |
| [10 Director](docs/task-10-director.md) | 질문·다음 행동, 질문 검증, 턴 정책 |
| [11 리포트](docs/task-11-report.md) | 문답·근거에 연결된 서술과 Persona 피드백 |
| [12 평가](docs/task-12-evaluation.md) | 사례·검수·입력 분리·평가 실행 체계 |
| [13 BE 연결](docs/task-13-backend-integration.md) | 저장·큐·전송과 AI 후보 결과의 최종 연결 |

먼저 [루트 작업 지침](../CLAUDE.md), [AI 작업 지침](CLAUDE.md), backend를 수정할 때는 [BE 작업 지침](../backend/CLAUDE.md)을 읽는다. 서비스 기능·계약·완료 조건은 [AI 아키텍처](../spec/ai/architecture.md), 맡은 [기능 명세](../spec/ai/features/), [AI 검증 기준](../spec/ai/verification.md)을 따른다. 공통 API·이벤트·타입은 [공통 계약](../spec/shared/contracts/README.md)과 [이관 상태](../spec/shared/contracts/migration.md)를 함께 확인한다.

구현 기준은 기존 `report.md`와 `spec/`의 FIX 계약 및 이후 승인된 [AI 결정](../spec/ai/decisions/README.md)의 해당 범위다. [내부 AI 계약](../spec/ai/contracts.md)은 최신 결정에서 채택한 구성과 미구현 상세를 구분한다. [검토 근거](../spec/ai/source-audit.md), [승인된 기준선](../spec/ai/decisions/0001-ai-baseline.md), [구현·검수 인계](docs/pipeline.md#기존-id별-구현검수-인계), [Sprint 2 후속 목록](../spec/ai/features/extensions.md#sprint-2-착수-시-검토할-사항)에서 출처와 상태를 확인한다. 작업 지침은 이 원본을 참조하며 새 요구사항·계약을 확정하지 않는다.

## 작업 지침과 검증 위치

[AI 작업 지침](CLAUDE.md)에 따라 AI 소스와 단독 검증은 `ai`, 서비스 실행과 통합 검증은 `backend`에서 수행한다. backend 파일을 수정할 때는 [BE 작업 지침](../backend/CLAUDE.md)도 확인한다. 별도 AI 서비스는 없다.

현재 설치·검증 명령은 [셋업](docs/task-01-setup.md)과 [테스트 안내](docs/testing.md)를 따른다.
