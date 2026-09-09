"""step 2 · 레포 선별. 룰 필터 + 포폴 합집합.
룰 필터: is_fork=false AND is_archived=false AND size_kb>50 AND primary_language IS NOT NULL
        ORDER BY repo_pushed_at DESC LIMIT 10
★ 포폴 언급 레포는 룰 필터를 무조건 우회한다 (사용자가 대표작이라 명시한 것).
  후보 = 룰 필터 10개 ∪ 포폴 언급 레포
★ full_name 매칭 실패(남의 레포·private·삭제·오타)는 정상 상황이다 — 실패 처리하지 않고
  '포폴에 언급된 3개 중 2개를 찾았습니다' 로 알린다.

확정본 §2 룰 필터 / task-08
"""
