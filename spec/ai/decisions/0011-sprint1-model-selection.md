# 0011 Sprint 1 모델 선택

- 상태: Accepted — 모델 선택 범위
- 날짜: 2026-09-21
- 결정자: 현재 사용자
- 관련 PR: 없음
- 결정 근거: 사용자의 “gpt-5.6 luna로 정해.” 지시

## 맥락과 결정

기존 `5.5 Luna` 표기는 실제 공급자와 API 식별자가 확인되지 않은 기준선이었다. 사용자 선택에 따라 Sprint 1의 LLM 모델을 **OpenAI GPT-5.6 Luna**, API 모델 ID **`gpt-5.6-luna`**로 정한다. 기존 L1·L2·답변 분석·Director·리포트의 단일 모델 방향을 유지한다.

Wanted 규칙 변환과 프로필 확정 집계는 [0006 결정](0006-task-llm-usage-policy.md)에 따라 LLM을 호출하지 않는다. 모델 선택으로 비호출 작업에 호출을 추가하지 않는다. 후속 [0019](0019-sprint1-profile-role-summary-restoration.md)에서 복원한 개인 역할의 자연어 요약에는 이 문서의 선택 모델을 사용하며, 통계 집계는 계속 LLM에 맡기지 않는다.

## 확인 근거와 이유

2026-09-21 [OpenAI 공식 모델 문서](https://developers.openai.com/api/docs/models/gpt-5.6-luna)를 조회해 모델 ID와 Responses·Chat Completions endpoint, structured outputs·function calling 지원을 확인했다. 정확한 ID는 공식 문서로 확인하고, 모델 선택은 사용자의 명시적 지시를 따른다. 성능 비교나 비용 실측을 완료했다는 결정은 아니다.

## 영향과 남은 확인

- 설정·seed에서 모델을 읽고 실제 사용값을 기록하는 기존 원칙을 유지한다. 모델명은 코드 상수로 고정하지 않는다.
- 서비스용 인증 설정, SDK/client·호출 경로와 모델 버전 기록 방식은 AI-L01에 남긴다. 기존 `anthropic` 의존성과 Claude client 설명만으로 이 모델 연결이 구현된 것으로 판단하지 않는다.
- 공식 기능 지원과 서비스 적합성은 구분한다. 계정 접근, task별 schema 준수·도구 호출, 지연·비용·품질은 실제 연결과 평가에서 확인한다. 이번에는 API 호출이나 계정 검증을 수행하지 않았다.
- 공통 호출 계층의 총 2회 attempt, semantic 실패 재호출 금지, ARQ `max_tries=1`은 [0010 결정](0010-sprint1-interface-runtime-decisions.md)을 유지한다. 실행 상한은 AI-L04에서 정한다.
- 모델 선택을 AI·BE 아키텍처와 결정 목록에 반영한다. 내부 계약, SDK 설치, 서비스 코드·DB·공개 API 변경까지 승인한 것으로 확대하지 않는다.

## 대체 관계

[0001 결정](0001-ai-baseline.md)의 7번 모델 선택과 기존 `5.5 Luna` 안내만 대체한다. 과거 결정·감사 기록은 작성 당시 이력으로 보존하며, 기존 `backend/CLAUDE.md`의 모델명 안내보다 이 사용자 결정과 갱신된 아키텍처를 우선한다. 팀 검수나 실제 연결 완료를 대신하지 않는다.
