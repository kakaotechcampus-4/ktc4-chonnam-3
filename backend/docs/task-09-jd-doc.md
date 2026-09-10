# task-09 — Wanted 공고 · 문서 Preview

> 선행: task-05
> 근거: `spec/backend/features/documents.md`, `spec/backend/features/analysis-run.md`

## 목표

Wanted 공고 수집과 `POST /documents/preview`를 구현한다.

## 작업

- Sprint 1은 Wanted URL만 지원한다.
- Wanted normalized URL 기준으로 `job_postings`를 재사용한다.
- `fetched_at` 24시간 이내 성공본은 재사용한다.
- Wanted 구조화 필드에서 required/preferred/unknown과 `skill_tags`를 추출한다.
- unsupported site는 공고 없이 진행으로 유도하지 않고 차단한다.
- `POST /documents/preview`는 PDF/DOCX/TXT/MD만 지원한다.
- 파일 크기 상한은 10MB.
- 파일 바이너리는 저장하지 않는다.
- extracted_text, extracted_github_urls, extract_status, truncation 여부를 저장한다.
- claim 추출은 하지 않는다.
- GitHub URL은 root repo로 정규화한다.

## 완료 조건

- Wanted 성공/unsupported/fetch 실패/extract 실패 테스트가 있다.
- 문서 preview 성공/partial/failed, 미지원 형식, 크기 초과 테스트가 있다.
