# Director 질문 생성·검증 구현 기록

상태: 4번의 AI 질문 생성·검증 경계와 fake 검증 구현. 실제 모델·의미 검토기·BE 연결은 미검증.

## 기준과 범위

- 사용자의 4번 구현·분할 커밋·원격 push 지시에 따라 진행하며 PR은 생성하지 않는다.
- 선행 3번이 미병합이라 `feature/ai-answer-analysis@8d68c5e`에서
  `feature/ai-director-question`을 분기했다.
- [질문 생성과 검증](../features/interviewer.md#질문-생성과-검증),
  [ADR 0008](../decisions/0008-ai-candidate-policy.md),
  [ADR 0010](../decisions/0010-sprint1-interface-runtime-decisions.md),
  [task-10](../../../ai/docs/task-10-director.md)을 따른다.
- 최신 `origin/develop@ebbe13d`의 task-10도 대조했다. 선행 브랜치의 문서 전체를 새로 병합하거나
  복사하지 않는다. Controller의 기술 최소 5턴·비기술 합산 최소 3턴 후보 계산과 전환은 5번 범위다.

## 계획과 생성

`QuestionPlan`은 질문 문장을 생성하기 전에 목적·필수 확인내용·가정·평가 범위를
`QuestionContract`로 구성한 입력이다. 현재 함수가 원문 Context에서 다음 목적을 자율적으로
선정하거나 새 계획을 무한 생성하는 루프는 아니다. 호출자가 준비한 계획을 고정하여 문장을 생성하고,
계획에 허용된 Persona 중 선택한 후보가 그 계획을 지키는지 검증한다.

| 입력 | 소유권과 검사 |
| --- | --- |
| `question_id`, `turn` | BE가 발급·확정한 식별자와 질문 번호; 모델이 새 ID를 만들지 않음 |
| `contract` | 생성 전에 구성한 목적·required_points·assumptions·basis_refs·evaluation_scope |
| `allowed_personas` | Controller가 계산한 FIX Persona 후보; 중복·잘못된 enum·첫 질문의 HR 외 허용을 거부 |
| `remaining_candidates` | 호출자가 주입하는 남은 논리 후보 상한; 음수·잘못된 타입 거부, 0이면 호출 없이 실패 |
| `personas` | BE가 주입한 세 Persona의 질문 책임·피해야 할 전제; 별도 Persona Agent 없음 |
| `ModelRequest` | BE가 주입한 `director_v1` prompt/model/schema/version·timeout/token 설정 |

`generate_question`은 기존 Director 모듈에 둔다. 논리적 생성·검증 책임을 별도 Agent·모듈·LLM
호출로 고정하지 않는다. 기본 운영 prompt나 model ID, Persona 문구, 별도 SDK를 추가하지 않는다.
`request.input_json`은 검증한 인수로 구성한 입력으로 교체하며 임의 부가 내용과 병합하지 않는다.

남은 후보 상한은 공통 LLM attempt와 구분한다. 한 논리 생성 요청 안에서 transport/parse/schema
실패는 기존 정책대로 총 2회까지 시도한다. semantic 실패 뒤에는 후보 상한이 남아 있어도 자동
재호출하지 않는다. 상한 차감·동시 실행·재개 허용·세션 종료 재확인은 Controller 책임이다.

## 순차 검증과 복구

1. 계약·정책: 계획 ID/Turn/Persona/상한/근거를 호출 전에 검사한다. 생성 뒤에는 schema와
   후보 Persona·Evidence·JD·basis 참조를 의미 검토보다 먼저 검사한다.
2. 전제: 독립 검토가 거짓·stale·자료를 넘어선 기여·도메인 전제를 확인한다.
3. 현재 맥락: 이전 문답·기여 정정·이미 확인한 목적의 반복 여부를 확인한다.
4. 표현: 한 중심 목적, 유도·복합 질문 등 의미를 유지하며 고칠 수 있는 표현인지 확인한다.
5. Contract 일치: 실제 문장이 필수 확인내용을 요구하는지 확인한다. 모델이 Contract 자체를
   다른 목적으로 바꿔도 전달하지 않는다. 표현 오류와 의미 불일치가 함께 있으면 재계획이다.

| 상황 | 반환 분류 |
| --- | --- |
| 전제·목적·필수 내용 유효, 표현만 잘못됨 | `rewrite` |
| 거짓/stale 전제, 현재 맥락 불일치·반복, 목적/Contract 불일치 | `replan` |
| 안전한 대안 없음, 상한 소진, 정책·참조 오류, 해석할 유효 후보 없음 | `no_valid_candidate` |

위 값은 1번에서 구현한 `CandidateRecovery`를 재사용한다. 새 WS/DB enum이나 정상 `finish`를
만들지 않는다. 실패 후보를 수정·기본값 보충·일반 질문으로 바꾸어 반환하지 않는다.

## 독립 의미 검토 경계

`review(plan, candidate)`는 현재 Context에서 독립적으로 수행한 검토 결과를 반환해야 한다.
`QuestionCandidateReview`는 정확한 계획 전체·질문 전체에 묶이며, 다른 ID·문장·Contract·Persona의
검토를 재사용하면 거절한다. 생성 모델이 출력한 self-review나 `passed` 필드를 신뢰하지 않는다.
이 타입은 모델 출력의 decode 계약으로 등록하지 않았다.

모듈은 이 검토 결과의 참조·타입·조합을 검증하고 ADR 0008 분류를 수행한다. 자연어 의미 판단기를
문자열 규칙으로 대신 구현하지 않는다. 실제 검토 callable은 같은 history·근거·정정·도메인
맥락을 사용해야 하며, 여기서는 fixture 검토기를 주입했다. 항상 True를 반환하는 연결은
production 검증이 아니다. 별도 유료 검토 호출을 자동 추가한 것도 아니다.

검토 중 `ContractError`는 생성 JSON 오류와 분리해 semantic 실패로 닫는다. 잘못된 검토 입력을
고치려고 생성 모델을 재호출하지 않고, 검토 예외의 원문을 실패 metadata에 복사하지 않는다.

## 근거와 이전 문답

- 3번의 Evidence·ToolResult·history 검사 함수를 재사용한다. 현재 선택 repo/ref/path를 벗어나거나
  ID만 있고 원문이 없는 근거는 호출 전에 거절한다.
- `ReferenceText`는 BE가 선택한 JD·Context source의 ID/원문 쌍이다. 상세 DB/public schema가 아니다.
  선택된 Evidence와 같은 ID의 다른 원문이 들어오면 충돌로 거절한다.
- 선택하지 않은 근거는 직접 evidence와 tool_results.items 양쪽에서 제외한다. 도구 실행의
  상태·실제 조회 범위·한계는 보존하며 tool_error를 거짓 주장으로 변환하지 않는다.
- 이전 문답은 실제 Turn·Persona·답변 원문·최초 분석과 기여 정정을 전달한다. 현재 검토에 필요한
  원문을 보존하고 과거 분석을 새 결과로 덮어쓰지 않는다.
- source 선택의 관련성·사용자 권한과 원문 진위는 BE Context Builder의 전제다. ID 일치만으로
  자연어 주장이나 개인 기여의 진실성을 증명하지 않는다.

## 결과와 연결 책임

`QuestionReady`는 BE 질문 ID·Turn과 `ModelSuccess[Question]`를 반환한다. Question은 모든 검사를
통과한 `ContractChecked` 안에만 있다. `QuestionRejected`에는 성공 질문 필드 없이 typed failure,
attempt 기록, 복구 분류만 있다. 원시 출력은 기존 호출 기록의 보호 대상이며 공개 질문이 아니다.

검증 통과는 DB 저장·현재 세션 상태·사용자에게 전달 가능함을 의미하지 않는다. BE는 저장 직전
종료·중복·권한을 재확인하고 commit 뒤 전송해야 한다. 후보 부족을 정상 종료로 바꾸지 않는다.

## 검증

- 기준선 208개에서 Director 테스트 49개를 추가해 전체 257개를 검증했다.
- 정상·실패 테스트를 먼저 작성해 실패를 확인한 뒤 구현했다. 독립 리뷰와 지적 보완 재검토를 수행했다.
- 수정 특성 확인 계획에서 정상 문장은 통과하고 “TTL은 몇 분인가요?”라는 목적 변경은 replan으로
  닫는 대조 사례를 포함한다. 이는 주입 검토·정책 경계의 검사이며 일반적인 NLP 정확도 측정이 아니다.
- 첫 HR의 무근거 자기소개, 세 Persona, ID/검토 불일치, 잘못된 ref, stale 검토, 표현/목적 복합 오류,
  상한 소진, parse/schema/transport 실패, 모델의 ID·self-review·finish 추가를 검증했다.
- 검증 명령: `uv --directory ai sync --locked --python 3.12`,
  `uv --directory ai run --locked ruff check .`, `uv --directory ai run --locked ruff format --check .`,
  `uv --directory ai run --locked mypy src`, `uv --directory ai run --locked pytest`.
- 공유 계약 검사는 uv Python 3.12와 `.claude/scripts/requirements-checks.txt`를 사용해
  `.claude/scripts/check_contracts.py`를 실행한다. 최종 실행 결과는 완료 보고에 남긴다.
- **미실행:** 실제 생성 모델·독립 의미 검토기 품질, BE 권한·DB·WS 통합, 운영 상한 실측.
- **후속 범위:** 5번 quota 계산·턴 전환·종료, domain frame 운영·선택 연결, 자율 목적 계획·Tool 실행
  루프·서비스 재개, 저장 직전 늦은 결과 차단. 이번 검증을 이들 기능의 완료로 해석하지 않는다.
- **범위 밖:** FE/BE·보호 파일 변경, 모델 SDK 의존성 추가, PR 생성.
