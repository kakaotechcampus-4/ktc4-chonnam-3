"""prepareStep 4단계 — analyze_repo / build_persona / compose_question / set_criteria.
★ L2 의 notable_areas 를 evidences 로 전개한다 (tool_name=NULL — 사전 분석 부산물).
  면접 중 Tool 호출 산출물(tool_name 값 있음)과 구분되어야 'Tool 호출 0건 = 근거 없는
  꼬리질문' 지표가 성립한다.
★ git_ref 는 session_repositories.snapshot_head_sha 에서 복사한다.

확정본 §5 evidences / task-15
"""
