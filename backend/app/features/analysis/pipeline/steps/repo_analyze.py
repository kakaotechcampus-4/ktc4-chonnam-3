"""step 6 · L1 기본 분석 → repo_analyses(analysis_level='shallow').
★ 캐시 키는 (repository_id, analysis_level, head_sha, prompt_version) — push 가 오면
  head_sha 가 바뀌어 자동 재분석된다.
★ 일부 repo 성공·일부 실패면 run은 partial, 전체 repo 실패면 failed다.
  DB partial은 FE failed로 매핑하지만 성공 결과 조회는 허용한다. 실제 집계·저장은 구현 대기다.

확정본 §2 repo_analyses / task-10
"""
