# BE 아키텍처 — 현재 설계 기반

기준: 2026-09-09 develop의 README·디렉터리. main.py는 스켈레톤이며 아래는 설계 책임이다.

| 경로 | 책임 |
| --- | --- |
| backend/app/features/ | router/service/queries |
| backend/app/core, db, shared | 설정·DB·공통 모델 |
| backend/app/agents, llm_tasks | 면접관 Agent·단발 LLM 작업 |
| backend/app/integrations, realtime, workers | 외부 I/O·실시간·작업 큐 |

호출 방향은 router → service → queries/agents/llm_tasks/integrations/realtime.
트랜잭션 commit은 service 책임. 쿼리 모듈은 GitHub repository 개념과 구분하여 queries.py로 명명한다.
상세 규칙의 현 원본: backend/docs/layer-rules.md. 이관 전에는 본 문서의 요약과 충돌할 때 원본·실제 코드를 대조한다.
