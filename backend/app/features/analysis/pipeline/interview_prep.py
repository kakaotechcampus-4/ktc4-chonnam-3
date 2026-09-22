"""옛 M2 경로의 골격. 현행 M2 작업명은 analysis_run이며 연결은 구현 대기다.
분석 steps 7개 —
doc_extract → repo_select → repo_detail → jd_fetch → jd_extract → repo_analyze → match_score.
문서 입력이 없으면 doc_extract는 skipped로 기록한다.
현행 interview_prep은 면접 생성 뒤 M4-a 준비 작업이다.

확정본 §2 M2 / task-11
"""
