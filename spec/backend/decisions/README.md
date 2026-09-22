# 결정 기록
상태: Proposed → Accepted → Superseded. 날짜·검토자·관련 PR을 실제 확인 후 기록한다.
원본 기록은 삭제하지 않는다. README에는 현재 유효한 핵심 결정 5~10개를 목표로 연결하되 개수를 채우려고 결정을 만들지 않는다.

## 작성 형식
- 제목 / 상태 / 날짜 / 관련 PR / 검토자
- 맥락: 해결할 문제
- 결정: 선택한 방법
- 이유: 대안과 선택 근거
- 영향: 영향 팀·계약·테스트·이관·되돌리기
- 대체 관계: 이전 또는 후속 결정 링크

팀 내부 결정만 기록한다. 계약·용어 영향이 있으면 spec/shared/decisions로 승격하고 이곳에는 링크를 둔다.

## 관련 공통 결정

- [0002 로컬 정책 기준 채택](../../shared/decisions/0002-local-policy-baseline.md): 2026-09-22 사용자 결정. 포트폴리오 20MB와 공고 재사용 7일은 유지하며 면접 배분은 후속 0004로 대체한다. 실제 BE 연결·검증은 구현 작업으로 남긴다.
- [0004 면접 질문 배분의 기존 기준 복원](../../shared/decisions/0004-flexible-persona-allocation-restoration.md): 2026-09-22 사용자 결정. 정상 9턴·첫 HR을 유지하고 기술 목표 6턴·최소 5턴, 도메인·HR 합산 최소 3턴과 개별 배분 비고정을 복원한다. DB·공개 API 구조는 유지하며 실제 횟수 제어는 구현·검증 대기다.
- [0003 Sprint 1 세션 인증](../../shared/decisions/0003-sprint1-session-auth.md): 2026-09-22 사용자 결정. Redis `auth:sess:{sid}`·HttpOnly `devon_session`·14일 sliding 세션을 사용하고 JWT·refresh는 Sprint 2로 넘긴다. SQL `auth_sessions` 제외와 GitHub token의 암호화 DB 저장을 유지하며 실제 인증 연결은 구현·검증 대기다.

## 관련 AI 결정

- [0011 Sprint 1 모델 선택](../../ai/decisions/0011-sprint1-model-selection.md): 2026-09-21 사용자 결정. Sprint 1 LLM 모델은 OpenAI `gpt-5.6-luna`다. 인증·SDK/client·호출 경로·버전 기록 방식은 AI-L01에서 계속 검토한다.
- [0012 질문별 평가 기준의 저장과 구성](../../ai/decisions/0012-question-contract.md): 부분 대체된 이력. 기존 다섯 내용 항목·같은 Turn 저장·당시 자료 보존은 유지하며 현재 형식은 0014를 따른다.
- [0013 답변 분석과 다음 행동 판단의 저장](../../ai/decisions/0013-turn-analysis-decision.md): 부분 대체된 이력. 두 JSONB 위치는 유지하며 추가 저장 객체·상태·조회별 쓰기는 0014로 대체한다.

- [0014 기존 설계를 유지하는 최소 변경 재결정](../../ai/decisions/0014-minimal-change-revision.md): 2026-09-21 사용자 결정. 기존 평면 계약과 T3/T4 저장 순서를 유지한다. 공고 변경 시 기존 자료 테이블의 새 ID는 당시 근거 보존에 필요한 보완으로 남긴다. 상세 계약·실패 저장 경계·복구는 기존 잔여 항목에서 검토한다.

- [0016 프로필 언어 집계와 Sprint 1 역할 요약 범위](../../ai/decisions/0016-profile-language-aggregation.md): 2026-09-22 사용자 결정. 완료 면접에서 사용한 저장소의 중복 제거·언어 비율 동일 비중 평균은 유지한다. 개인 역할 요약 보류·안내 표시는 후속 0019로 대체하며 기존 저장소·공개 응답과 report 후 갱신 흐름은 유지한다.

- [0019 Sprint 1 개인 역할 요약의 기존 계획 복원](../../ai/decisions/0019-sprint1-profile-role-summary-restoration.md): 2026-09-22 사용자 결정. 기존 role_summary·roleSummary·화면·job으로 LLM 역할 요약을 제공한다. 통계는 기존 방식으로 집계하며 근거 없는 기여 추정은 금지한다. 실제 생성·저장·호출은 구현 대기다.

- [0017 Sprint 1 추천 숫자 점수 보류](../../ai/decisions/0017-recommendation-score-deferral.md): 2026-09-22 사용자 결정. matchScore 필드는 null로 반환하고 기존 추천 표시·이유·상한·저장 위치를 유지한다. 선정 기준은 후속 0018을 따르며 실제 DB·응답 연결은 구현 시 검증한다.

- [0018 기존안 일괄 유지와 질문·구현·후속 검토 분리](../../ai/decisions/0018-existing-baseline-bulk-resolution.md): 기존 기술 직접 비교·후보 순서에서 run 전체 최대 5개 추천을 채택한다. 기존 계약·저장·Worker·종료 흐름을 유지하며 상세 연결·실측은 구현 인계로 구분한다. 실제 문답과 연결 자료를 후속 내부 비교에 보관·재사용하고 최종 내부 비교 검증 뒤에도 보관한다. 별도의 자동 삭제 기한은 두지 않는다.
