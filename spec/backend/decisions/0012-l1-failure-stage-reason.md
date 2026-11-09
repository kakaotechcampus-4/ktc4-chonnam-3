# 0012 — L1 실패 행에 AI 실패 단계·사유 보존

- 상태: Proposed
- 날짜: 2026-11-02
- 관련 PR: [#166](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/166)
- 검토자: PR 리뷰에서 확인 예정

## 맥락

AI L1은 실패를 호출 전체(`CallFailure`) 또는 저장소별(`RepoItemFailure`)로 반환하며
`stage`와 `reason_summary`로 중복·누락 ID, 항목 오류, provider 오류 등을 구분한다.
BE `to_repo_analysis_rows`는 이를 공개 `error_code`(`llm_parse_failed`, `llm_failed` 등)로만
바꾸고 실패 행 `result`를 `null`로 저장해 이 구분이 사라졌다. 공개 `error_code`를 늘리면
OpenAPI, FE 문구 표, `REPO_ANALYSIS_ERROR_CODES`를 함께 바꿔야 한다.

## 결정

- L1 실패 행(`analysis_level='l1'`, `status='failed'`)의 `result`에 BE 저장 전용 키
  `_failure: {stage, reason_summary}`를 둔다. 값은 AI가 반환한 실패를 그대로 옮긴다.
  공개 `error_code`는 바꾸지 않는다.
- 저장소별 실패는 그 저장소의 첫 실패를 남긴다. 재요청 응답의 실패가 앞선 사유를 덮지 않는다.
  호출 전체 실패는 입력 저장소의 모든 행에 같은 호출 실패를 남긴다.
- AI가 실패 원인을 주지 않았거나, BE가 저장할 수 없는 문자를 감지해 실패로 바꾼 행은
  `result`를 `null`로 둔다. `_failure` 값에 저장할 수 없는 문자가 있어도 같은 검사로 `null`이 된다.
- 요청하지 않은 ID나 ID가 없는 실패 항목은 대응할 행이 없어 `raw_output`에만 남는다.
- succeeded·partial 행과 L2 실패 행에는 이 키를 두지 않는다.

## 읽는 쪽 규칙

- L1 실패 행의 `result`는 `null` 또는 `{"_failure": {...}}`다. `null`이라고 가정하지 않는다.
- `_failure`는 진단용 BE 내부 값이다. 공개 API 응답, FE, AI 모델 입력에 노출하지 않으며
  성공 판정·추천·면접 근거에 사용하지 않는다.
- 결정 시점에 실패 행 `result`를 해석하는 곳은 없다. `resolve_bound_analysis`(면접 준비 포함)는
  succeeded만, `partial_cache`는 오류 없는 L1 partial만 읽는다.
  `agent_context._analysis_limitations`는 상태와 무관하게 같은 저장소·SHA 행의 `result`를 읽지만
  `limitations`·`analysis` 키만 사용하므로 `_failure`는 무시된다.

## 이유

AI가 이미 구분한 실패 단계를 공개 계약 변경 없이 보존해 운영 진단과 재현에 쓴다.
기존 JSONB에 BE 전용 키를 두는 방식은 [0007](0007-task10-collection-retry-and-partial-cache.md)의
`_truncation_cache` 선례를 따른다. 실패 행에는 분석 결과가 없으므로 키가 충돌하지 않는다.

- 새 `error_code`: 공개 계약 세 곳과 FE 노출 문구를 함께 결정해야 해 이번 범위를 넘는다.
- 별도 컬럼: migration이 필요하지만 사용처가 진단뿐이다.
- `raw_output`만 사용: 원문을 다시 해석해야 하고, 호출 전체 실패에는 원문이 없을 수 있다.

## 영향과 검증

BE 저장 데이터만 바뀐다. L1 실패 행 `result`가 `null`에서 `{"_failure": ...}`가 될 수 있다.
공개 API, `error_code`, AI 출력 계약, DB 컬럼, migration은 바꾸지 않는다. 키 기록을 제거하면
이전처럼 `null`로 저장하며, 이미 저장된 키는 해석하는 곳이 없어 남아도 동작에 영향이 없다.
`to_repo_analysis_rows` 단위 테스트와 PostgreSQL 저장·조회로 확인한다. 실행 결과는 PR에 남긴다.

## 대체 관계

[0007](0007-task10-collection-retry-and-partial-cache.md)의 BE 전용 `result` 키 방식을
L1 실패 행에 확장한다. 0007과 공개 계약은 대체하지 않는다.
