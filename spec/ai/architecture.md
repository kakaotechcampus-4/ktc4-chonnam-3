# AI 기능 아키텍처 — 설계 기반

이 문서는 DEVON 서비스의 AI 기능 명세다. 코딩 AI의 작업 지침은 ai/CLAUDE.md에 둔다.

| 경로 | 책임 |
| --- | --- |
| backend/app/agents/ | 단일 면접관 구현 영역. 저장소 문서 명칭은 Director |
| backend/app/llm_tasks/ | 사전 분석·피드백 등 단발 LLM 작업 |
| backend/app/integrations/ | 외부 LLM·GitHub I/O |
| spec/ai/ | AI 기능 요구사항·설계·평가 조건 |

단일 면접관과 3개 페르소나의 동작은 features/interviewer.md에 정의한다.
Agent는 DB 세션을 받지 않으며 prompt_loader의 예외 경계는 backend 기존 상세 규칙을 따른다.
AI 코드의 별도 서비스 분리·경로 이동은 아직 결정하지 않았다. 모델·provider·RAG 저장소도 계약 이관 검수 항목이다.
