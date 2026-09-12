# AI 구현 작업 지도

이 문서는 재사용 가능한 구현 체크리스트의 연결 지도다. 서비스 pipeline 원본은 [AI 아키텍처의 확정 흐름](../../spec/ai/architecture.md)과 [BE pipeline](../../backend/docs/pipeline.md)이며, 이 작업 번호로 외부 분석 단계·worker 순서·계약을 변경하지 않는다.

현재 상태는 설치 가능한 패키지 골격이다. `task-01`의 구조 검사와 별개로 `task-02`부터 `task-13`의 기능·통합·평가 구현은 완료되지 않았다. [레이어 규칙](layer-rules.md)과 [검증 안내](testing.md)를 공통으로 적용한다.

## 작업을 선택하는 순서

1. [루트 지침](../../CLAUDE.md), [AI 지침](../CLAUDE.md), [README의 보호 지침 안내](../README.md)를 읽는다. BE 파일을 수정할 작업은 [BE 지침](../../backend/CLAUDE.md)도 읽는다.
2. 아래 표에서 맡은 작업과 관련 명세를 찾고 현재 파일·사용자 변경·기존 테스트를 확인한다.
3. FIX와 [AI 결정 기록](../../spec/ai/decisions/README.md)의 Accepted 정책, Proposed 계약, [later.md](../../later.md)의 잔여 미결정 항목을 구분한다. 한 정책의 부분 승인을 관련 저장·API 계약 전체의 승인으로 취급하지 않는다.
4. 각 task의 검증 fixture와 독립 정책 검사부터 시작한다. 미결정 사항을 임의로 채우거나 아직 없는 함수를 이미 제공되는 API처럼 호출하지 않는다.
5. 계약 채택·실제 provider·BE 연결 조건이 충족된 경로만 구현·연결하고 실행 근거를 남긴다. 다른 경로의 보류가 독립적인 검토와 mock 검사를 모두 중단시키지는 않는다.

아래 선행 작업은 읽고 맞출 입력·출력의 관계다. 모든 선행 task의 운영 배포 완료를 기다리는 직렬 일정이 아니다. 예를 들어 합성 입력으로 L1/L2 정책 검사를 준비하거나, 답변 분석 fake를 사용해 Director 정책을 검토할 수 있다. 가정한 fixture의 이름·타입은 production 계약으로 채택하지 않는다.

## 작업별 선행 관계

| 작업 | 주요 선행·참조 | 넘길 결과와 연결 전 확인 |
| --- | --- | --- |
| [01 셋업](task-01-setup.md) | 없음 | 설치·구조 검증 기반; 기능 구현과 구분 |
| [02 내부 계약](task-02-contracts.md) | 01, 내부 계약 원본 | 검토 fixture와 채택 범위; AI-L02 |
| [03 LLM 경계](task-03-llm-boundary.md) | 01·02, [ADR 0008](../../spec/ai/decisions/0008-ai-candidate-policy.md) | parse/schema/semantic 실패와 fail-closed fake; 실제 provider AI-L01, 재호출 책임 AI-L04 |
| [04 L1](task-04-repo-shallow.md) | 02·03, ADR 0008 | repo별 유효 결과 보존·invalid 분리; version·저장 매핑 AI-L03 |
| [05 L2](task-05-repo-deep.md) | 02·03·04, ADR 0008 | 고정 ref의 사용 가능·제한·무효 관찰; readiness·상태 AI-L06 |
| [06 Context 준비](task-06-context-preparation.md) | 02·04·05 | BE 주입 입력·준비 불변 조건; 상태 연결 AI-L11·12·14 |
| [07 도메인 프레임](task-07-domain-frames.md) | 02, ADR 0005·0008 | 맥락 관련성·목적 비반복 후보 선택; 운영 seed AI-L10 |
| [08 Evidence](task-08-evidence-tools.md) | 02·05, ADR 0003·0008 | 세 조건·후보 우선순위; 실제 열거·I/O·상한 AI-L04·08 |
| [09 답변 분석](task-09-answer-analysis.md) | 02·03·08 | 평가·검증 필요 후보, 후속 보완; 저장·복구 AI-L02·09 |
| [10 Director](task-10-director.md) | 02·03·06·07·08·09, ADR 0008 | rewrite/replan/failure 질문 후보; BE의 상태·턴·권한 검증 필요 |
| [11 리포트](task-11-report.md) | 02·03·09·10 | 서술·Persona 피드백 후보; 공개 점수 AI-L15, 생성 상태 AI-L16 |
| [12 평가](task-12-evaluation.md) | 01, [ADR 0007](../../spec/ai/decisions/0007-evaluation-design-policy.md)·[0009](../../spec/ai/decisions/0009-ai-evaluation-method.md); 실행 대상 task | 합성 JSON 쌍·입력 격리·grader·통제 비교; 실제 자료·운영 schema·수치·출시 AI-L01·18·19 |
| [13 BE 연결](task-13-backend-integration.md) | 연결할 02~11, 12의 관련 검사 | 저장·큐·전송의 통합 증거; 경로별 AI-L11~17 및 개별 task 조건 |

06의 입력·준비 조건 검토는 10의 첫 질문 생성보다 먼저 할 수 있다. 첫 질문의 실제 저장·전송은 10의 결과를 13에서 연결한다. 07의 정책 fixture와 12의 평가자료 분리 준비도 다른 기능 구현과 병행할 수 있다.

## 기능과 소스 연결

아래 경로는 현재 존재하는 골격의 위치다. 해당 기능이 구현되어 있다는 뜻이 아니다. 새 테스트 파일과 fixture의 제안 위치는 각 task의 `검증`에 적고 실제 생성 여부를 구분한다.

| 명세·책임 | 작업 | 현재 구현 대상 |
| --- | --- | --- |
| [내부 계약](../../spec/ai/contracts.md) | 02·03 | [contracts.py](../src/devon_ai/contracts.py), BE 주입 경계 |
| [레포 분석](../../spec/ai/features/repository-analysis.md) | 04·05·13 | [repo_shallow.py](../src/devon_ai/llm_tasks/repo_shallow.py), [repo_deep.py](../src/devon_ai/llm_tasks/repo_deep.py); 수집·추천·저장은 BE |
| [Context](../../spec/ai/features/job-context.md) | 06·13 | BE [prepare.py](../../backend/app/features/interview/prepare.py), AI contracts와 Director의 입력 사용 |
| [도메인 프레임](../../spec/ai/features/domain-frames.md) | 07·10 | [Director](../src/devon_ai/agents/director/agent.py)의 주입 frame 사용; 실제 seed는 BE |
| [Evidence](../../spec/ai/features/evidence-retrieval.md) | 08·09·10 | [tools.py](../src/devon_ai/agents/director/tools.py); 실제 파일 조회·권한·저장은 BE |
| [답변 평가](../../spec/ai/features/answer-evaluation.md) | 09·10·11 | [answer_analysis.py](../src/devon_ai/llm_tasks/answer_analysis.py)와 결과 소비 모듈 |
| [면접 진행](../../spec/ai/features/interviewer.md) | 10·13 | AI Director와 BE [turn_service.py](../../backend/app/features/interview/turn_service.py)·[ws.py](../../backend/app/features/interview/ws.py) |
| [리포트·프로필](../../spec/ai/features/report-profile.md) | 11·13 | [report.py](../src/devon_ai/llm_tasks/report.py), BE 리포트와 프로필 집계 |
| [검증·평가](../../spec/ai/verification.md) | 모든 task, 12 | [tests](../tests/), [evals](../evals/), BE 통합 테스트 |
| [후속 기능](../../spec/ai/features/extensions.md) | 현재 구현 task 대상 아님 | AI-L21~26에서 범위 승인 후 착수; 음성·Claim·OCR·외부 도메인 조회 모듈을 선행 생성하지 않음 |

## BE에 남기는 작업

AI 기능과 관련되더라도 다음 작업을 `devon_ai`로 옮기거나 중복 구현하지 않는다. 06은 주입 데이터·준비 조건을 맞추고, 13은 해당 BE 작업과 AI 반환 후보의 실제 연결을 검증한다.

| 작업 | BE 경계·원본 | AI 문서에서 확인할 조건 |
| --- | --- | --- |
| L0·GitHub 수집 | [GitHub client](../../backend/app/integrations/github/client.py), [BE task-08](../../backend/docs/task-08-github.md) | 선택 repo·고정 ref·원문 범위가 실제 입력과 일치 |
| Wanted 분류 | [jd_extract.py](../../backend/app/llm_tasks/jd_extract.py), [ADR 0006](../../spec/ai/decisions/0006-task-llm-usage-policy.md) | 규칙 변환·LLM 비호출; AI-L03의 version·저장과 AI-L05 단계 관계 |
| 추천·match score | [match_score.py](../../backend/app/features/analysis/pipeline/steps/match_score.py), [BE task-10](../../backend/docs/task-10-match.md) | AI-L07 산식·미계산·FE 표시 합의; 실패를 낮은 점수로 바꾸지 않음 |
| Prompt·설정·모델 I/O | [prompt_loader.py](../../backend/app/llm_tasks/prompt_loader.py), [LLM client](../../backend/app/integrations/llm/client.py) | 문자열·검증 데이터·도구 주입, 실제 provider·재시도·기록 책임 합의 |
| 프로필 집계 | [profile_summary.py](../../backend/app/llm_tasks/profile_summary.py), [ADR 0006](../../spec/ai/decisions/0006-task-llm-usage-policy.md) | LLM 비호출·확정 데이터 집계; AI-L17과 후속 job 연결 |
| 큐·저장·전송 | [BE pipeline](../../backend/docs/pipeline.md), [BE task-15](../../backend/docs/task-15-interview-ws.md), [BE task-16](../../backend/docs/task-16-report.md) | 기존 여섯 job·텍스트 WS·분석 SSE 유지; 멱등성·복구·공개 응답의 미합의 구분 |

## 결정 대기 지점을 다루는 방법

대기 목록의 원본은 [later.md](../../later.md)이며 이 문서에 별도 상태 원장을 만들지 않는다. 각 task는 관련 ID와 재개에 필요한 합의·검수·설정 근거를 명시한다.

- AI-L01·02·04: 실제 모델 식별, 내부 계약, 실행 상한·재시도 책임은 각각 별도 확인한다. 하나의 승인으로 다른 항목을 채택하지 않는다.
- [ADR 0008](../../spec/ai/decisions/0008-ai-candidate-policy.md)의 후보 정책과 [ADR 0009](../../spec/ai/decisions/0009-ai-evaluation-method.md)의 평가 방법을 포함한 Accepted AI 정책은 즉시 적용하고, `later.md`에는 version·저장·runtime·운영·실측 같은 잔여 합의만 확인한다.
- AI-L05~07·11~17: 영향받는 BE·FE 연결을 구분한다. 리포트 점수, 추천 점수, 준비 성공, WS 복구는 서로 다른 조건이다.
- AI-L18·19: 합성 fixture 준비와 실제 사용자 자료·독립 검수·실제 모델 평가의 권한·품질 조건을 구분한다.
- AI-L21~26: 후속 기능 채택 여부를 현재 패키지 구조나 task 번호로 승인하지 않는다.

담당자가 결정을 확정하면 해당 원본 결정 문서와 검토 fixture를 먼저 맞춘 뒤 관련 task를 재개한다. 팀 검수자를 임의로 기록하거나, 미정 값에 임의 숫자·모델 ID·enum을 넣어 테스트를 통과시키지 않는다.

## 완료와 인계

각 task의 완료 조건은 순수 검사·실제 모델 평가·BE 통합을 구분한다. 해당 기능의 예정 테스트가 생성·수집·실행되었는지 확인하고, 실행한 명령·결과·미실행 범위·남은 AI-L ID를 [테스트 안내](testing.md)에 따라 인계한다.

문서가 모두 존재하거나 현재 패키지 import 테스트가 통과했다는 사실만으로 기능 전체를 완료 처리하지 않는다. 모델 평가의 결과는 검수 자료와 실제 model·prompt·dataset version에 연결하고, 실제 서비스 연결의 결과는 저장·상태·전송 경로의 증거에 연결한다.
