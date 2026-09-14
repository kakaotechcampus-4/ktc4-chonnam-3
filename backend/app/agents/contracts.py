"""인터페이스 계약 4종 — Question / DirectorDecision / AnswerAnalysis / Evidence.
★ analysis · decision 의 JSONB 키 이름을 여기서 고정한다. 2차에 answer_analyses /
director_decisions 테이블로 승격할 때 컬럼명이 그대로여야 마이그레이션이 단순하다.
Agent 는 Director 하나뿐이고, 나머지 LLM 산출물은 app/llm_tasks/ 가 만든다.

확정본 §5 / docs/layer-rules.md 1절 / task-14
"""
