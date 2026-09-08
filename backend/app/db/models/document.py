"""user_documents, document_claims.
★ document_claims 는 1차 포함이다 (becontext.md §9.1 의 '1단계 제외' 는 폐기).
  이미 끝난 면접의 '어느 주장이 다뤄졌나' 는 소급 복원이 불가능하다.
  1차 컬럼: claim_text / claim_type / tech_tags / paragraph_no / confidence
  2차 컬럼: topic_code(FK) / repository_hint(FK repositories) ← 대조의 열쇠

확정본 §3 / task-02
"""
