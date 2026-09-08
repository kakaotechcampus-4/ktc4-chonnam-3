"""prompt_versions 테이블에서 프롬프트 로드. 하드코딩 금지.
★ llm_tasks 중 유일하게 AsyncSession 을 받는다 — service 가 이걸로 로드한 뒤
agents/ 와 나머지 task 에 문자열로 주입한다. 그래야 Eval 에서 DB 없이 돌 수 있다.

docs/layer-rules.md 1·2절 / task-03 task-14
"""
