"""step 7 · 매칭 점수 → repo_match_scores.
jd_requirements.tech_tags ↔ repo_analyses.tech_stack 대조 → matched_requirement_ids.
★ is_ai_recommended 를 5개 이하로 제한한다. is_selected 상한이 5개라, 추천을 8개 내면
  채택률이 구조적으로 62.5% 를 못 넘어 지표가 처음부터 망가진 채 쌓인다.
★ candidate_source = rule_filter / portfolio / both → M3 카드의 포트폴리오 배지.

확정본 §4 repo_match_scores / task-10
"""
