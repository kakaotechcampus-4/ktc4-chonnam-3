"""interview_sessions, session_repositories, interview_turns.
★ interview_turns.topic_code 는 1차에 FK 를 걸지 않는다 (topic_taxonomy 확정 후 2차).
★ persona CHECK = tech_lead / hr_manager / domain_lead.
★ turn_evidences PK = (turn_id, evidence_id, usage) — 같은 evidence 가 질문 근거이면서
  채점 근거일 수 있다.

확정본 §5 / task-02
"""
