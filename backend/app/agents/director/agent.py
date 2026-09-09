"""유일한 Agent. context_state 를 읽어 Question / DirectorDecision 생성 + Tool 호출 루프.
프롬프트는 service 가 로드해 문자열로 주입한다 (AsyncSession 을 받지 않는다).

docs/layer-rules.md 1절 / 확정본 §5 / task-14
"""
