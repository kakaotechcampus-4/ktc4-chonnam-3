# task-07 - 도메인 질문 프레임 정책

상태: 구현 가이드. 생성 정책과 개발용 후보는 승인됐지만 runtime seed와 Director 연결은 아직 구현되지 않았다.

## 목표

- `domain_lead`가 사용할 질문 생성 정책을 결정적 검사와 개발용 fixture로 구현한다.
- FIX인 7개 category와 category별 3개, 총 21개 후보를 변경 없이 검증한다.
- 개발용 후보와 운영 seed 승인·설치·활성 version을 분리한다.
- 별도 도메인 Agent, 점수, 외부 지식 조회를 만들지 않는다.

## 근거

- [도메인 질문 프레임의 고정 범위·선택과 질문 생성](../../spec/ai/features/domain-frames.md)
- [0005 도메인 질문 생성과 개발용 후보 유지 결정](../../spec/ai/decisions/0005-domain-question-policy.md)
- [0008 AI 후보 검증·선택 정책](../../spec/ai/decisions/0008-ai-candidate-policy.md)의 도메인 frame 후보 선택
- [Director와 텍스트 면접의 Persona·질문 검증](../../spec/ai/features/interviewer.md)
- [AI 내부 계약의 Question·domain_frames 제안](../../spec/ai/contracts.md)
- [BE 도메인 seed 작업](../../backend/docs/task-03-seed.md)
- [잔여 결정 목록의 AI-L02·AI-L10](../../later.md)

## 선행 조건

- [전체 AI pipeline](pipeline.md)과 [task-02 내부 계약](task-02-contracts.md)의 Proposed 경계를 확인한다.
- [task-06 Context 준비](task-06-context-preparation.md)에서 검증된 category 입력만 받는다는 전제를 둔다.
- 21개 후보의 구조, 승인된 생성 정책과 frame 우선순위는 비식별 fixture로 즉시 검증할 수 있다.
- 실제 seed 설치, table column, 검토 metadata와 활성 version은 BE·도메인 검수자의 합의 전에는 진행하지 않는다.

## 대상 파일과 책임

- [AI Director 모듈](../src/devon_ai/agents/director/agent.py): 향후 단일 Director가 정책을 소비할 위치이며 현재 docstring뿐이다.
- [AI 계약 자리](../src/devon_ai/contracts.py): 채택된 category/frame 참조 타입만 두며 현재 미구현이다.
- [BE Director adapter](../../backend/app/agents/director/agent.py): prompt/seed 조회 결과를 AI에 주입하는 연결 경계다.
- BE는 `domain_question_frames` 조회, seed 설치·재실행, 활성 version과 검수 metadata를 소유한다.
- AI는 전달받은 검수된 frame에서 질문 후보를 만들고 정책 위반 여부를 판정한다.
- [task-10 Director](task-10-director.md)는 Persona·턴 선택을 소유하며 이 작업은 그 정책 입력을 준비한다.

## 작업

- [ ] category 집합이 `finance`, `game`, `travel`, `shopping`, `medical`, `mobility`, `etc`인지 검사한다.
- [ ] 각 category에 민감정보, 신뢰성·운영, 사용자 경험·서비스 맥락 축이 하나씩 있는지 검사한다.
- [ ] 총 21개 후보와 원문을 source spec 대조 fixture에 고정하고 임의 수정하지 않는다.
- [ ] category가 없거나 신뢰하기 어려우면 산업을 추측하지 않고 `etc`를 선택한다.
- [ ] 확인된 category가 있으면 모델 선호로 다른 category로 바꾸지 않는다.
- [ ] 적격 frame 중 검증된 서비스 맥락·질문 목적에 더 직접 관련된 후보를 우선한다.
- [ ] 관련성이 같으면 이전 질문의 목적을 덜 반복하는 후보를 선호한다.
- [ ] 한 질문에는 중심 목적 하나만 남기고 복합·유도 질문을 거절한다.
- [ ] 확인되지 않은 경력·프로젝트·회사·규제 조건은 가정형으로 표현한다.
- [ ] 기술 질문을 표현만 바꿔 반복하지 않고 운영·사용자 영향·판단 이유를 묻는다.
- [ ] JD 자격요건 검사나 실제 산업 경력 확인 질문으로 변질된 후보를 거절한다.
- [ ] 법률·의료적 정답, 규제 준수 보증, 전문가 조언으로 표현된 후보를 거절한다.
- [ ] domain 전용 score·가중치·합격 기준을 출력하거나 저장하지 않는다.
- [ ] frame을 사용자 프로젝트의 Evidence나 개인 경험 근거로 사용하지 않는다.
- [ ] 답변에 검증 가능한 코드 주장이 생긴 경우에만 기존 Evidence 흐름에 넘긴다.
- [ ] 질문 문구를 prompt나 Director 코드에 하드코딩하지 않고 주입 경계를 유지한다.
- [ ] Persona는 기존 `domain_lead`를 사용하고 별도 Agent·package·taxonomy를 추가하지 않는다.
- [ ] domain/HR 각각의 새 최소 횟수나 고정 교대 규칙을 만들지 않는다.
- [ ] 세 축의 고정 순환·축별 최소 횟수·relevance 점수·모든 축 소진 의무를 만들지 않는다.

## 검증

- 예정 테스트: `ai/tests/agents/director/test_domain_frames.py` (추가 예정, 현재 없음).
- [ ] 7개 category x 3개 축과 총 21개 후보의 보존을 검사한다.
- [ ] category 없음·불신 입력의 `etc` fallback과 확인된 category 보존을 대조한다.
- [ ] 적격 후보가 여러 개일 때 검증된 맥락 관련성과 목적 비반복 순으로 선택되는지 검사한다.
- [ ] 중심 목적 하나와 복합 질문, 가정형과 경력 단정을 짝지어 검사한다.
- [ ] 기술 질문 중복, JD 검사, 법률/의료 보증, 점수화를 금지 사례로 둔다.
- [ ] domain 경험이 없다는 답변을 감점 근거로 바꾸지 않는지 검사한다.
- [ ] fixture 정책 통과를 운영 문구 독립 검수나 실제 모델 품질 통과로 보고하지 않는다.
- [ ] 실제 seed가 없는 현재 상태에서는 DB 설치·version 재현 검증을 미실행으로 기록한다.

## 완료 조건

- [ ] 승인된 fallback·목적·가정형·중복 방지 정책이 순수 fixture에서 재현된다.
- [ ] frame 관련성·목적 비반복 우선순위가 고정 순환이나 새 quota 없이 재현된다.
- [ ] 21개 후보 원문과 세 축 구조가 변경되지 않는다.
- [ ] Director 정책과 BE seed 운영 책임이 분리된다.
- [ ] 별도 Agent·점수·외부 지식 조회·하드코딩이 없다.
- [ ] 운영 seed 설치와 활성 version 검증은 실제 승인 전 완료로 표시되지 않는다.

## 결정 대기와 재개 조건

- AI-L10: 운영 문구의 독립·도메인 검수, category 신뢰 입력, 활성 version·저장 방식이 승인되면 BE seed 설치와 실제 조회 연결을 재개한다.
- AI-L02: `domain_frames` 참조와 Question Contract의 정확한 필드·version·저장 위치가 채택되면 타입 검증을 고정한다.
- AI-L04: 실제 모델 호출·재작성 횟수와 budget이 정해지기 전에는 정책 위반 후보를 무제한 재생성하지 않는다.
