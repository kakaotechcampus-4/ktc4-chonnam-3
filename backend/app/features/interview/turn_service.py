"""한 턴의 DB 쓰기 — T1 질문 / T2 답변 / T3 분석 / T4 판단.
T1: evidences INSERT → interview_turns INSERT(status='asked', depth, parent_turn_no,
    jd_requirement_ids, claim_ids) → turn_evidences INSERT(usage='question_basis')
T2: answer_text UPDATE, status='answered' (제출 1회)
T3: analysis UPDATE
T4: decision UPDATE + interview_sessions.context_state / turn_count / elapsed_sec 갱신
★ depth 1=주제 시작, 2+=꼬리질문. 새 주제로 넘어가면 1로 리셋.
★ turn_evidences 필수 여부는 페르소나별로 다르다 — tech_lead 는 필수,
  domain_lead 는 jd_requirement_ids, hr_manager 는 claim_ids 로 갈음된다.

확정본 §5 / task-15
"""
