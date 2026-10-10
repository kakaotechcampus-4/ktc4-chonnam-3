"""step 5 · task-11 분석 worker가 연결할 Wanted 요구사항 단계.

llm_tasks.jd_extract.build_requirement_drafts()는 LLM 없이 구조화 필드를 변환한다.
posting_service는 공고와 요구사항을 함께 확정한다. 저장된 요구사항은
posting_queries.get_posting_requirements()로 display_order 순서대로 조회한다.
수집 실패는 jd_fetch_failed, 유효한 요구사항 부재는 jd_extraction_failed로 구분한다.
7개 분석 단계의 실행·상태 보고는 task-11의 책임이다.
"""
