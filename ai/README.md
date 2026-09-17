# AI Python 패키지

서비스 요구사항의 원본은 [`spec/ai/`](../spec/ai/), AI 소스의 원본은 [`src/devon_ai/`](src/devon_ai/)다. [승인된 패키지 설계](../spec/ai/designs/2026-09-12-ai-package-structure.md)에 따라 기존 backend API와 ARQ worker가 로컬 `devon-ai` 패키지를 import한다. 별도 AI 서버는 없다.

현재 런타임은 **설치 가능한 docstring 스켈레톤**이다. 모듈 import와 패키지 경계 검사는 가능하지만 callable facade, Director·분석·평가·리포트 함수, 내부 DTO·Protocol, 실제 provider 연결은 아직 없다. import 성공을 기능 구현이나 서비스 연결 완료로 해석하지 않는다.

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
| [pipeline.md](docs/pipeline.md) | 전체 작업 순서, 기능·소스 지도, BE 소유권, 결정 대기 지점 |
| [layer-rules.md](docs/layer-rules.md) | AI·BE 소유권, 기능별 소스 경로, FIX·Proposed 경계 |
| [testing.md](docs/testing.md) | 검증 명령, mock-first 흐름, 평가·미실행·인계 기준 |

### 기능별 작업 지침

먼저 작업 지도를 읽고 해당 task를 선택한다. 문서 생성은 기능 구현 완료가 아니다. 각 task의 선행 조건과 결정 대기 항목을 확인하며, 독립적인 정책·fixture 검토와 실제 서비스 연결을 구분한다.

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

구현 기준은 기존 `report.md`와 `spec/`의 FIX 계약 및 이후 승인된 [AI 결정](../spec/ai/decisions/README.md)의 해당 범위다. [내부 AI 계약](../spec/ai/contracts.md)은 Proposed이며 AI-L02의 DTO·Protocol·저장 형식은 아직 채택되지 않았다. [검토 근거](../spec/ai/source-audit.md), [승인된 기준선](../spec/ai/decisions/0001-ai-baseline.md), [미결정 목록](../later.md)에서 출처와 상태를 확인한다. 작업 지침은 이 원본을 참조하며 새 요구사항·계약을 확정하지 않는다.

## 보호 지침 라우팅

`ai/CLAUDE.md`는 보호 대상이며 현재의 backend 중심 코드 위치 안내가 새 패키지 배치를 반영하지 못한 상태다. 보호 규칙을 우회해 자동 편집하지 않는다. 담당자가 적용할 대체 라우팅 문안은 다음과 같다.

> AI 소스와 단독 검증의 작업 디렉터리는 ai, 서비스 실행과 통합 검증은 backend다. 현재 명령은 ai/README.md와 spec/ai/verification.md를 따른다. backend 파일을 수정할 때는 backend/CLAUDE.md도 확인한다. 별도 AI 서비스 실행 명령은 없다.

현재 설치·검증 명령은 [셋업](docs/task-01-setup.md)과 [테스트 안내](docs/testing.md)를 따른다.
