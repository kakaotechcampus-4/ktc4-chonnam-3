# task-08 — GitHub 수집

> 선행: task-06
> 근거: `spec/backend/features/analysis-run.md`

## 목표

public repo L0-a/L0-b 수집과 GitHub rate limit 처리를 구현한다.

현재 수집 pipeline·worker는 골격이다. task-06에서 제공하는 `app.state.github.get(user_id, path)`와 요청 시 token 갱신은 후속 수집 API의 기반이며, 저장소 수집 완료를 뜻하지 않는다.

## 작업

- `initial_sync`에서 전체 public repo L0-a metadata를 저장한다.
- `initial_sync` 시작 시점은 후속 계약이다. 현재 OAuth callback에서는 enqueue하지 않는다.
- 인증이 필요한 GitHub GET은 `app.state.github.get(user_id, path)`를 사용한다. 서비스가 access 만료 60초 전부터 refresh하고 token pair를 서버에만 암호화 저장하므로 수집 코드가 token이나 별도 갱신 cron을 관리하지 않는다.
- `token_invalid`는 GitHub 재로그인이 필요한 연결 상태다. 네트워크·429·5xx·잘못된 응답의 `provider_unavailable`과 구분한다. GitHub 연결 실패가 DEVON JWT session을 폐기하지는 않는다.
- private repo는 지원하지 않는다. `is_private` 필드는 저장하되 분석/선택 대상에서 제외한다.
- 기본 필터: public, non-fork, non-archived, primary language 있음.
- `size_kb` threshold는 기본값을 두되 설정 가능하게 한다.
- L0-b 필수 수집: languages, README, head_sha, commit_count, user_commit_count.
- README는 DB에 저장하되 길이 제한을 둔다. 큰 README는 중요한 섹션 중심으로 축약하고 `partial` 처리한다.
- rate limit 발생 시 가능한 결과는 저장하고 실패 repo는 `rate_limited`로 기록한다.

## 완료 조건

- public/private/fork/archived/no_language/too_small/inaccessible 케이스가 분리된다.
- rate limit 일부 실패는 run partial 정책으로 이어진다.
- GitHub API 서비스의 token 갱신·오류 계약을 유지하고, task-06 검증만으로 수집 pipeline 완료를 주장하지 않는다.
