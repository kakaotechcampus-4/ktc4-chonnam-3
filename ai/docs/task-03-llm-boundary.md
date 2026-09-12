# task-03 - provider 중립 LLM 경계

> 상태: 구현 가이드. 실제 provider 연결과 AI runtime 호출은 아직 구현되지 않았다.
> 선행: [전체 순서](pipeline.md), [task-01 패키지 셋업](task-01-setup.md), [task-02 내부 계약](task-02-contracts.md)

## 목표

AI 로직은 주입된 모델 호출 경계만 소비하고, 구체 transport·인증·설정·prompt 조회는 기존 BE 파일이 소유하게 한다. 실제 provider를 가정하지 않는 fake로 호출·실패 정책을 검토하며 새 AI gateway 클래스나 모듈을 만들지 않는다.

## 근거

- [AI 내부 계약](../../spec/ai/contracts.md)의 `Model Gateway와 실패`, `task별 structured output 범위`
- [AI 작업 Context](../../spec/ai/features/job-context.md)의 `LLM 경계`
- [AI 아키텍처](../../spec/ai/architecture.md)의 `책임과 의존 방향`, `공통 품질 원칙`
- [AI 구현 기준선](../../spec/ai/decisions/0001-ai-baseline.md)의 논리 모델과 실제 API 식별자 구분
- [0008 AI 후보 검증·선택 정책](../../spec/ai/decisions/0008-ai-candidate-policy.md)의 구조화 후보 실패
- [0009 AI 평가 방법과 비교 실험](../../spec/ai/decisions/0009-ai-evaluation-method.md)의 합성 입력 격리·통제 비교
- [의사결정 대기 목록](../../later.md)의 `AI-L01`, `AI-L02`, `AI-L04`, `AI-L18`
- 기존 BE [LLM client](../../backend/app/integrations/llm/client.py), [설정 진입점](../../backend/app/core/config.py), [prompt loader](../../backend/app/llm_tasks/prompt_loader.py)

## 선행 조건

- provider 독립 fake와 순수 성공·실패 fixture는 AI-L01 전에 작성할 수 있다.
- 주입 callable의 정확한 signature, 요청/응답 타입 또는 Protocol은 AI-L02에서 채택된 계약만 사용한다.
- 실제 provider, 호출 가능한 model ID, 인증 설정과 기능은 AI-L01 확인 전 코드·seed·문서 기본값으로 만들지 않는다.
- parse/schema/semantic 실패 구분과 invalid 후보의 fail-closed 처리는 Accepted다. 실제 재시도 주체·횟수, semantic 재호출, timeout과 task별 budget은 AI-L04에서 확정해야 production 호출을 연결할 수 있다.
- 사용자 원문·raw output·호출 metadata의 production 보존은 AI-L18의 위치·권한·마스킹·보존 결정 뒤 연결한다.

## 대상 파일과 책임

- [backend/app/integrations/llm/client.py](../../backend/app/integrations/llm/client.py): 구체 SDK transport, 응답 metadata 수집과 provider/transport 실패 매핑을 맡는다.
- [backend/app/core/config.py](../../backend/app/core/config.py): 승인된 provider credential, model ID, timeout/budget 설정의 단일 환경 진입점이다.
- [backend/app/llm_tasks/prompt_loader.py](../../backend/app/llm_tasks/prompt_loader.py): DB session을 받는 유일한 LLM task 경계로 prompt 문자열·version과 승인된 설정을 로드한다.
- `ai/tests/test_llm_boundary.py` (추가 예정, 현재 없음): provider 독립 fake, timeout/provider/parse 실패와 metadata fixture를 둔다.
- `devon_ai` task는 BE/SDK/DB를 import하지 않고 주입값만 소비한다. 별도 `gateway.py`, provider package, facade 또는 client class를 추가하지 않는다.

## 작업

- [ ] 채택된 task input/output과 typed failure만 통과시키는 최소 주입 경계를 정의한다.
- [ ] fake가 정상 JSON, timeout, provider 오류, 깨진 JSON, schema/의미 오류를 독립적으로 반환하게 한다.
- [ ] 구조화 문서를 읽지 못한 parse 실패, 읽었지만 계약을 어긴 schema 실패, 구조는 맞지만 참조·Persona·근거·범위를 어긴 semantic 실패를 구분한다.
- [ ] `prompt_loader`가 task 이름에 맞는 prompt 문자열과 version을 로드하고 task에 DB session을 넘기지 않게 한다.
- [ ] prompt, model ID, credential을 AI 소스나 task 상수로 하드코딩하지 않는다.
- [ ] AI-L02에서 채택한 task 계약과 ADR 0008의 semantic 검증을 통과하기 전에는 어느 계층도 provider 응답을 downstream 성공으로 확정하지 않게 한다.
- [ ] timeout/provider 오류/JSON parse 실패의 FIX 재시도 1회를 정책 fixture로 표현하되 관리 계층과 운영값은 AI-L04 전 확정하지 않는다.
- [ ] SDK·client·task·worker의 중복 재시도로 총 호출 수가 곱해지는 시나리오를 실패 사례로 둔다.
- [ ] 어떤 invalid 후보도 빈 성공·추측한 기본값·누락값 보충·ad hoc repair로 바꾸지 않고 task 범위 typed failure로 반환한다.
- [ ] token 값을 provider가 주지 않으면 0으로 추정하지 않고 미수집 상태를 보존한다.
- [ ] model, prompt version, schema version, latency, attempt, 오류 metadata 후보에서 비밀키와 원문 로그를 분리한다.
- [ ] ad hoc repair, 무제한 재생성, provider fallback 또는 task별 모델 분리는 승인 없이 추가하지 않는다.
- [ ] 실제 연결 전 fake와 같은 계약 검사를 concrete transport adapter에도 재사용할 수 있게 한다.

## 검증

- [ ] fake 정상 결과가 DB·네트워크 없이 채택된 검증 경계를 통과하는지 확인한다.
- [ ] timeout, provider 오류와 parse/schema/semantic 실패가 서로 구분되고 최종 실패가 downstream 성공으로 전달되지 않는지 확인한다.
- [ ] invalid 후보가 빈 객체·default inference·누락값 보충·ad hoc repair로 성공 처리되지 않는지 확인한다.
- [ ] 중복 retry fixture에서 한 논리 작업의 attempt가 여러 계층에서 증가하지 않는지 확인한다.
- [ ] prompt/model/config가 호출 시 주입되고 AI package가 BE 설정이나 환경변수를 직접 읽지 않는지 확인한다.
- [ ] credential, GitHub token, 사용자 원문과 raw output이 일반 application log에 출력되지 않는지 확인한다.
- [ ] 계획 테스트를 추가한 뒤 [테스트 안내](testing.md)의 AI 단위 검사와 BE adapter 검사를 각각 실행한다.
- [ ] 실제 모델 호출은 별도 평가로 기록하고 mock 통과를 provider 적합성·비용·품질 완료로 보고하지 않는다.
- [ ] 모델 비교는 task-12의 같은 합성 JSON 쌍·source group에서 한 요인만 바꾸고 실패·품질·비용·지연을 함께 기록한다.
- [ ] 기대·검수·control metadata가 prompt나 Tool 입력으로 유출되지 않는지 평가 경계에서 확인한다.

## 완료 조건

- [ ] provider 독립 fake와 기존 BE transport/config/prompt loader의 책임이 분리되어 있다.
- [ ] 새 AI gateway 클래스·모듈·Protocol 또는 승인되지 않은 설정 필드가 없다.
- [ ] 실패 분류·fail-closed 정책과 metadata 경계가 승인된 결정에 맞게 검증된다.
- [ ] 실제 model ID, 운영 budget, 보존 정책이 확인되기 전 production 호출 완료로 표시하지 않는다.
- [ ] ADR 0009의 비교 방법 적용을 실제 수치 목표·provider 선택·출시 승인으로 해석하지 않는다.

## 결정 대기와 재개 조건

- AI-L01은 AI·BE가 provider, 실제 model ID, 인증 설정, 지원 기능과 버전 기록 방식을 검증하면 실제 transport 연결을 재개한다.
- AI-L02는 AI·BE가 정확한 task 입력·출력·실패 계약과 schema version을 채택하면 해당 계약의 runtime 검증을 재개한다.
- AI-L04는 AI·BE가 attempt 관리 주체와 횟수, semantic 재호출 여부, timeout·token·Context·동시성 budget과 소진 처리를 기록하면 production retry와 제한을 재개한다.
- AI-L18은 운영 담당과 저장 위치, 접근권한, 마스킹, 보존·삭제, metadata 범위를 승인하면 실제 원문·raw output 기록을 재개한다.
- 이 결정들 전에도 Proposed fixture 기반 fake, 설정값 양수·일관성 검사, 중복 retry 차단 시나리오는 계속 진행한다.
