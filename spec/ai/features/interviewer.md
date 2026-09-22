# Director와 텍스트 면접

상태: Sprint 1 FIX 정리. 질문 후보의 재작성·재계획·유효 후보 없음 선택은 0008에서 Accepted이며 [0014](../decisions/0014-minimal-change-revision.md)의 기존 필드·저장 순서 채택 외 상세 형식·runtime 복구는 Proposed.

원본: [BE 면접](../../backend/features/interview.md), [공통 용어](../../shared/glossary.md), [통신 이관](../../shared/contracts/migration.md), [FE 면접](../../frontend/features/interview.md). 과거 원본 `report.md` 25~30은 현재 저장소에 없으며, 당시 검토 내역은 [원본 감사 기록](../source-audit.md)을 참고한다.

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

Question Contract는 [0014](../decisions/0014-minimal-change-revision.md)에 따라 같은 Turn의 `question_contract` JSONB에 [기존 다섯 필드](../contracts.md#question-contract-저장-형식)로 저장한다. 문서 채택과 실제 저장·평가 구현 완료를 구분한다.

준비 실패는 `preparing_failed`이며 `abandoned`와 다르다. 실패를 숨기고 일반 질문으로 면접을 시작하지 않는다. 준비 단계 순서는 `analyze_repo`, `build_persona`, `set_criteria`, `compose_question`이다. 공개 점수 6개·단순 평균은 확정됐으며, 세부 평가 기준의 작성·검수가 끝나지 않은 상태를 임의 기준으로 메우지 않는다.

## 고정 9턴 정책

- 질문 하나와 그 답변이 한 Turn이다. Tool 호출·질문 재작성은 사용자 Turn 수에 넣지 않는다.
- 정상 Sprint 1은 9번째 질문에 대한 답변 처리를 완료한 뒤 종료한다. 9번째 질문을 보냈다는 이유만으로 답변을 받기 전에 완료하지 않는다.
- 첫 질문은 `hr_manager`, 이후 Persona는 Director가 선택한다.
- [공통 0002 결정](../../shared/decisions/0002-local-policy-baseline.md)에 따라 정상 9턴의 Persona 횟수는 `tech_lead` 6회·`domain_lead` 2회·`hr_manager` 1회로 고정한다.
- [BE Turn 정책](../../backend/features/interview.md#turn-정책)에 따라 2번째 질문부터 Director가 잔여 횟수가 있는 Persona 중에서 선택한다. 첫 HR 질문 외에 고정 질문 순서·교대를 추가하지 않으며 미관찰 Persona의 피드백을 지어내지 않는다.
- 기술 질문은 primary repo 1~2개 중심으로 한다. 선택된 모든 repo를 균등하게 질문할 의무는 없다.
- Director의 정상 조기 종료는 허용하지 않는다. 사용자 종료·장애 처리는 별도 service 정책이고, 분포를 채우기 위해 사용자 종료 이후 계속 질문하지 않는다.

Controller의 Persona 후보 제한:

Controller는 6·2·1에서 이미 확정·제시한 Persona별 횟수를 빼고, 잔여 횟수가 없는 Persona를 후보에서 제외한다. 첫 HR 질문 뒤에는 HR 잔여 횟수가 0이므로 다시 선택하지 않는다. Director는 남은 후보 안에서 현재 답변에 적합한 관점을 선택하며, 정상 종료 시 6·2·1을 충족해야 한다.

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

이 세 의미 기준은 과거 원본 `context/AI.md`의 질문 검증에서 수용한 내부 검토안이다. 해당 원본은 현재 저장소에 없으며, 현행 후보 정책은 [0008 결정](../decisions/0008-ai-candidate-policy.md)을 따른다. 별도 모델을 추가해야 한다는 뜻이 아니다. 결정적 검사로 확인 가능한 ID·enum·quota는 코드로 먼저 검사한다.

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

[0014](../decisions/0014-minimal-change-revision.md)에 따라 기존 T3 분석 저장·T4 판단과 Context 갱신 순서를 유지하고, `analysis`·`decision` JSONB에 기존 객체를 직접 보관한다. 별도 실행 상태·공통 바깥 객체·조회별 DB 쓰기는 추가하지 않는다. 실제 조회 요약은 성공 판단의 `reason_summary`에 포함하며 최초 분석·근거를 보존한다. 실패·중단 기록은 [저장 경계](../contracts.md#분석과-판단의-저장)를 따르고 영구 실패 기록 위치·형식은 AI-L02·AI-L18에서 정한다.

DB 변경의 정확한 transaction 분리와 row lock/CAS 방식은 BE와 맞춘다. 외부 LLM이 응답할 때까지 긴 DB transaction을 유지하지 않는다. 질문 저장 후 알림만 실패하면 같은 질문을 재전달하며, 모델을 다시 호출해 다른 질문을 만들지 않는다.

## 공개 메시지와 보류 항목

확정 입력은 `{ "type": "answer", "turn": 3, "text": "답변 내용" }`다. 서버는 `turn`이 현재 답변 가능한 turn과 일치할 때만 저장한다. 서버 메시지 이름은 `answerReceived`, `thinking`, `evidenceCheck`, `question`, `interviewEnd`, `error`다. `question`은 `persona`, `text`, `turn`을 포함하며 질문 전달 완료를 의미한다. 예전 타입의 `role`, `answerStart`, `answerEnd`, `transcript`, `questionEnd`를 Sprint 1 기준으로 쓰지 않는다.

`answerReceived`는 저장 완료 신호이지 다음 질문에 답해도 된다는 뜻은 아니다. FE는 제출 중 상태를 해제하되 입력창은 다음 `question` 도착 전까지 잠근다. 내부 판단·raw output을 WS로 그대로 내보내지 않는다.

별도 `clientSubmissionId`는 Sprint 1에 추가하지 않는다. 같은 연결의 진행 중 중복은 service 상태/lock으로 막고, turn mismatch나 이미 답변된 turn의 메시지는 저장하지 않는다. 동일 본문이라는 이유로 모든 반복 답변을 중복 처리하지 않는다.

WS 경로는 `/api/ws/interviews/{sessionId}`이며 REST route는 `interviewId`를 사용한다. `POST /interviews`와 `GET /interviews/{id}`는 `sessionId`를 반환한다. WS 인증은 [공통 0003](../../shared/decisions/0003-sprint1-session-auth.md)에 따라 HttpOnly `devon_session` 쿠키와 Redis 로그인 세션으로 handshake 시 확인한다. 로그인 세션 ID는 면접 `sessionId`와 별개다. 준비 실패 snapshot은 `GET /interviews/{id}`의 `lastError`와 `prepareSteps`로 복구하고, 준비 재시도는 `POST /interviews/{id}/prepare/retry` REST endpoint로 처리한다. Sprint 1에서는 연결 끊김·재연결 실패만으로 `abandoned`를 설정하지 않는다.

명시적 나가기 확인·레포 재선택만 abandoned로 처리하는 기존 정책을 유지한다. 사용자 종료 요청의 정확한 wire는 이 동작과 기존 소유권에 맞춰 BE·FE 연결 시 구체화하며 메시지 필드·WS/REST를 사용자에게 개별 선택으로 묻지 않는다. 내부 Controller에서 종료 이후 결과 차단을 검사할 수 있지만, 실제 송수신 계약을 기록·검증하기 전 종료 연동 완료를 주장하지 않는다.

질문 생성이 허용된 시도 후에도 실패하면 기존 기록 보존·오류 안내·명시적 나가기와 새 면접 흐름을 유지한다. 진행 중 면접의 새 수동 이어가기 기능을 추가하지 않는다. 오류 안내나 WS 연결 종료는 DB의 completed/abandoned 확정과 다르며, 재연결을 실패한 LLM 작업의 자동 재호출로 사용하지 않는다. 재시도는 0010의 공통 계층 1회·semantic 실패 재호출 금지가 우선한다. 오류 전달·종료·실패 보존의 실제 연결은 AI-L09·AI-L12·AI-L18에서 구현 검증한다.

## 수용 검사

- 첫 질문 HR, 정상 9턴의 6·2·1 횟수, 잔여 횟수가 없는 Persona 선택 거절, 9번째 답변 후 종료와 10번째 질문 없음을 확인한다.
- 후속 답변 보완·기여 정정·Persona 전환 후에도 같은 기록 참조.
- 없는 Evidence·범위 밖 repo·잘못된 ref·중복 질문 후보 차단.
- JSON/Tool/재계획 실패로 질문 또는 답변이 두 번 확정되지 않음.
- 유효한 목적의 표현 오류, 거짓·stale·반복 목적, 공급된 제약에서 유효 후보가 없는 경우를 각각 재작성·재계획·유효 후보 없음으로 구분.
- 사용자 종료 중 늦게 도착한 모델 결과가 질문을 저장·전달하지 않음.
- 공개 텍스트 프로토콜과 내부 결정 객체가 분리됨.
- 미합의 reconnect/stale 제출 보장을 완료로 주장하지 않음.

실행 환경과 모델 평가 범위는 [검증 기준](../verification.md)에 따른다.
