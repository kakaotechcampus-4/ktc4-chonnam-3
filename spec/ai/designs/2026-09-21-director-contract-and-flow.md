# Director 계약과 검증 흐름 제안

- 상태: **Proposed**. 현재 사용자는 `feature/ai-director-define`의 정의·사례·검증 작업을 요청했다. 정확한 production DTO, 저장 계약과 AI·BE 공동 채택은 아직 완료되지 않았다.
- 작성일: 2026-09-21
- 범위: 단일 Director의 요청·후보·실패 경계와 실행 가능한 로컬 계약 검토.
- 근거: [면접](../features/interviewer.md), [내부 계약](../contracts.md), [ADR 0008](../decisions/0008-ai-candidate-policy.md), [ADR 0010](../decisions/0010-sprint1-interface-runtime-decisions.md), [AI-L02 등 잔여 결정](../../../later.md).

## 목적과 채택 범위

BE가 준비한 Context와 제약을 받아 질문·조회·종료 후보를 구분하고, 유효하지 않은 모델 출력을 저장·전송 전에 거절할 수 있는 계약을 검토한다. Director는 Persona별 Agent로 나누지 않는다. 상태·권한·허용 Persona 계산·저장·전송은 BE Controller가 맡는다.

이번 실행 도구는 `ai/scripts/review_director_contract.py`다. `ai/src/devon_ai/` 밖의 개발용 검사이며 wheel과 sdist에 포함되지 않는다. 입력/기대 JSON은 ADR 0009에 따라 `ai/evals/inputs/`와 `ai/evals/expectations/`에 분리한다. script 통과는 production Director, 자연어 품질, DB·WS 통합 완료가 아니다.

## 선택안

1. 기존 내부 계약 초안을 바로 runtime DTO로 구현: 빠르지만 저장·실패·참조 방식이 공동 채택되기 전에 API가 굳어진다.
2. **독립된 제안 계약 검사와 fixture를 먼저 작성**: 지금 합의할 필드와 경계를 실행으로 검토하고, 채택 후 실제 타입/검증으로 옮긴다. 이번 선택이다.
3. BE 전체 면접 구현 뒤 Director 착수: 정책·계약 문제 발견이 늦어진다.

2번의 개발용 dict와 결과 표시는 production 인터페이스가 아니다. 계약 채택 후 해당 검사를 canonical 타입의 테스트로 이전하고 이중 validator를 유지하지 않는다.

## 요청 경계 제안

서비스 callable은 아직 만들지 않는다. 향후 비동기 Director 호출은 검증된 Context, Controller 제약, prompt 문자열·version과 provider 중립 호출/Tool 경계를 주입받는 방향이다. 구체 Python signature·DTO·Protocol은 AI-L02 채택 대상이다. credentials·DB session·Redis client는 AI에 전달하지 않는다.

로컬 JSON의 `payload`는 다음 두 객체만 가진다. case ID, version, source group, split과 기대값은 payload 밖의 자료 관리 정보다.

| 객체 | 필드 | 의미 |
| --- | --- | --- |
| `controller` | `questions_asked`, `answers_completed` | 제시한 질문 수와 답변 처리가 끝난 수를 구분. 각각 0~9 정수 |
| `controller` | `question_allowed` | 준비·현재 상태를 확인한 BE의 후보 생성 허용 여부. 실제 상태 검증 구현을 대신하지 않음 |
| `controller` | `completion_allowed` | 9번째 답변 처리까지 확인한 BE의 정상 종료 허용 여부 |
| `controller` | `allowed_personas` | BE가 FIX 분포를 달성할 수 있도록 계산한 후보. Director가 재계산하거나 확장하지 않음 |
| `controller` | `repositories` | 선택 repository ID → 면접의 고정 SHA |
| `controller` | `evidence` | 유효한 Evidence 참조 → repository ID·고정 SHA. 제외/무효 관찰은 넣지 않음 |
| `controller` | `tool_requests` | BE가 조회 필요성·권한·고정 SHA·path·범위까지 검증한 요청 ID → 요청 정보 |
| `controller` | `tool_calls_remaining` | BE가 공급한 남은 조회 횟수. fixture의 값은 운영 기본값이 아님 |
| `context` | `history`, `answer_analysis`, `limitations`, `domain_category`, `domain_frames` | 원문/판정/미확인 범위를 보존한 모델용 맥락. 정확한 전체 DTO는 기존 내부 계약과 함께 검토 |

fixture의 `context`는 의미 검토 자료다. script는 Context Builder 전체 schema, 권한, 준비 성공, Persona 배분 알고리즘 또는 자연어 사실성을 구현하지 않는다. 첫 입력의 history는 빈 목록, answer_analysis는 null이다. 그 null은 첫 질문 전 분석 부재만 표현한다. 이후 분석 실패를 같은 null로 숨기지 않는다.

원본/이전 답변을 축약해 전달할 수 있으므로 fixture history 길이로 전체 Turn 수를 재계산하지 않는다. authoritative count와 이력의 일치, 정정 이력·입력 버전은 BE 통합 검사에서 확인한다.

## 후보 경계 제안

모델 후보는 `next_step`에 따른 배타적 객체다. 아래 필드와 enum은 검토용 제안이다. DB/WS에 그대로 저장하거나 공개하지 않는다. 모르는 값의 default 보충, 알 수 없는 필드 무시, JSON repair는 하지 않는다.

| `next_step` | 허용 필드 | 의미 |
| --- | --- | --- |
| `ask` | `next_step`, `question` | 질문 후보 하나 |
| `retrieve` | `next_step`, `tool_requests` | BE가 공급한 요청 ID의 중복 없는 목록. 임의 repo/ref/path 생성 금지 |
| `finish` | `next_step` | BE가 이미 정상 종료 조건을 확인했을 때만 허용되는 제안 |

`Question`은 `persona`, `text`, `question_contract`만 가진다. Persona를 Decision과 Question에 중복 저장하지 않는다. `topic_code`, 최상위 `evidence_refs`, `intent/target`는 이 최소 제안에서는 중복 도입하지 않는다. 기존 초안과의 차이이며 채택 시 기존 계약 문서에 반영한다. JD 연결과 도구 결과의 durable ID 변환은 AI-L02의 저장/참조 검토에서 별도로 확정한다.

`question_contract`는 다음을 모두 가진다.

- `purpose`: 비어 있지 않은 중심 목적 하나.
- `required_points`: 비어 있지 않은 `{key, description}` 목록. key는 중복되지 않는다.
- `assumptions`: 명시한 가정의 문자열 목록. 가정이 없으면 빈 목록이다.
- `basis_refs`: Controller가 공급한 유효 Evidence 참조 목록. 중복/없는 참조를 거절한다.
- `evaluation_scope`: 비어 있지 않은 평가 범위 설명.

모델이 turn ID·번호·depth·parent·소유권·최종 status를 넣으면 알 수 없는 필드로 거절한다. 첫 HR 질문과 domain 가정형 질문은 코드 Evidence가 없어도 가능하다. 기술 질문은 유효한 코드 근거를 필요로 한다. basis_refs 검사는 출처 유효성만 확인하며 원문이 실제 전제를 뒷받침하는지는 별도 의미 검수다.

Tool 요청 ID 방식은 인수를 그대로 생성하는 방식보다 범위를 좁히기 위한 제안이다. 실제 `read_file/search_code/list_commits`의 signature·디렉터리 열거·상한은 이 문서로 승인하지 않는다. ToolResult의 found/not_found/insufficient_analysis/tool_error는 기존 제안과 함께 AI-L02/08에서 채택한다. 요청 허용은 실제 조회 성공이나 주장의 입증이 아니다.

## 검증과 실패

1. JSON을 해석할 수 없거나 중복 key/비표준 NaN·Infinity가 있으면 `parse`로 거절한다.
2. 필드·타입·배타적 action 구조·필수값·중복 참조를 어기면 `schema`로 거절한다.
3. 허용 Persona, 첫 HR, 현재 Turn, 종료 조건, Evidence/Tool 허용 범위·SHA·조회 budget을 어기면 `semantic`으로 거절한다.
4. 기계 검사를 통과해도 자연어 의미와 전제를 검수해야 한다. script의 `valid`는 앞의 제한된 검사 통과 표시다.

검사기의 `parse/schema/semantic/valid`는 개발용 결과다. production 실패는 실패 단계·원인과 재시도 가능 여부를 구분한 typed failure로 전달하는 방향을 제안하며, error code·외부 reason 매핑은 AI-L02/04/09에서 결정한다. 결과에 원문을 echo하지 않는다.

`rewrite/replan/failure`는 `next_step`에 추가하지 않는다. 이는 후보의 표현 오류/전제·목적 오류/안전 후보 부재에 대한 검수 분류이며, 분류만으로 모델을 재호출하거나 정상 종료하지 않는다. 자동 언어 품질 판별기를 이 검사기에 넣지 않는다.

ADR 0010에 따라 timeout/provider/parse/schema 실패의 attempt는 공통 호출 계층 한 곳에서 최대 2회 관리하고 semantic 실패는 재호출하지 않는다. Tool·재작성·재계획 상한과 소진 처리 등 AI-L04/09 잔여 사항은 실제 loop 연결 전에 결정한다. 이 script는 모델/Tool을 호출하지 않고 retry도 실행하지 않는다.

## Turn 및 BE 연결

- `ask`: `question_allowed=true`, `questions_asked=answers_completed<9`여야 한다. 첫 질문의 Persona는 HR이다.
- `retrieve`: 질문 생성 가능한 동일 Turn 경계에서 공급된 요청과 남은 budget 안에서만 허용한다. Turn 수는 바꾸지 않는다.
- `finish`: `questions_asked=answers_completed=9`이고 `completion_allowed=true`여야 한다. 9번째 질문만 제시한 상태는 종료 불가다.
- 모델 호출 전후 BE가 상태·권한·입력 버전을 다시 읽는다. 질문/Contract/Persona/근거 관계를 commit한 뒤 WS `question`으로 변환한다.
- 사용자 종료·중복 제출·전송 실패 후 같은 질문 재전달·DB/Redis 복구는 BE 통합 책임이다. 내부 후보를 WS로 직접 직렬화하지 않는다.

준비는 ADR 0010의 primary repo 1~2개 중 검증된 notable area가 최소 1개면 허용하고, 총 0개면 preparing_failed다. 무효 관찰을 evidence allowlist에 넣지 않는다. 이 준비 판정은 fixture의 true 값만으로 검증됐다고 주장하지 않는다.

## 검수 사례와 아직 실행하지 않는 검사

아래는 자연어/서비스 검수 사례다. 문자열·boolean으로 기대 분류를 되돌려주는 가짜 테스트를 만들지 않는다.

| 사례 입력 | 기대/금지 결과 | 후속 검증 주체 |
| --- | --- | --- |
| 목적은 동시 요청 처리 근거 확인, 문장은 설계·테스트·장단점을 한꺼번에 질문 | 목적/필수 확인내용을 보존해 표현 재작성. 새 평가 기준 추가 금지 | AI 모델 평가 |
| 현재 근거에는 없는 Redis 사용을 사실로 전제 | 새로운 근거·목적으로 재계획. 표현만 바꾸어 전제를 유지하지 않음 | AI 모델 평가 |
| 이미 충분히 설명한 잠금 선택 이유를 다시 질문 | 표현이 달라도 같은 목적의 반복으로 재계획 | AI 모델 평가 |
| 허용 Persona/관찰 한계 안에서 안전한 질문을 만들 수 없음 | 유효 후보 없음. invalid fallback·정상 finish 금지 | AI·BE 실패 통합 |
| 코드와 답변이 불일치하나 버전/실행 조건은 미확인 | 조건 확인형 후속 질문. 거짓 단정 금지 | AI 모델 평가 |
| 도메인 category가 없거나 신뢰할 수 없음 | etc frame, 가정형 표현. 경험/산업 추측 금지 | AI 모델 평가 |
| 관련성이 같은 두 frame 중 하나가 이전 목적과 반복 | 덜 반복하는 목적을 우선. 축 고정 순환 금지 | AI 모델 평가 |
| 제시 7턴에서 기술 3·비기술 4 | 이후 두 질문은 기술 최소 5를 달성할 수 있어야 함 | BE quota 검사 |
| 제시 7턴에서 기술 6·비기술 1 | 이후 두 질문은 비기술 합산 최소 3을 달성해야 함 | BE quota 검사 |
| 사용자 종료 중 모델 응답 도착 | 다음 질문 저장/전송 없음 | BE 통합 |
| 질문 commit 뒤 WS 전송 실패 | 같은 질문 재전달, 모델 재생성 없음 | BE 통합 |
| 후속 답변에서 본인 기여를 팀원 기여로 정정 | 다음 Context에 반영하되 원문/최초 분석 보존 | AI·BE 통합 |

## 계약 채택 체크

- [ ] AI·BE가 요청/후보 구조, null·enum·schema version, callable signature를 채택한다.
- [ ] 최소 Question의 basis_refs와 기존 evidence_refs/JD 연결의 저장·변환을 맞춘다.
- [ ] 질문·분석·결정·metadata 저장 위치와 입력 버전/늦은 결과 차단 방식을 확정한다.
- [ ] 실제 Tool 요청/결과 계약, 상한·실패·복구 책임을 확정한다.
- [ ] 운영 prompt/domain frame, provider/model ID와 평가자료 검수를 확인한다.

현재 검토자/운영값/승인을 임의로 기록하지 않는다. 채택된 범위만 `devon_ai.contracts`와 Director로 구현하고, production validator가 준비되면 개발용 validator를 이전/제거한다.

## 2026-09-21 실행 기록

| 검사 | 실행 결과 | 한계 |
| --- | --- | --- |
| AI `.venv/Scripts/python.exe -m pytest -q` | 77 passed: 기존 26 + 제안 검사 51 | production Director·실제 모델 미실행 |
| AI Ruff check / format check | 통과 | 자연어 의미·서비스 계약 승인 아님 |
| AI mypy `src scripts/review_director_contract.py` | 12 source files 통과 | source의 runtime은 계속 스켈레톤 |
| 제안 CLI | 합성 사례 4쌍 통과 | 독립 검수 정답/모델 품질 점수 아님 |
| BE `tests/agents/test_ai_package_imports.py` | 1 passed | 설치·import만 검사 |
| 공통 `check_contracts.py` | 2 schemas·부분 OpenAPI·7 fixtures 통과 | 전체 API/WS 호환성 미검증 |
| 로컬 uv `--directory ai build --offline` | wheel·sdist 생성 및 scripts/evals/tests 제외 확인 | 서비스 배포 아님 |
| 별도 에이전트의 코드 리뷰 | 중대 결함 없음. domain 사례에 명시적 가정 보완 | AI·BE 공동 계약 채택/사람의 사례 검수와 구분 |

DB·Redis·API·worker·WS·실제 provider 호출과 언어 품질 평가는 미실행이다. AI-L02 및 운영 budget·실패 복구의 Proposed 상태는 이번 검사로 변경하지 않았다.
