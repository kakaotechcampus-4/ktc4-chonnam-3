# 0022 공고 도메인 category의 LLM 판정

- 상태: Accepted
- 날짜: 2026-10-06
- 결정자: 박현솔 (AI C 역할 — JD·문서·Domain Context Builder 담당)
- 관련 PR: 없음 (이 결정과 함께 올림). 채택하지 않은 규칙안: #74
- 검토자: 2026-10-06 전체 회의에서 LLM 판정과 category 7종 유지를 합의. 아래 세부(입력·검증·실패 처리)는 담당 파트 내부 결정
- 연결 항목: [0005](0005-domain-question-policy.md)의 "승인하지 않은 범위" 중 category 신뢰 판단 방식, [0006](0006-task-llm-usage-policy.md)의 prompt version 목록

## 맥락

category 7종(`finance`·`game`·`travel`·`shopping`·`medical`·`mobility`·`etc`)과 "없거나 신뢰하기 어려우면 `etc`" 원칙은 [0005](0005-domain-question-policy.md)와 [도메인 질문 프레임](../features/domain-frames.md)에 정해져 있다. 공고에서 category를 어떤 근거로 판정할지는 0005에서 승인하지 않은 범위로 남아 있었다. W5 완료 기준은 "회사명만으로 도메인을 강제 분류하지 않기"다.

PR #74는 LLM 없이 공고 원문 키워드를 필드 가중치로 합산하는 규칙안을 제안했다. 실제 원티드 개발 공고 600건(2026-10-05 수집)에 적용하자 category가 정해진 203건 중 69건(34%)이 우대사항 한 줄만으로 결정됐고, "여행을 좋아하는 분" → `travel`, "4대보험" → `finance`, "항공우주공학" → `travel` 같은 오판이 다수였다. 키워드는 문장의 의미를 구분하지 못하고, 서비스 성격이 가장 잘 드러나는 회사·서비스 소개(`detail.intro`)는 회사 홍보 문구가 섞여 키워드 대상으로 쓰기 어려웠다.

원티드 `company.industry_name`도 대안이 되지 못한다. 같은 날 최신 개발 공고 1,000건 중 687건이 `IT, 컨텐츠`였고, 데이팅·라이브 스트리밍·에듀테크 공고 3건이 모두 같은 값이었다.

2026-10-06 전체 회의에서 LLM 판정 결과를 확인하고 LLM 판정을 채택했다. category 7종 개편(game 제거, `etc` 세분화)은 하지 않기로 했다.

## 결정

1. **LLM 판정**: 공고 원문을 읽고 category 7종 중 하나를 LLM이 고른다. #74의 키워드 규칙은 채택하지 않는다.
2. **입력**: `position`·`intro`·`main_tasks`·`requirements`·`preferred_points`만 넣는다. `company_name`과 `company.industry_name`(`PostingContent.industry`)은 넣지 않는다. 회사명이 입력에 있으면 모델이 학습 지식으로 회사의 업종을 추측하게 되어 W5 완료 기준과 어긋난다.
3. **판정 기준**: 이 포지션이 만드는 서비스의 도메인을 고른다. `intro`는 참고하되 직무 내용과 다르면 직무 내용을 따른다(예: 금융사의 사내 ERP 개발은 `finance`가 아니다). 우대사항의 취향·경험 문장과 복리후생은 근거로 쓰지 않는다. 근거가 부족하면 산업을 추측하지 않고 `etc`를 고른다([도메인 질문 프레임](../features/domain-frames.md) §선택과 질문 생성 1항).
4. **출력과 검증**: strict JSON schema로 `category`(7종 enum)와 `evidence`(판단 근거 원문 인용)를 받는다. `etc`가 아닌데 `evidence`가 비었거나 공백을 정규화한 입력 원문에 포함되지 않으면 근거를 신뢰할 수 없으므로 `etc`로 기록한다. 이 경우는 의미 검증 실패이므로 같은 입력으로 재호출하지 않는다.
5. **실패는 `etc`, NULL은 판정 전에만**: `postings.domain_category`의 NULL은 "아직 판정하지 않음"에만 쓴다. 공급자 오류·시간 초과·schema 오류로 공통 호출 재시도까지 실패하면 `etc`를 기록하고 분석 run은 실패시키지 않는다. 판정 단계를 거친 공고는 성공·실패와 관계없이 항상 7종 중 하나를 가진다.
6. **공고당 1회**: 판정은 공고 행에 한 번 기록한다. `JD_REUSE_TTL_DAYS` 안에서 공고 행을 재사용하면 저장된 category를 그대로 쓰고 LLM을 호출하지 않는다. prompt version이 바뀌어도 기존 행을 재판정하지 않는다.
7. **근거는 공고 행에 저장하지 않음**: `evidence`는 검증에만 쓰고 `postings`에 저장하지 않는다. 호출 metadata는 공통 LLM 호출 기록 방식을 따른다.
8. **prompt version 추가**: 새 task `domain_category`와 version `domain_category_v1`을 추가한다. 모델은 [0011](0011-sprint1-model-selection.md)의 기본 모델을 쓴다.

## 이유

- 우대사항 한 줄 오판의 원인은 키워드가 문장의 의미(서비스 설명인지, 지원자 취향인지)를 구분하지 못하는 데 있다. 필드 가중치 조정이나 "우대사항 단독 신호는 `etc`" 같은 규칙 보완은 오판을 줄이는 만큼 누락을 늘리고, `intro`를 활용하지 못하는 한계는 그대로 남는다.
- 회사명·`industry_name`을 입력에서 빼는 이유는 0021 규칙안과 같다. 회사 단위 값은 직무와 관계없이 같은 회사의 모든 공고에 같은 답을 준다. 회사명으로 외부 검색·원티드 OpenAPI 기업 정보를 조회하는 안도 같은 한계가 있고, 원티드 OpenAPI는 파트너 승인이 필요해 채택하지 않았다.
- 근거 인용 검증은 모델이 원문에 없는 근거로 category를 단정하는 경우를 `etc`로 되돌리기 위한 최소 장치다. 판정 근거를 원문에서 되짚을 수 있어야 한다는 0005의 방향을 따른다.
- 호출 실패를 `etc`로 기록하는 이유는 질문 생성이 NULL과 `etc`를 똑같이 `etc` frame으로 다루므로 사용자에게 보이는 차이가 없고, 공고 행을 재사용할 때 "판정 전"(NULL)과 "판정 후"를 값만으로 구분할 수 있기 때문이다. 대신 "근거가 없어 `etc`"와 "호출 실패로 `etc`"는 값으로 구분하지 못한다. 실패 건은 공통 LLM 호출 기록으로 확인하고, 실패한 공고를 재판정하지 않는다. NULL로 두는 안은 재사용 시 매번 다시 호출해야 하는지 판단할 규칙이 추가로 필요해 채택하지 않았다.
- 기존 `jd_extract_v1`은 요구사항 추출용 이름이다. 도메인 판정을 이 version에 얹으면 0006이 금지한 version 재정의가 되므로 새 version을 둔다.

## 영향

- AI: `ai/src/devon_ai/llm_tasks/domain_category.py`(출력 schema, 요청 생성, 근거 검증)와 테스트를 추가한다. [내부 계약](../contracts.md)의 prompt version 목록에 `domain_category_v1`을 추가한다.
- BE 확인 필요:
  - 판정 호출 위치. 분석 단계 순서([0010](0010-sprint1-interface-runtime-decisions.md))는 바꾸지 않고 `jd_extract` 단계 안에서 호출하는 안을 제안한다.
  - `PostingContent`에 `intro` 필드 추가. 현재는 `raw_text`에만 합쳐져 있다.
  - `backend/scripts/seed_prompt_versions.py`에 `domain_category` 추가.
  - BE 어댑터 `backend/app/llm_tasks/domain_category.py`(prompt 로드·호출·`postings.domain_category` 저장).
- DB 스키마·공개 API·category 값 집합 변경 없음.
- 비용: 새로 수집한 공고 1건당 LLM 호출 1회(재시도 포함 최대 2회).
- 검증: 원티드 개발 공고 100건 표본으로 사람 라벨과 LLM 판정을 비교한다. 결과와 실행 기록은 [구현 기록](../implementation.md)에 남긴다.
- 되돌리기: `postings.domain_category`의 값 집합이 같으므로 판정 함수만 교체하면 된다. 이미 기록된 값은 그대로 유효하다.

## 대체 관계

- 0005의 승인하지 않은 범위 중 "category 신뢰 판단 방식"을 채운다. 0005의 나머지 보류 범위(운영 seed 검수, 활성 version, 저장·migration)는 그대로 둔다.
- 0006의 "일곱 version 목록"에 `domain_category_v1`을 더한다. 기존 일곱 version을 삭제하지 않는다는 원칙과 Wanted 요구사항 분류의 LLM 비호출은 유지한다.
- #74의 0021 초안(미머지)은 채택하지 않았으며 develop에 기록하지 않는다. 규칙안의 실측 근거는 이 문서의 맥락에 옮겼다.
