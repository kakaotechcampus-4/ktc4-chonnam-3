"""step 7 · 추천 근거를 repo_match_scores에 연결하는 구현 예정 경계.
AI 0017~0018에 따라 숫자 점수는 계산하지 않고 필수 matchScore는 null로 유지한다.
공고 기술 태그와 유효한 L1 기술 목록을 직접 비교하며, 일치한 선택 가능 후보를
기존 run 순서에서 전체 최대 5개까지 추천한다. 추가 LLM 호출은 하지 않는다.
★ 개별 요구사항 문장에도 기술이 명시된 경우에만 matched_requirement_ids를 연결한다.
  태그 겹침만으로 모든 요구사항을 연결하거나 기술 일치를 경력·자격 충족으로 해석하지 않는다.
★ candidate_source = rule_filter / portfolio / both → M3 카드의 포트폴리오 배지.

확정본 §4 repo_match_scores / task-10
"""
