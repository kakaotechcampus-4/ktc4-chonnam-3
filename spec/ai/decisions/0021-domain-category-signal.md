# 0021 공고 도메인 category 판정 방식

- 상태: Accepted
- 날짜: 2026-09-27
- 결정자: 박현솔 (AI C 역할 — JD·문서·Domain Context Builder 담당)
- 관련 PR: 없음 (이 결정과 함께 올림)
- 검토자: 별도 팀 검토자 지정 없음 — 다른 파트와 닿지 않는 담당 파트 내부 결정
- 연결 항목: [0005](0005-domain-question-policy.md)의 "승인하지 않은 범위" 중 category 신뢰 판단 방식

## 맥락

category 7종(`finance`·`game`·`travel`·`shopping`·`medical`·`mobility`·`etc`)과 "없거나 신뢰하기 어려우면 `etc`" 원칙은 [0005](0005-domain-question-policy.md)와 [도메인 질문 프레임](../features/domain-frames.md)에 정해져 있다. 그러나 공고에서 category를 어떤 근거로 판정할지는 0005에서 승인하지 않은 범위로 남아 있었다. W5 완료 기준은 "회사명만으로 도메인을 강제 분류하지 않기"다.

## 결정

1. **규칙 기반 판정**: LLM을 호출하지 않는다. 공고의 `position`·`main_tasks`·`requirements`·`preferred_points` 원문에서 category 키워드를 찾는다. 결제·예약·재고·물류·운송처럼 여러 도메인에 공통으로 나오는 기능 단어는 키워드로 쓰지 않는다.
2. **필드 가중치 합산, 단독 1위만 채택**: 근거 필드 가중치(`position` 4, `main_tasks` 3, `requirements` 2, `preferred_points` 1)를 category별로 합산해 1위가 단독이면 채택한다. 1위가 동점이면 `etc`, 신호가 없어도 `etc`다.
3. **회사 단위 값은 쓰지 않음**: `company_name`과 원티드 `company.industry_name`(`PostingContent.industry`)은 판정에 쓰지 않는다.
4. **NULL과 `etc` 구분**: `postings.domain_category`의 NULL은 "아직 판정하지 않음"에만 쓴다. 판정을 실행하면 항상 7종 중 하나를 기록한다. `etc`는 신호가 없거나 1위가 동점이었다는 뜻이다.
5. **근거는 저장하지 않음**: 판정 근거(원문 필드·문장·키워드)는 함수 결과로만 돌려주고 DB에 저장하지 않는다. 근거를 저장하라는 명세가 없고, 저장하려면 BE 스키마를 바꿔야 한다.

## 이유

- Sprint 1 Wanted 처리는 구조화 필드를 규칙으로 변환하고 LLM을 호출하지 않는다([0006](0006-task-llm-usage-policy.md)). 판정 방식도 이 방향을 따른다.
- `industry_name`은 공고가 아니라 회사에 붙은 값이다. 직무와 관계없이 같은 회사의 모든 공고가 같은 값을 받으므로 회사명 기준 분류와 위험이 같다. 실제 공고 2건(`부동산`, `판매, 유통`)에서도 7종 키워드와 일치하지 않아 판정에 기여하지 못했다. 본문 키워드와 방향이 같을 때만 보조 근거로 쓰는 안은 결과를 거의 바꾸지 않으면서 규칙만 복잡하게 만들어 채택하지 않았다.
- 처음에는 category가 두 개 이상 나오면 모두 `etc`로 두었으나, 커머스 공고의 우대사항 한 줄이나 "결제" 같은 기능 단어만으로도 `etc`가 되어 누락이 지나치게 많았다. 직무를 설명하는 필드일수록 도메인 신호가 강하므로 가중치로 우열을 가리고(우대사항은 필수 요건보다 낮게 두어 W5 완료 기준 "우대를 필수로 바꾸지 않기"와 맞춘다), 우열이 없는 동점일 때만 추측을 피하려고 0005의 `etc` fallback을 적용한다.

## 영향

- 코드: `backend/app/llm_tasks/domain_signal.py`, `backend/tests/llm_tasks/test_domain_signal.py`.
- DB 스키마·공개 API·AI 내부 계약 변경 없음. 기존 `postings.domain_category`(nullable) 컬럼 안에서 값의 의미만 정한다.
- 판정 함수를 분석 파이프라인의 어느 단계에서 호출해 `domain_category`에 기록할지는 BE 파이프라인 연결 시 확인한다.
- 키워드 목록은 운영 중 오분류가 확인되면 이 결정의 범위 안에서 조정한다.

## 대체 관계

0005의 승인하지 않은 범위 중 "category 신뢰 판단 방식"만 채운다. 0005의 나머지 보류 범위(운영 seed 검수, 활성 version, 저장·migration)는 그대로 둔다.
