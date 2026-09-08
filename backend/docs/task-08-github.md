# task-08 — GitHub 수집 — L0-a · L0-b · 룰 필터

> 선행: task-06
> 설계 근거: [becontext.md](../../becontext.md) · [db-schema.md](db-schema.md)

## 목표

M1 `initial_sync`(L0-a 전체 레포) + M2 의 `repo_select` · `repo_detail` step + L1 배치 분석.

## 확정본 반영 (becontext.md 대비 변경)

becontext 의 "`fetch_repos` step" 하나가 **3개로 쪼개졌다.**

- **L0-a (M1)** — 연동 직후 백그라운드. 목록 API 응답에 이미 있는 필드만, `fetch_level=list`.
- **룰 필터 (M2 `repo_select`)** — `is_fork=false AND is_archived=false AND size_kb>50 AND primary_language IS NOT NULL ORDER BY repo_pushed_at DESC LIMIT 10`. 포폴 언급 레포는 이 필터를 **무조건 우회**한다.
- **L0-b (M2 `repo_detail`)** — 후보만 `detail` 승격. 레포당 4회.
  `head_sha` 와 `commit_count` 를 따로 부르지 않는다 — `commits?per_page=1` 의 `body[0].sha` 가 `head_sha`, Link 헤더 `rel="last"` 의 `page=N` 이 `commit_count` (`integrations/github/pagination.py`).
- **L1 (`llm_tasks/repo_shallow.py`)** — 배치 1프롬프트. 응답을 레포 단위로 **부분 파싱**해 깨진 것만 `failed` 로 남기고, `raw_output` 에 원문을 보존해 LLM 재호출 없이 복구한다.

## 작업

- [ ] TODO

## 완료 조건

- [ ] TODO

## 커밋 메시지

```
TODO
```
