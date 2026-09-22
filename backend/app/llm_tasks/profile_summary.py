"""Sprint 1 프로필 집계·개인 역할 요약의 BE 경계. 실제 집계·생성·저장은 미구현이다.

완료 면접에 사용된 저장소를 중복 제거하고 저장소별 언어 비율을 같은 비중으로 평균낸다.
언어·프로젝트 유형 집계에는 LLM을 사용하지 않으며 개인 역할 요약만 LLM으로 생성한다.
기존 role_summary 저장 필드·roleSummary 응답과 report 성공 후 갱신·실패 분리를 유지한다.
기존 근거가 뒷받침하지 않는 개인 기여를 만들어내거나 프로젝트 설명을 개인 역할로 단정하지 않는다.

spec/ai/decisions/0016-profile-language-aggregation.md
spec/ai/decisions/0019-sprint1-profile-role-summary-restoration.md · docs/task-16-report.md
"""
