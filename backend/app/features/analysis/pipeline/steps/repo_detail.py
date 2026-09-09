"""step 3 · L0-b 추가 매핑. 후보 레포만 fetch_level='detail' 로 승격.
레포당 4회 — languages / readme / commits?per_page=1 / commits?per_page=1&author={login}
★ head_sha 와 commit_count 를 따로 부르지 않는다: commits?per_page=1 의 body[0].sha 가
  head_sha, Link 헤더 rel='last' 의 page=N 이 commit_count.

확정본 §2 M2 비용 최적화 / task-08
"""
