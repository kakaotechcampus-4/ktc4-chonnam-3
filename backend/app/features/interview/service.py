"""세션 생성 / 동시 면접 제한 / sessionId 발급.
★ job_posting_id 가 NOT NULL 이다 (공고 필수).
★ status = preparing / in_progress / completed / abandoned. paused 없음.
★ answer_mode = 'text' 고정 (CHECK). 2차에 voice 완화.
★ 이탈은 status='abandoned' + abandoned_at_turn. 미답변 턴은 'asked' 로 남는다
  (1차에 timeout 판정 배치를 만들지 않는다).

확정본 §5 interview_sessions / task-13
"""
