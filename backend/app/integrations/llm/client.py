"""OpenAI 호출·재시도·사용량 기록을 연결할 예정인 골격. 실제 호출은 미구현이다.

Sprint 1 모델은 ADR 0011의 gpt-5.6-luna를 BE 설정·seed에서 주입한다.
모델 ID를 코드 상수로 두지 않으며 SDK/client 연결·계정 접근은 구현·검증해야 한다.

docs/layer-rules.md 2절 · .env.example / task-14
"""
