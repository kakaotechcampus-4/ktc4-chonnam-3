# 0001 포트폴리오 언급 레포의 룰 필터 우회 범위

상태: Accepted
날짜: 2026-09-28
관련 PR: #45
검토자: dreactive(결정), gdh0730(2차 리뷰)

## 맥락

`repo_select.py`의 `select_candidates()`는 전체 public repo에 `filter_reason()`(private/fork/archived/no_language/too_small)을 적용해 `eligible`/`excluded`를 가른 뒤, 포트폴리오 언급·base_rank 상위·high_contribution 세 그룹을 섞어 첫 배치 최대 10개를 만든다(그룹별 상한은 `spec/ai/decisions/0010-sprint1-interface-runtime-decisions.md`, `spec/backend/features/analysis-run.md:57`, `backend/docs/task-10-match.md:15`에 이미 3(포트폴리오)/5(base_rank)/2(high_contribution)로 확정돼 있어 이 결정의 대상이 아니다).

문제는 "포트폴리오 언급 레포가 룰 필터에 걸리면 어떻게 되는가"다.

- PR #45 최초 구현(dreactive, 커밋 `422ef33`)은 포트폴리오 언급이면 `filter_reason` 결과와 무관하게 무조건 `eligible`로 처리했다 — private까지 포함해 전부 우회했다.
- PR #45 2차 리뷰(gdh0730, 커밋 `b4efe8c`)는 포트폴리오 매칭을 `eligible_names`(이미 필터를 통과한 것)에서만 찾도록 바꿔, private/fork/archived/no_language/too_small 중 어떤 사유로든 걸리면 포트폴리오 언급이어도 첫 배치 후보에서 완전히 빠지게 됐다.

`spec/backend/features/analysis-run.md:59`("제외 repo도 `filter_status='excluded'`, `filter_reason`으로 저장한다")는 제외된 레포의 저장 방식만 규정할 뿐, 포트폴리오 언급이 필터를 우회하는지는 어떤 spec 문서에도 명시돼 있지 않았다.

## 결정

포트폴리오 언급 레포는 `is_private`일 때만 제외한다. `fork`, `archived`, `no_language`, `too_small`은 포트폴리오 언급 레포에는 적용하지 않고 무조건 `eligible`로 포함한다.

## 이유

사용자가 이력서·포트폴리오 문서에 명시적으로 언급한 레포는 "대표작"이라는 사용자 의도가 명확하다. fork·archived·오래된 레포·작은 크기·언어 미상 같은 자동 판정 사유로 이를 숨기면 사용자가 직접 고른 레포가 정작 첫 배치에서 빠지는 상황이 된다. 반면 private은 이 문제와 층위가 다르다 — Sprint 1은 GitHub 수집 자체를 public repo로 한정하고(`GithubClient.list_repositories`가 `visibility=public`만 조회), private 토큰 범위·권한 문제까지 얽혀 있어 포트폴리오 언급이라는 이유로 예외를 둘 수 없다.

## 영향

- 팀: BE
- 대상 코드: `backend/app/features/analysis/pipeline/steps/repo_select.py`의 `select_candidates()`. `filter_reason()`(base.py) 자체는 변경하지 않고, 포트폴리오 언급 레포를 배치 후보로 뽑는 조건만 별도로 분기한다.
- 계약 변경: 없음. `analysis_repo_candidates.filter_status`/`filter_reason` 필드와 값 종류는 그대로이며, 어떤 레포에 어떤 값이 채워지는지 로직만 바뀐다.
- 테스트: `filter_reason`이 private이 아닌 사유로 막힌 포트폴리오 언급 레포가 `eligible`+`portfolio_mentioned`로 배치에 포함되는 케이스, private 포트폴리오 언급 레포는 여전히 `excluded`+`private`로 남는 케이스를 추가한다.
- 3+5+2 배치 슬롯 구조 자체는 이 결정과 무관하게 기존대로 유지한다.

## 대체 관계

없음(신규).
