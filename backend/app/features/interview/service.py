"""세션 생성 / 동시 면접 제한 / sessionId 발급.
★ job_posting_id 가 NOT NULL 이다 (공고 필수).
★ status = preparing / preparing_failed / in_progress / completed / abandoned. paused 없음.
★ answer_mode = 'text' 고정 (CHECK). 2차에 voice 완화.
★ 명시적 이탈·레포 재선택만 status='abandoned' + abandoned_at_turn으로 처리한다.
  WS 끊김은 재연결 대상이며 미답변 턴은 asked로 남는다. 자동 timeout 이탈 판정은 없다.
  실제 상태 저장·연결은 구현 대기다.

확정본 §5 interview_sessions / task-13
"""
