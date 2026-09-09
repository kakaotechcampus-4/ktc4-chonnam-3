"""Director 의 Evidence Tool 3종 — search_code / read_file / list_commits.
★ 3종 모두 ref(커밋 SHA) 를 필수 인자로 받는다. session_repositories.snapshot_head_sha 를
그대로 넘겨야 evidences.git_ref(NOT NULL) 가 채워지고 면접 중 push 에도 근거가 어긋나지 않는다.

확정본 §5 Turn 2 / task-14
"""
