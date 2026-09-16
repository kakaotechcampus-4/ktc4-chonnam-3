# task-01 — AI 패키지 셋업

> 선행: 저장소 루트 접근, Python 3.12 이상, uv
> 근거: [승인된 패키지 설계](../../spec/ai/designs/2026-09-12-ai-package-structure.md), [AI 아키텍처](../../spec/ai/architecture.md), [AI 검증 기준](../../spec/ai/verification.md)

전체 기능 작업은 [구현 작업 지도](pipeline.md)에서 찾는다. 이 task의 완료 범위는 설치·구조 검증이며 `task-02` 이후의 계약·분석·면접·평가·BE 연결 구현을 대신하지 않는다.

## 목표

AI 담당자가 `ai/`에서 DB·Redis·모델 연결 없이 설치, lint, type check, 구조 테스트를 수행할 수 있는 로컬 Python 패키지 기반을 유지한다. 서비스 실행 주체는 기존 backend API와 ARQ worker이며 별도 AI 서버를 만들지 않는다.

## 작업

- Python 요구 버전은 3.12 이상으로 유지하고 `uv.lock`으로 AI 개발 환경을 고정한다.
- 배포명 `devon-ai`, import 이름 `devon_ai`, `src/` layout을 유지한다.
- `src/devon_ai/`와 `py.typed`만 runtime wheel에 포함하고 `tests/`, `evals/`, 검수 정답은 제외한다.
- `src/devon_ai/` 모듈은 현재 책임을 설명하는 docstring 스켈레톤으로 유지한다. 승인된 계약과 기능이 생기기 전에는 빈 성공 함수, 임시 DTO·Protocol, callable facade, provider 호출을 추가하지 않는다.
- AI와 BE의 `.venv`·`uv.lock`은 독립적으로 관리한다. BE는 `../ai`를 editable dependency로 설치하며 AI dependency나 metadata가 바뀌면 양쪽 lock의 영향을 확인한다.
- 설치 누락을 `sys.path` 수정이나 `PYTHONPATH`로 가리지 않는다.
- 실제 검증 명령과 결과 기록은 [테스트 안내](testing.md)를 따른다.

## Windows 로컬 환경

현재 checkout에는 Git 제외 영역에 uv bootstrap과 Python/cache 경로가 준비되어 있다. 전역 Python이나 `PATH`를 바꾸지 않고 저장소 루트에서 실행한다. 다른 checkout에서는 이 임시 도구가 없을 수 있으므로 먼저 uv를 별도로 준비한다.

```powershell
$repoRoot = (Get-Location).Path
$uv = Join-Path $repoRoot '.claude/scratch/tools/uv-bootstrap/Scripts/uv.exe'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $repoRoot '.claude/scratch/python'
$env:UV_CACHE_DIR = Join-Path $repoRoot '.claude/scratch/uv-cache'
& $uv --directory ai sync --locked --python 3.12
& $uv --directory ai run --locked pytest
```

저장소 루트에서 이 로컬 uv를 사용할 때는 `--directory ai`를 생략하지 않는다.

## 완료 조건

- Python 3.12 환경에서 locked sync, lint, format check, mypy, pytest, wheel build 결과를 보고한다.
- 격리된 설치 환경과 저장소 밖 작업 디렉터리에서 배포된 모든 AI 모듈을 import하고 실제 패키지 경로를 확인한다.
- wheel에 runtime source·타입 표시·표준 metadata만 포함되는지 확인한다.
- BE 환경의 editable 설치와 `devon_ai` import smoke 결과를 별도로 확인한다.
- 구조 검사의 성공을 callable AI 기능, 모델 품질, DB·Redis·API·worker 동작 또는 배포 성공으로 보고하지 않는다.

검증 기반을 확인한 뒤 [내부 계약](task-02-contracts.md)과 [LLM 경계](task-03-llm-boundary.md)의 fixture·정책 검토로 이동한다. 실제 함수·타입 채택은 각 task의 결정 대기 조건에 따른다.
