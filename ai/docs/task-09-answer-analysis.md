# task-09 - 답변 정성 분석

상태: 구현 가이드. 정성 평가 의미와 보존 원칙은 승인됐지만 task runtime·저장·복구는 아직 구현되지 않았다.

## 목표

- [답변 분석 task](../src/devon_ai/llm_tasks/answer_analysis.py)에 질문 범위 안의 정성 분석을 구현한다.
- 충분성, 기술적 정확성, 기여·근거 정합성을 서로 대체하지 않는 세 축으로 다룬다.
- 평가 가능 여부와 축별 자료 부족을 구분하고 점수나 개인 기여를 만들어내지 않는다.
- 후속 보완·기여 정정을 반영하되 최초 답변 원문과 최초 분석을 보존한다.

## 근거

- [답변 분석과 평가의 세 판단·후속 답변과 정정](../../spec/ai/features/answer-evaluation.md)
- [0004 답변 정성 평가와 후속 보완 결정](../../spec/ai/decisions/0004-answer-assessment-policy.md)
- [0003 추가 근거 조회와 결과 해석 결정](../../spec/ai/decisions/0003-evidence-lookup-policy.md)
- [0008 AI 후보 검증·선택 정책](../../spec/ai/decisions/0008-ai-candidate-policy.md)의 구조화 실패·질문 복구 선택
- [Director와 텍스트 면접의 답변부터 다음 질문까지](../../spec/ai/features/interviewer.md)
- [AI 내부 계약의 AnswerAnalysis 제안](../../spec/ai/contracts.md)
- [잔여 결정 목록의 AI-L02·AI-L04·AI-L09·AI-L18](../../later.md)

## 선행 조건

- [전체 AI pipeline](pipeline.md)과 [task-02 내부 계약](task-02-contracts.md)의 Proposed 상태를 확인한다.
- [task-06 Context 준비](task-06-context-preparation.md)의 확정 질문·Contract·답변 원문 fixture를 입력으로 사용한다.
- [task-08 Evidence Tool](task-08-evidence-tools.md)의 조회 필요성·결과 해석 정책을 따른다.
- 실제 enum·JSONB·복구 상태가 미정이어도 승인된 세 축과 보존 정책의 fixture 검증은 진행할 수 있다.

## 대상 파일과 책임

- [AI answer_analysis](../src/devon_ai/llm_tasks/answer_analysis.py): 단발 분석 후보 생성과 의미 검증을 소유하며 현재 docstring뿐이다.
- [AI 계약 자리](../src/devon_ai/contracts.py): 채택 후 입력·출력 타입을 두며 현재 실제 클래스가 없다.
- [BE turn service](../../backend/app/features/interview/turn_service.py): 확정 답변과 분석·결정의 저장 순서를 소유한다.
- [BE Director adapter](../../backend/app/agents/director/agent.py): 검증된 분석을 다음 행동 후보에 전달한다.
- BE는 DB 상태, Tool 실행, 서비스 상태·공개 흐름 복구, WS/API 변환과 원문 보존을 소유한다.
- LLM 호출 attempt와 retry는 AI-L04가 SDK/client/task/worker 중 선택한 한 계층만 소유한다.
- AI task는 DB session을 받거나 다음 질문·점수·최종 상태를 직접 확정하지 않는다.

## 작업

- [ ] 현재 질문, 전달 전에 확정된 Contract, 제출된 답변 원문의 대응을 먼저 검사한다.
- [ ] 다른 Turn 답변, 초안, 전송 오류, 질문 전제 오류, 해석 불가 입력을 구분한다.
- [ ] 평가 가능 여부를 먼저 판정하고 잘못된 질문을 사용자 역량 부족으로 바꾸지 않는다.
- [ ] 자료 부족이면 확인할 수 없는 축만 보류하고 관찰 가능한 충분성까지 일괄 보류하지 않는다.
- [ ] 충분성은 실제 질문의 required point만 충분·부분·불충분 의미로 비교한다.
- [ ] 질문하지 않은 항목을 누락으로 추가하지 않고 답변 구절을 근거로 남긴다.
- [ ] 기술적 정확성은 적용 조건·버전, 타당한 설명·오류·판단 보류를 구분한다.
- [ ] 유효한 대안을 모델 선호와 다르다는 이유로 오류 처리하지 않는다.
- [ ] 기여 범위는 본인·공동·타인·미확인을 사용자 발언과 외부 근거로 나눠 본다.
- [ ] 코드 존재, README 문구, commit 수만으로 개인 작성·담당 업무를 확정하지 않는다.
- [ ] 답변 길이·전문용어 수·Persona를 대리 점수로 사용하지 않는다.
- [ ] 정상 제출된 “모르겠습니다”를 처리 오류·거짓말·기술 오류로 자동 판정하지 않는다.
- [ ] 검증할 주장 원문·목적·repo/ref/허용 위치를 구조화하되 Tool을 직접 실행하지 않는다.
- [ ] 추가 조회는 task-08의 세 조건을 모두 만족할 때만 요청 후보로 만든다.
- [ ] 미조회·정상 미발견·분석 부족·Tool 장애·실제 불일치의 의미를 유지한다.
- [ ] 후속 답변이 앞선 부족점을 보완하면 Turn 연결을 통해 이후 판단에 반영한다.
- [ ] 본인 기여 정정은 이후 질문 전제에 반영하되 과거 원문·최초 분석을 덮어쓰지 않는다.
- [ ] 새 이력 테이블, 과거 답변 편집·재평가 API, 리포트 재생성을 임의로 추가하지 않는다.
- [ ] 정성 label을 숫자로 환산하거나 공개 점수·가중치·합격 기준을 생성하지 않는다.
- [ ] parse/schema/semantic 실패를 구분하고 빈 성공·default inference·누락값 보충·ad hoc repair로 넘기지 않는다.

## 검증

- 예정 테스트: `ai/tests/llm_tasks/test_answer_analysis.py` (추가 예정, 현재 없음).
- [ ] 같은 질문의 충분·부분·불충분 답변이 Contract 기준으로 구분되는지 검사한다.
- [ ] 길고 틀린 답변과 짧고 타당한 답변에서 충분성과 정확성이 독립적인지 검사한다.
- [ ] 질문 오류, 해석 불가, 정상 “모르겠습니다”, 실제 설명 부족을 대조한다.
- [ ] 코드 자료 부족 시 정확성만 보류하고 관찰 가능한 다른 축은 유지하는지 검사한다.
- [ ] 팀원 구현을 본인 기여로 만들지 않고 이후 기여 정정을 반영하는지 검사한다.
- [ ] 유사하지만 무관한 코드와 다른 ref를 지지 근거로 채택하지 않는지 검사한다.
- [ ] 후속 보완 뒤에도 최초 답변·최초 분석이 그대로 남는지 검사한다.
- [ ] mock schema 통과는 실제 모델 품질, DB 보존, 공개 응답 검증을 대신하지 않는다.
- [ ] 다른 Turn/ref를 인용한 구조상 정상 결과를 semantic 실패로 거절하는지 검사한다.

## 완료 조건

- [ ] 세 축과 평가 가능 여부가 서로 독립된 의미로 검증된다.
- [ ] 모든 판단이 실제 질문 범위·답변 구절·검증된 근거 또는 명시한 한계를 가진다.
- [ ] 개인 기여·점수·미확인 사실을 생성하지 않는다.
- [ ] 후속 보완과 기여 정정이 반영되며 최초 기록은 보존된다.
- [ ] 저장·복구·공개 변환 미합의 상태를 runtime 완료로 표시하지 않는다.

## 결정 대기와 재개 조건

- AI-L02: 평가 상태·세 축 필드·null·enum·Question Contract·JSONB 위치가 채택되면 실제 타입과 저장 변환을 고정한다.
- 질문 후보의 rewrite/replan/failure 선택은 ADR 0008에 따라 즉시 검사한다. AI-L09에서 사용자 입력과 runtime 상태 복구가 합의되면 Director·서비스 공개 복구 흐름을 연결한다.
- AI-L18: 실패 raw output, 답변 원문, 최초 분석·정정 이력의 위치·권한·마스킹·보존/삭제가 정해지면 운영 보존 검증을 완료한다.
- AI-L04: 실제 호출 timeout·재시도 주체·attempt 계산이 정해지기 전에는 provider 실행 완료를 주장하지 않는다.
- 공개 점수와 품질 수용 기준은 각각 AI-L15·AI-L19의 별도 결정이며 이 작업에서 정하지 않는다.
