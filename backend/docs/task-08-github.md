# task-08 — GitHub 수집

> 선행: task-06
> 근거: `spec/backend/features/analysis-run.md`

## 목표

public repo L0-a/L0-b 수집과 GitHub rate limit 처리를 구현한다.

## 작업

- `initial_sync`에서 전체 public repo L0-a metadata를 저장한다.
- private repo는 지원하지 않는다. `is_private` 필드는 저장하되 분석/선택 대상에서 제외한다.
- 기본 필터: public, non-fork, non-archived, primary language 있음.
- `size_kb` threshold는 기본값을 두되 설정 가능하게 한다.
- L0-b 필수 수집: languages, README, head_sha, commit_count, user_commit_count.
- README는 DB에 저장하되 길이 제한을 둔다. 큰 README는 중요한 섹션 중심으로 축약하고 `partial` 처리한다.
- rate limit 발생 시 가능한 결과는 저장하고 실패 repo는 `rate_limited`로 기록한다.

## 완료 조건

- public/private/fork/archived/no_language/too_small/inaccessible 케이스가 분리된다.
- rate limit 일부 실패는 run partial 정책으로 이어진다.
