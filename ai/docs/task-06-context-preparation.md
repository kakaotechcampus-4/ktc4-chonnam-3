# task-06 - 면접 Context 준비 경계

상태: 구현 가이드. AI·BE runtime과 해당 통합 테스트는 아직 구현되지 않았다.

## 목표

- 면접 준비에 필요한 입력과 준비 완료 조건을 AI·BE 사이의 점검표로 고정한다.
- 이 작업은 새 AI Context Builder, Agent 또는 package를 만드는 작업이 아니다.
- 선택·권한·DB/Redis·pipeline·첫 질문 저장은 BE 책임으로 유지한다.
- 미결정 schema나 준비 성공 기준을 추측하지 않고 독립 fixture 검증부터 진행한다.

## 근거

- [작업 Context의 Context Builder 입력·멱등성과 stale 결과 차단](../../spec/ai/features/job-context.md)
- [Director와 텍스트 면접의 준비와 첫 질문](../../spec/ai/features/interviewer.md)
- [AI 내부 계약의 Context 입력·Question Contract 제안](../../spec/ai/contracts.md)
- [0008 AI 후보 검증·선택 정책](../../spec/ai/decisions/0008-ai-candidate-policy.md)의 L2 관찰과 질문 복구 경계
- [BE 면접 명세의 prepareStep·실패 상태](../../spec/backend/features/interview.md)
- [BE pipeline의 analysis_run과 interview_prep](../../backend/docs/pipeline.md)
- [잔여 결정 목록의 AI-L02·AI-L06·AI-L09·AI-L11~AI-L14](../../later.md)

## 선행 조건

- [전체 AI pipeline](pipeline.md)의 단계와 소유권을 먼저 확인한다.
- [task-02 내부 계약](task-02-contracts.md)의 fixture 형태를 사용하되 Proposed를 채택된 schema로 보지 않는다.
- 검증된 posting/JD와 [task-04 L1 분석](task-04-repo-shallow.md), [task-05 L2 분석](task-05-repo-deep.md)의 검증된 출력만 준비 입력으로 사용한다.
- AI-L06이 풀리기 전에도 유효/무효 path, 잘못된 ref, 부분 L2 fixture 검사는 진행할 수 있다.

## 대상 파일과 책임

- [AI 계약 자리](../src/devon_ai/contracts.py): 채택 후 Context 타입을 둘 위치이며 현재 docstring뿐이다.
- [BE 면접 준비](../../backend/app/features/interview/prepare.py): L2 근거 전개와 고정 SHA 사용을 소유한다.
- [BE 준비 pipeline](../../backend/app/features/analysis/pipeline/interview_prep.py): primary 1~2개 선정, L2, `notable_areas` 검증, context snapshot, 첫 `hr_manager` 질문의 orchestration을 소유한다. 기존 7단계는 [BE pipeline](../../backend/docs/pipeline.md)의 `analysis_run` 책임이다.
- [BE worker](../../backend/app/workers/tasks/interview_prep.py): 승인된 직렬화 인수로 pipeline을 호출한다.
- [BE 면접 service](../../backend/app/features/interview/service.py): 사용자·공고·선택·상태 검사를 소유한다.
- [BE turn service](../../backend/app/features/interview/turn_service.py): 첫 질문·Persona·근거 관계의 확정 저장을 소유한다.
- AI는 BE가 검증해 주입한 최소 입력만 소비하며 DB session, Redis client, token을 받지 않는다.

## 작업

- [ ] 현재 사용자, analysis run, interview가 서로 일치하는지 검사하는 fixture를 만든다.
- [ ] 선택 저장소 1~5개, 성공한 L1, primary 1~2개라는 FIX 조건을 입력 사례에 반영한다.
- [ ] primary의 L2와 `notable_areas`가 같은 `snapshot_head_sha`를 가리키는지 검사한다.
- [ ] 다른 사용자 repo, 선택에서 제외된 repo, 다른 ref의 분석·Evidence를 입력에서 거절한다.
- [ ] 공고/JD, domain category, 선택 repo, 분석 범위의 출처를 서로 구분한다.
- [ ] 비밀키·GitHub token·ORM 객체·DB session·불필요한 과거 원문이 payload에 없음을 검사한다.
- [ ] 준비 단계 의존성은 criteria가 준비된 뒤 첫 질문을 구성하도록 보존한다.
- [ ] 첫 질문은 `hr_manager`이며 코드 Evidence 없이 허용되는 fixture를 둔다.
- [ ] 경력·개인 기여를 추정하지 않는 자기소개 질문 후보만 허용한다.
- [ ] 질문·Persona·Question Contract 후보가 전달 전에 함께 검증되는 경계를 표시한다.
- [ ] Question Contract 저장 구조가 미정이면 fixture 검토까지만 하고 DB column을 추가하지 않는다.
- [ ] 준비 성공과 `preparing_failed`를 구분하고 이를 사용자 이탈 `abandoned`로 바꾸지 않는다.
- [ ] PostgreSQL을 원본으로 두고 Redis snapshot hit/miss/expiry/손상 복구 사례를 정의한다.
- [ ] Redis snapshot이 종료 상태나 최신 DB turn보다 우선하지 않는지 검사한다.
- [ ] 외부 호출 뒤 SHA·prompt version·현재 상태가 바뀐 stale 결과를 확정하지 않는다.
- [ ] 첫 질문 저장 뒤 알림만 실패하면 저장된 질문을 재사용하고 새 질문을 생성하지 않는다.
- [ ] 실제 selection, 조회, transaction, snapshot 갱신, 공개 이벤트는 BE 인계 항목으로 남긴다.
- [ ] 새 turn job이나 독립 `deep_analysis` queue를 이 작업에서 만들지 않는다.

## 검증

- 예정 테스트: `backend/tests/features/interview/test_prepare_context.py` (추가 예정, 현재 없음).
- [ ] 정상 입력과 다른 사용자·미선택 repo·ref 불일치 입력을 대조한다.
- [ ] L1 누락, primary L2 누락, 사용 가능·제한·무효 notable area를 서로 다른 fixture로 둔다.
- [ ] AI-L06 결정 전에는 부분 결과의 최종 성공/실패 기대값을 임의로 고정하지 않는다.
- [ ] Redis hit, miss, expiry, 손상에서 PostgreSQL 기준 결과가 동일한지 검사한다.
- [ ] 중복 worker, 종료 중 완료, 저장 후 알림 실패에서 첫 질문이 두 번 확정되지 않는지 검사한다.
- [ ] 준비 실패 시 일반 fallback 질문으로 `in_progress`를 시작하지 않는지 검사한다.
- [ ] 첫 질문의 목적·전제는 유효하나 표현만 결함이면 rewrite 후보, 거짓·stale·중복 전제면 replan 후보로 구분하고 안전한 후보가 없으면 유효 후보 없음 실패를 반환하는지 검사한다.
- [ ] 유효 후보 없음 실패를 임의로 `preparing_failed`나 공개 오류에 매핑하지 않는다.
- [ ] 실제 provider·DB·Redis·WS를 연결하지 않은 fixture 성공은 production 준비 완료로 보고하지 않는다.

## 완료 조건

- [ ] 준비 입력의 출처·선택·권한·SHA 검증 책임이 AI와 BE 사이에 명확히 나뉜다.
- [ ] 첫 질문 후보 생성과 BE 영구 저장·전달의 경계가 테스트로 확인된다.
- [ ] DB 원본과 Redis snapshot의 우선순위·복구가 테스트된다.
- [ ] 준비 성공/실패와 사용자 이탈을 혼동하지 않는다.
- [ ] 새 Context Builder나 미승인 schema·queue·공개 상태가 추가되지 않는다.

## 결정 대기와 재개 조건

- AI-L02: Context·Question Contract의 필드, enum, null, version, 저장 위치가 채택되면 실제 타입·변환 검증을 재개한다.
- AI-L06: L2 부분 실패와 `preparing_failed` 매핑이 합의되면 readiness 판정을 고정한다.
- AI-L09: 유효 후보 없음의 실제 반환 계약과 BE/FE 준비 상태·사용자 복구 매핑이 합의되면 첫 질문 실패 연결을 고정한다.
- AI-L11: worker signature·payload·timeout·retry 책임이 정해지면 실제 enqueue 연결을 재개한다.
- AI-L12: transaction·중복 방지·저장 후 알림 실패 복구가 정해지면 멱등성 구현을 완료한다.
- AI-L13·AI-L14: WS 식별·준비 상태·재연결 계약이 정해져야 공개 준비 완료 흐름을 완료로 표시한다.
