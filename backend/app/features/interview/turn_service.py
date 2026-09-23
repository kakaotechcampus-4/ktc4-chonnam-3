"""한 턴의 DB 쓰기 — T1 질문 / T2 답변 / T3 분석 / T4 판단.
T1: evidences INSERT → interview_turns INSERT(status='asked', depth, parent_turn_no,
    jd_requirement_ids, claim_ids) → turn_evidences INSERT(usage='question_basis')
T2: answer_text UPDATE, status='answered' (제출 1회)
T3: analysis UPDATE
T4: decision UPDATE + interview_sessions.context_state / turn_count / elapsed_sec 갱신
★ depth 1=주제 시작, 2+=꼬리질문. 새 주제로 넘어가면 1로 리셋.
★ 실제 질문 근거가 있으면 질문과 함께 question_basis를 저장한다.
  tech_lead는 가능한 한 근거를 연결하고 domain_lead·hr_manager는 근거 없이도 허용한다.
  첫 HR 질문은 evidence가 없어도 되며 Sprint 1 문서 Claim 생성·연결은 요구하지 않는다.
  답변에서 검증 가능한 주장이 나오면 후속 근거를 evaluation_basis로 연결한다.
  위 저장·전송 경계는 구현·검증 대기다.

확정본 §5 / task-15
"""
