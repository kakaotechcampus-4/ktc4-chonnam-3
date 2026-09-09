# DEVON 용어 원본 — 검수 초안

| 용어 | 의미 | 경계 |
| --- | --- | --- |
| Repository | 분석 대상 GitHub 저장소 | 코드의 queries 모듈과 혼동하지 않음 |
| JobPosting | 지원 공고와 요구사항 | 공고 URL 자체와 분석 결과를 구분 |
| AnalysisRun | 사전 분석 실행 단위 | 사용자 조회 상태와 내부 job 상태는 별도 |
| Interview | 질문·답변·평가가 연결된 면접 기록 | interviewId와 sessionId를 혼용하지 않음 |
| Session | 면접 진행 연결·실행 단위 | 수명·재연결·만료 정책은 계약에서 확정 |
| Persona | 단일 면접관 Agent가 취하는 질문 관점 | 각 관점이 독립 Agent라는 뜻은 아님 |
| Evidence | 코드·문서에서 확인한 질문·평가 근거 | 출처와 추론을 구분 |

사용자 설계: 면접관 Agent 하나에 3개 페르소나, 사전 분석·피드백은 단발 LLM 호출.
저장소의 Director 명칭과 사용자 설명의 Interviewer가 같은 역할인지 AI 팀 검수 필요.
페르소나 enum 값은 spec/shared/contracts/migration.md에서 조정한다.
변경 시 관련 타입·문서의 영향 확인 후 공통 결정에 기록한다.
