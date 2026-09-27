"""step 4 · task-11 분석 worker가 연결할 Wanted 공고 수집 단계.

task-09의 posting_service.get_or_fetch_posting()이 URL 검증, 7일 성공 자료 재사용,
외부 수집과 새 공고·요구사항의 원자 저장을 제공한다. 실패는 기존 수집/추출 예외로 전달된다.
원문 그룹은 job_postings.raw_payload에 저장하며 존재하지 않는 raw_text 컬럼에 쓰지 않는다.
worker의 step 상태·run FK 확정·실패 알림은 task-11에서 연결한다.
"""
