"""step 4 · 공고 페이지 수집. resolver 로 어댑터 선택 → raw_text / source_image_urls /
content_form 저장.
★ 재사용 규칙: fetched_at 7일 이내 AND parse_status='success' 면 행을 재사용하고 LLM 0회.
  재조회 내용이 같으면 기존 ID를 재사용하고 바뀌면 새 공고·요구사항 ID로 저장한다.
  이전 요구사항과 run·면접 참조를 삭제하지 않는다. 재사용·저장 연결은 구현 대기다.

확정본 §3 job_postings / task-09
"""
