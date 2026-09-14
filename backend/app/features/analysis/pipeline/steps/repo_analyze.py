"""step 6 · L1 기본 분석 → repo_analyses(analysis_level='shallow').
★ 캐시 키는 (repository_id, analysis_level, head_sha, prompt_version) — push 가 오면
  head_sha 가 바뀌어 자동 재분석된다.
★ 일부 레포 실패는 job 실패가 아니다. job='succeeded', 개별 row 만 'failed'.

확정본 §2 repo_analyses / task-10
"""
