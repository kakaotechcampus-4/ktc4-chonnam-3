# task-14 — Director Agent · LLM task

> 선행: task-03
> 설계 근거: [becontext.md](../../becontext.md) · [db-schema.md](db-schema.md)

## 목표

`agents/contracts.py` 계약 4종 + Director Agent + `llm_tasks/` 단발 호출.

## 확정본 반영 (becontext.md 대비 변경)

**Agent 는 Director 하나뿐이다.** 나머지는 Agent 가 아니라 단발 LLM 호출로 충분하다.

- `agents/director/{agent,tools}.py` — Evidence 는 별도 Agent 가 아니라 **Director 의 Tool** (`search_code` / `read_file` / `list_commits`). Tool 3종 모두 `ref`(커밋 SHA) 를 필수 인자로 받는다.
- `app/llm_tasks/` 신규 — `repo_shallow` / `repo_deep` / `jd_extract` / `doc_claims` / `answer_analysis` / `report` / `profile_summary` / `conflict`(2차).
- `prompt_loader` 는 `llm_tasks` 중 **유일하게 `AsyncSession` 을 받는다.** service 가 이걸로 로드해 문자열로 주입하므로 agents 는 DB 를 모른 채로 남고 Eval 에서 DB 없이 돈다.
- `analysis` · `decision` JSONB 키 이름을 `contracts.py` 에서 지금 고정한다 (2차에 테이블 승격).

## 작업

- [ ] TODO

## 완료 조건

- [ ] TODO

## 커밋 메시지

```
TODO
```
