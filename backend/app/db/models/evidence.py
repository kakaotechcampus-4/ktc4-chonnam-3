"""evidences, turn_evidences, evidence_conflicts.
★ evidences.git_ref 는 NOT NULL — 없으면 재조회가 불가능하다.
★ evidences.tool_name NULL = L2 사전분석 부산물, 값 있음 = 면접 중 Tool 호출.
★ evidence_conflicts 는 1차에 테이블만 만들고 행을 만들지 않는다. 미리 만드는 이유는
  FK 가 document_claims · evidences 양쪽을 참조해서, 나중에 추가하면 그 시점의
  정합성을 다시 봐야 하기 때문이다.

확정본 §3 §5 / task-02
"""
