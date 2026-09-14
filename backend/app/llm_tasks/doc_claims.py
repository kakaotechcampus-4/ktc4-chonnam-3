"""자소서 → document_claims 추출.
★ kind='cover_letter' 만 대상. portfolio 는 claim 을 만들지 않는다 (URL 파싱만).
★ 1차 추출 타입은 tech_decision / contribution 2종. achievement · motivation 은
CHECK 에만 남기고 추출하지 않는다 — 커버리지 지표가 희석된다. 상한 10개.

확정본 §3 document_claims / task-09
"""
