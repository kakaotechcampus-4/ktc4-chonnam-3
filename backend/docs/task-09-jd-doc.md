# task-09 — 공고 어댑터 · 문서 추출 · claim

> 선행: task-05
> 설계 근거: [becontext.md](../../becontext.md) · [db-schema.md](db-schema.md)

## 목표

원티드 어댑터 + 문서 텍스트 추출 + `jd_extract` · `doc_extract` step.

## 확정본 반영 (becontext.md 대비 변경)

- `integrations/jd/fetcher.py` 단일 파일이 **어댑터 구조**로 바뀌었다 (`base` / `resolver` / `wanted` / `generic`). `site_adapter` 컬럼이 어댑터별 성공률 비교 축이다.
- **원티드 1종만 1차.** `/wd/{id}` → `/api/chaos/jobs/v1/{id}/details` 공개 JSON 이 항목별로 이미 나뉘어 오고 `skill_tags` 가 `tech_tags` 원천이라 LLM 추측이 불필요하다. 사람인(본문이 이미지 PNG)·잡코리아는 2차.
- 공고 **재사용 TTL 7일** — `fetched_at` 이 이내 + `parse_status=success` 면 LLM 0회.
- **claim 추출은 자소서만.** 포폴은 `mentioned_repo_urls`(GitHub URL 파싱)만 하고 claim 을 만들지 않는다. `source_type=link` 포폴의 `extract_status=unsupported` 는 정상이다.
- claim 타입은 `tech_decision` / `contribution` 2종만 (상한 10). `achievement` · `motivation` 은 CHECK 에만 남긴다.

## 작업

- [ ] TODO

## 완료 조건

- [ ] TODO

## 커밋 메시지

```
TODO
```
