"""/ws/interviews/{sessionId} — 핸드셰이크, 단일 접속 락, 하트비트.
★ 스프린트1 은 양방향 텍스트다. 오디오 프레임 · transcript · stt_failed · tts_failed 는
  스프린트2 에서 붙인다 (answer_mode CHECK = 'text').
★ 답변 초안 저장 없음 — 제출 1회로 answer_text UPDATE.
★ 연결 끊김은 명시적 이탈이 아니며 재연결 시 저장된 준비 상태·현재 턴을 복구한다.
  사용자가 중단한 면접을 수동 재개하는 기능은 없다 (status에 paused 없음).
★ 준비 재시도는 REST /interviews/{id}/prepare/retry, 질문 완료는 question 이벤트다.
  Sprint 1 WS prepareRetry·questionEnd는 사용하지 않는다. 실제 WS 연결은 구현 대기다.

확정본 §5 interview_sessions / task-15
"""
