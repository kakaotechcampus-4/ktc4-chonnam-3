"""step 5 · 공고 분석 → jd_requirements.
error_code 를 단계별로 나눈다 — unsupported_site / url_unreachable / content_empty 는
우리 코드 실패(재시도 무의미), not_a_job_posting / extraction_failed / llm_timeout 은 LLM 실패.

확정본 §3 parse_error_code / task-09
"""
