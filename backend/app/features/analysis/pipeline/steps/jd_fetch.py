"""step 4 · 공고 페이지 수집. resolver 로 어댑터 선택 → raw_text / source_image_urls /
content_form 저장.
★ 재사용 규칙: fetched_at 7일 이내 AND parse_status='success' 면 행을 재사용하고 LLM 0회.
  그 외에는 재fetch 후 jd_requirements DELETE → 재INSERT.

확정본 §3 job_postings / task-09
"""
