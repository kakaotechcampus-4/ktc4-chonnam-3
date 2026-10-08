# 0007 — Task 10 재수집 실패 보존과 README 축약 캐시

- 상태: Proposed — 구현 반영, 팀 리뷰 대기
- 날짜: 2026-10-08
- 관련 PR: [#80](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/80)
- 검토자: PR 리뷰에서 확인 예정

## 맥락

GitHub 재수집이 중단되면 DTO의 기본 빈 값이 이전 자료를 덮었다. SHA를 확인하지 못한
실패가 같은 run의 성공 L1 참조와 추천도 무효화했다. README 축약은 기존 정책대로
partial이지만, 같은 입력을 재시도할 때마다 LLM을 다시 호출했다.

## 결정

- `RepoDetail.collected_fields`로 이번에 실제 확인한 필드를 구분한다. 정상 빈 값과
  README 404는 반영하고 실패·미호출·저장 불가 값은 기존 자료를 지우지 않는다.
- Repository 행을 잠근 뒤 SHA와 커밋 수를 함께 갱신한다. 새 SHA에서 미확인 커밋 수는
  비우고, SHA 자체가 미확인이면 이번 커밋 수를 이전 SHA와 섞지 않는다.
- SHA·프롬프트·분석 ID가 없는 수집 실패는 같은 run에 이미 연결된 성공만 보존한다.
  다른 run의 성공 캐시를 가져오지 않는다. 실제 접근 불가, 확인된 새 SHA의 분석 실패,
  토큰 폐기와 rate limit 기록은 기존 처리를 유지한다.
- README 축약의 partial 상태와 추천·면접 선택 제외 정책은 유지한다. 다른 수집 오류가
  없고 LLM 결과가 검증된 경우에만, 분석 당시 입력 전체의 SHA256을
  `RepoAnalysis.result._truncation_cache.input_sha256`에 저장한다.
- 저장소·SHA·프롬프트와 입력 전체가 같은 축약 partial만 재사용한다. 근거가 없는 과거
  partial, 달라진 입력, 수집 오류, 완전한 README를 다시 확보한 경우에는 재분석한다.

## 이유

값의 유무만으로 수집 성공을 판단하면 정상 `{}`·`""`·`0`과 실패를 구별할 수 없다.
또한 최신 Repository 값은 분석 당시 입력의 증거가 아니므로 캐시 근거로 사용하지 않는다.
원문을 중복 저장하거나 모든 partial을 성공으로 바꾸지 않고 필요한 호출만 줄인다.

## 영향과 검증

BE 내부 DTO와 저장 JSON의 보조 정보만 추가한다. 공개 API·AI 출력 계약·DB 컬럼·migration은
변경하지 않는다. 캐시 보조 키를 제거하면 재사용 없이 다시 분석하므로 되돌릴 수 있다.
PostgreSQL과 HTTP mock으로 성공 후 재수집 실패, 빈 값·404, SHA/커밋 수 조합, 축약 반복
호출 수와 추천 제외를 검증한다. 실제 외부 서비스 품질 검증과 Task 11의 실행 상태 집계는
별도 통합 범위다. 구체적인 실행 결과는 [Task 10 구현 기록](../implementation-task-10.md)에 남긴다.

## 대체 관계

[0003](0003-task10-ranking-and-analysis-reference.md)의 run별 L1 참조와 추천 저장 경계를
보완한다. 기존 README partial 정책과 공개 계약은 대체하지 않는다.
