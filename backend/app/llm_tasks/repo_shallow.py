"""L1 기본 분석 (M2). 후보 레포를 한 프롬프트에 배치로 넣어 project_types / tech_stack /
role_summary 생성.
★ 응답을 레포 단위로 부분 파싱한다 — 1건이 깨져도 나머지를 살리고 깨진 것만 status='failed'.
★ raw_output 에 배치 원문을 보존한다 (LLM 재호출 없이 파싱 로직만 고쳐 복구).

확정본 §2 repo_analyses / task-08
"""
