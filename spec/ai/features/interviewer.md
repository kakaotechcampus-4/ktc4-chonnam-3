# Director와 텍스트 면접

상태: Sprint 1 FIX 정리. 질문 후보의 재작성·재계획·유효 후보 없음 선택은 0008에서 Accepted이며 정확한 내부 형식·runtime 복구는 Proposed.

원본: [BE 면접](../../backend/features/interview.md), [공통 용어](../../shared/glossary.md), [통신 이관](../../shared/contracts/migration.md), [FE 면접](../../frontend/features/interview.md), [report 25~30](../../../report.md).

## 역할과 입력

Director는 현재 문답·평가·근거·남은 턴으로 다음 질문의 관점과 목적을 선택하는 유일한 Agent다. Controller는 service/turn_service의 결정적 코드로 권한·순서·제한·저장을 통제한다. Director가 Controller를 대체하지 않는다.

| Persona | 질문 책임 | 피해야 할 전제 |
| --- | --- | --- |
| `hr_manager` | 긴장 완화, 자기소개, 협업, 본인 역할·판단, 이전 답변 확인 | 조직 repo 접근이나 commit 수로 개인 기여를 확정 |
| `tech_lead` | 실제 코드·설계·기술 선택·문제 해결·answer_vs_code 확인 | 읽지 않은 구현·성능·배포 성공을 사실로 단정 |
| `domain_lead` | 산업/서비스의 개인정보·운영·사용자 맥락 | JD 요건 암기 검사, 사용자의 도메인 실무 경험을 추정 |

입력은 [Context](job-context.md), [AnswerAnalysis](answer-evaluation.md), [Evidence](evidence-retrieval.md), 현재 Turn, 허용 Persona와 호출 budget이다. 출력은 [Question/DirectorDecision 내부 제안](../contracts.md)이며, WS 전송 객체와 동일하지 않다.

## 준비와 첫 질문

사용자·run·선택 repo의 접근권한, 공고 성공, 선택 1~5개/L1 성공, primary 1~2개의 유효 L2·notable areas, 현재 선택과 준비 입력의 일치를 먼저 확인한다.

첫 질문은 `hr_manager`다. 자기소개를 시작점으로 사용하되 개인 경력·기여를 추정하지 않는다. 코드 Evidence 없이도 허용한다. 질문·Persona·Question Contract를 전달 전에 함께 검증·저장한다.

여기서 Question Contract의 상세 필드·저장은 Proposed 내부 설계다. AI·BE가 해당 계약을 채택한 뒤 아래 저장·평가 흐름에 적용한다. 합의 전에는 fixture로 설계를 검증하고, 임의의 DB 컬럼·테이블을 추가하거나 Contract 기반 평가 완료를 선언하지 않는다.

준비 실패는 `preparing_failed`이며 `abandoned`와 다르다. 실패를 숨기고 일반 질문으로 면접을 시작하지 않는다. `analyze_repo`, `build_persona`, `set_criteria`, `compose_question`의 실행 의존성을 만족해야 하며, FE의 표시 순서와 차이는 [원본 검토](../source-audit.md)에 남긴다. 점수 산식 미합의를 임의 rubric으로 메우지 않는다.

## 고정 9턴 정책

- 질문 하나와 그 답변이 한 Turn이다. Tool 호출·질문 재작성은 사용자 Turn 수에 넣지 않는다.
- 정상 Sprint 1은 9번째 질문에 대한 답변 처리를 완료한 뒤 종료한다. 9번째 질문을 보냈다는 이유만으로 답변을 받기 전에 완료하지 않는다.
- 첫 질문은 `hr_manager`, 이후 Persona는 Director가 선택한다.
- `tech_lead` 목표 6턴·최소 5턴, `domain_lead + hr_manager` 합산 최소 3턴이다.
- domain과 HR 각각의 최소 횟수나 고정 교대 순서는 합의돼 있지 않다. 미관찰 Persona의 피드백을 지어내지 않는다.
- 기술 질문은 primary repo 1~2개 중심으로 한다. 선택된 모든 repo를 균등하게 질문할 의무는 없다.
- Director의 정상 조기 종료는 허용하지 않는다. 사용자 종료·장애 처리는 별도 service 정책이고, 분포를 채우기 위해 사용자 종료 이후 계속 질문하지 않는다.

Controller의 Persona 후보 제한 제안:

현재까지 제시한 Persona 횟수에 후보를 1회 추가하고 남은 질문 수를 계산한다. 기술 최소 5회까지 필요한 수와 비기술 합산 최소 3회까지 필요한 수의 합이 남은 질문 수보다 크면 그 후보를 제외한다. 가능한 후보 중 기술 목표 6회와 현재 답변의 적합성을 고려한다. 이는 FIX 분포의 실행 방식 제안이며 새로운 최소치를 추가하지 않는다.

질문 수·답변 완료 수는 구분한다. 요청 중복·Tool 재시도 때문에 횟수를 늘리지 않는다. 이미 사용자에게 제시한 질문의 Persona를 나중에 바꿔 quota를 맞추지 않는다.

## 질문 생성과 검증

질문마다 목적·필수 확인내용·가정을 먼저 구성한다. 모델 후보를 아래 순서로 검사한다.

| 검사 | 확인할 내용 | 실패 처리 |
| --- | --- | --- |
| 계약·정책 | schema, 허용 Persona, 남은 턴, 유효 참조 | 후보 거절 |
| 전제 타당성 | 코드·기여·JD·도메인 가정이 실제 자료나 명시적 가정과 일치 | 근거 조회 또는 목적 재계획 |
| 현재 맥락 | 이전 답변·기여 정정·이미 확인한 내용·후속 목적과 일치 | 중복 제거, 주제/목적 재계획 |
| 표현 | 한 중심 목적, 과도한 복합 질문·정답 유도 없음 | 표현 재작성 |
| Contract 일치 | 실제 문장이 required_points를 요구하는지 | 질문 또는 Contract를 전달 전에 수정 |

[0008 결정](../decisions/0008-ai-candidate-policy.md)에 따라 전제·목적·필수 확인내용이 유효하고 표현만 잘못된 후보는 의미를 바꾸지 않는 재작성 대상으로 삼는다. 거짓·stale 전제, 잘못된 목적 또는 이미 확인한 목적의 반복은 재계획 대상으로 삼는다. 공급된 허용 Persona·맥락·근거·범위 안에서 안전한 질문을 만들 수 없으면 검증되지 않은 fallback을 발행하지 않고 유효 후보 없음으로 반환한다.

이 선택은 새 enum, 정상 종료, 사용자 입력 복구, service 상태, 추가 모델 호출, attempt/budget 또는 Persona·Turn quota를 승인하지 않는다. Controller가 최종 상태와 공개 동작을 결정한다.

이 세 의미 기준은 [context AI의 질문 검증](../../../context/AI.md)에서 수용한 내부 검토안이다. 별도 모델을 추가해야 한다는 뜻이 아니다. 결정적 검사로 확인 가능한 ID·enum·quota는 코드로 먼저 검사한다.

보완 질문은 이전 답변의 부족한 부분을, 심화 질문은 새로운 판단 조건을 확인한다. 이미 충분히 설명한 내용을 표현만 바꿔 반복하지 않는다. `answer_vs_code` 차이는 확인형 질문으로 제시한다. 검색 미발견을 거짓의 증거로 표현하지 않는다.

재작성·Tool·재계획은 공통 budget을 갖는다. 운영 상한은 [기준 결정](../decisions/0001-ai-baseline.md)에서 합의해야 하며, 상한 소진 때 검증 실패 질문을 내보내는 fallback은 금지한다.

## 답변부터 다음 질문까지

1. WS handler가 인증과 현재 면접·답변 가능 상태를 확인한다.
2. service가 현재 질문의 답변을 한 번 확정·저장한다. 성공 후 `answerReceived`를 보낸다는 의미는 FE 명세의 요구에 맞춘 설계이며 공통 WS 계약 검수에 포함한다.
3. `thinking` 상태에서 T3 답변 평가를 수행한다. 필요한 경우 제한된 근거 검색과 `evidenceCheck` 알림을 사용한다.
4. 평가·근거·정정·진행 상태를 모아 T4 Director를 실행한다.
5. Controller가 현재 면접·Turn을 다시 읽고 늦은 결과·종료 후 결과를 차단한다.
6. 다음 질문이 필요하면 검증된 Question/Contract/Persona·근거 관계를 확정하고 DB commit 후 전달한다. 정상 종료는 9번째 답변 처리 완료일 때만 확정한다. 사용자 종료나 시스템 실패는 service의 별도 상태 처리이며 모델이 정상 종료로 바꾸지 않는다.
7. Postgres Context 확정 후 Redis snapshot을 갱신한다. Redis 누락은 DB에서 복구한다.

DB 변경의 정확한 transaction 분리와 row lock/CAS 방식은 BE와 맞춘다. 외부 LLM이 응답할 때까지 긴 DB transaction을 유지하지 않는다. 질문 저장 후 알림만 실패하면 같은 질문을 재전달하며, 모델을 다시 호출해 다른 질문을 만들지 않는다.

## 공개 메시지와 보류 항목

확정 입력은 `{ "type": "answer", "text": "답변 내용" }`다. 서버 메시지 이름은 `answerReceived`, `thinking`, `evidenceCheck`, `question`, `interviewEnd`, `error`다. FE 면접 명세는 `question`에 `persona`, `text`, `turn`을 요구하므로 이를 소비자 요구로 삼아 공통 WS payload를 검수한다. 예전 타입의 `role`, `answerStart`, `answerEnd`, `transcript`를 Sprint 1 기준으로 쓰지 않는다.

FE 명세가 요구하는 `answerReceived`는 저장 완료 신호이지 다음 질문에 답해도 된다는 뜻은 아니다. 이 의미와 FE 입력 잠금·새 질문 도착 조건을 BE와 함께 확정한다. 내부 판단·raw output을 WS로 그대로 내보내지 않는다.

현 answer 메시지에는 `turnId`·제출 ID가 없다. 같은 연결의 진행 중 중복은 service 상태/lock으로 막을 수 있지만, 다음 질문 후 도착한 이전 제출을 완전히 식별하는 보장은 현재 계약만으로는 부족하다. 동일 본문이라는 이유로 모든 반복 답변을 중복 처리하지 않는다. 식별자 확장은 FE·BE 공통 결정으로 남긴다.

WS 경로의 interviewId/sessionId, 준비 재시도 메시지·준비 실패 snapshot, disconnect/heartbeat/재연결, 텍스트 `questionEnd`는 `PENDING_FE`다. FE 문서에 예시가 있다는 이유로 공통 합의 완료로 표시하지 않는다.

사용자 종료 요청의 정확한 wire도 별도 확인한다. 내부 Controller에서 종료 이후 결과 차단을 검사할 수 있지만, 승인되지 않은 종료 메시지·endpoint를 새로 만들어 공개 완료를 주장하지 않는다.

## 수용 검사

- 첫 질문 HR, 9번째 답변 후 종료, 10번째 질문 없음, quota를 불가능하게 하는 선택 거절.
- 후속 답변 보완·기여 정정·Persona 전환 후에도 같은 기록 참조.
- 없는 Evidence·범위 밖 repo·잘못된 ref·중복 질문 후보 차단.
- JSON/Tool/재계획 실패로 질문 또는 답변이 두 번 확정되지 않음.
- 유효한 목적의 표현 오류, 거짓·stale·반복 목적, 공급된 제약에서 유효 후보가 없는 경우를 각각 재작성·재계획·유효 후보 없음으로 구분.
- 사용자 종료 중 늦게 도착한 모델 결과가 질문을 저장·전달하지 않음.
- 공개 텍스트 프로토콜과 내부 결정 객체가 분리됨.
- 미합의 reconnect/stale 제출 보장을 완료로 주장하지 않음.

실행 환경과 모델 평가 범위는 [검증 기준](../verification.md)에 따른다.
