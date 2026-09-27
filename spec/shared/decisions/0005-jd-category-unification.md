# 0005 JD 분류 category 통일 — ai 패키지·공통 계약 반영

- 상태: Proposed
- 날짜: 2026-09-27
- 작성: 송유석(이슈 #63 코멘트) / 반영: 박현솔
- 검토자: 구동한 (검토 대기)
- 관련 PR: [#41](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/41) (DB 모델·원 결정, 2026-09-21 코멘트, merged), [#67](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/67) (BE jd_extract·AI 계약 반영)
- 관련 이슈: [#63](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/63)

## 맥락

PR #41에서 DB `jd_requirements.category`를 `required`/`preferred`/`responsibility`로 확정했고, PR #67에서 BE `jd_extract`와 BE 문서를 이 값에 맞췄다. 그런데 AI 계약(`ai/src/devon_ai/contracts.py`의 `JDRequirement`)과 `spec/ai/`, 공통 계약 이관 기록(`spec/shared/contracts/migration.md` "PR #15 JD 분류 정합화")에는 옛 설계(`requirement_type` + `unknown`, API·DB 분리 변환)가 남아 있었다. `migration.md`는 공통 계약 원본이므로 BE 단독이 아니라 AI 쪽 합의를 거쳐 갱신한다.

## 결정

- AI 쪽도 BE와 동일하게 `category` 단일 개념으로 통일한다.
- `requirement_type` 필드명과 `unknown` 값을 폐기한다.
- AI 계약의 `JDRequirement`는 `category: Literal["required", "preferred", "responsibility"]`를 사용한다.
- API 표시용 값과 DB/AI 저장값을 구분하는 변환 레이어는 두지 않는다.

## 이유

- DB 스키마는 PR #41로 `category`가 확정·merge되었고 BE 소비 코드(PR #67)도 통일했다. AI만 옛 개념을 유지하면 BE가 넘기는 `jd_requirements`와 AI 계약의 필드명·값 집합이 달라 Context 구성 시 스키마 검증 실패가 나거나 존재하지 않는 필드를 참조하게 된다.
- 두 팀이 같은 개념에 다른 이름·값을 쓸 이유가 없고, 변환 레이어는 양쪽 enum 동기화 부담만 늘린다.

## 영향

| 파일 | 변경 |
| --- | --- |
| `ai/src/devon_ai/contracts.py` `JDRequirement` | `requirement_type: Literal["required", "preferred", "unknown"]` → `category: Literal["required", "preferred", "responsibility"]` |
| `spec/ai/contracts.md` Context 입력 표·`jd_extract_v1` 행 | `requirement_type` → `category`, `required/preferred/unknown` → `required/preferred/responsibility` |
| `spec/ai/features/repository-analysis.md` "Wanted 요구사항" | 주요 업무(`main_tasks`)는 `category=responsibility`로 저장하고 `source_field`로 출처를 구분 |
| `spec/shared/contracts/migration.md` "PR #15 JD 분류 정합화" | API `JdCategory`와 DB·AI `category`는 같은 값, 변환 레이어 없음 |

- 영향 팀: AI(계약·구현), BE(소비 없음, 검증만).
- 계약 변경 범위: AI 내부 계약(`ai/src/devon_ai/contracts.py`, `spec/ai/`)과 공통 계약 이관 기록(`migration.md`)만. 공개 REST API(`openapi.yaml`)와 DB 스키마는 PR #41로 확정된 값 그대로다.
- 검증: `ai` ruff·mypy·pytest, `backend/tests/agents/test_ai_package_imports.py`, `python3 .claude/scripts/check_contracts.py`.

## 대체 관계

`spec/shared/contracts/migration.md` "PR #15 JD 분류 정합화"의 기존 결정("API `JdCategory`와 DB·AI `requirement_type`은 서로 다른 의미이므로 각각 유지")과 `spec/ai/features/repository-analysis.md`의 "`responsibility`를 새 enum 값으로 만들지 않는다"를 대체한다.

[AI 0006](../../ai/decisions/0006-task-llm-usage-policy.md#wanted-분류)의 Wanted 분류 중 `required/preferred/unknown` enum만 `required/preferred/responsibility`로 대체한다. 구조화 필드의 규칙 변환과 LLM 비호출, `skill_tags` 기반 `tech_tags`, 원문에 없는 요구사항·기술 태그와 수집·입력 실패를 LLM 추측으로 보충하지 않는 원칙은 유지한다.
