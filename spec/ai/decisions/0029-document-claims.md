# 0029 포트폴리오 문서 Claim 추출 (AI 모듈)

- 상태: Accepted
- 날짜: 2026-10-26
- 결정자: 박현솔 (AI C 역할 — JD·문서·Domain Context Builder 담당)
- 관련 PR: 없음 (이 결정과 함께 올림)
- 검토자: 담당 파트 내부 결정. BE 저장·호출 위치와 Director 사용은 아래 "확인 필요"로 각 담당자에게 제안한다.
- 연결 항목: [AI-L22](../features/extensions.md#ai-l22-문서-claim과-문서코드-충돌), [0010](0010-sprint1-interface-runtime-decisions.md)의 "문서 claim 추출은 Sprint 2로 넘긴다"
- 후속 정정: [0030 검증 순서와 서비스 연결 경계](0030-document-claims-validation-boundary.md). 아래 원본의 면접 준비 상태·기존 `claim_checks` 재사용·호출 단위 설명은 후속 경계와 함께 읽는다.

## 맥락

C 역할의 산출물 중 하나는 "확인된 문서 주장"이다. Sprint 1은 포트폴리오 preview에서 텍스트와 GitHub URL만 추출하고, `document_claims` 테이블은 만들었지만 row를 만들지 않았다([BE 모델](../../../backend/app/db/models/document.py)). 면접 쪽은 Claim을 받을 준비가 돼 있다. `interview_turns.claim_ids`가 있고, `AnswerAnalysis.claim_checks`가 주장의 지지 상태(`supported`·`partially_supported`·`unverified`·`conflicting`)를 다룬다. 빠진 것은 문서에서 Claim을 뽑는 단계다.

[후속 기능 경계](../features/extensions.md)는 Claim 도입 시 지킬 원칙을 정해 두었다. 원문 위치를 잃지 않고, 문서에 적힌 사실과 코드로 확인된 사실을 구분하며, 충돌해도 거짓으로 단정하지 않고, 인식 실패를 부정 평가로 바꾸지 않는다.

일정상 이 항목은 Sprint 2(W8~W9) 범위였고 착수하지 못했다. 이번 결정은 AI 쪽 추출 모듈의 범위만 정한다.

## 결정

1. **대상 문서는 포트폴리오만**: 지금 preview가 받는 문서다. 자소서는 preview·업로드 경로 변경(BE·FE)이 필요해 이번 범위에서 제외한다.
2. **내부 전용**: Claim은 면접 질문의 재료이며 사용자에게 보여주거나 확인·수정·제외를 받지 않는다. FE 화면과 공개 API를 추가하지 않는다.
3. **줄 ID 입력**: 추출 텍스트의 비어 있지 않은 줄마다 `L<순번>`(0부터) ID를 붙여 `{lines: [{id, text}]}`로 보낸다. PDF 추출은 페이지 사이에만 빈 줄을 넣고 DOCX 추출은 문단을 한 줄씩 이어 붙이므로, 빈 줄 기준 문단으로는 원문 위치를 가리킬 수 없다. `document_claims.paragraph_no`에는 이 줄 순번을 저장한다. 같은 문서의 `extracted_text`로 원문 줄을 복원할 수 있다.
4. **출력**: `{claims: [{claim_text, claim_type, tech_tags, line_id}]}`, 최대 20개.
   - `claim_type`은 확인 방법 기준 4종이다. `tech_usage`(기술 사용)와 `implementation`(직접 구현·설계)은 코드와 비교할 수 있고, `outcome`(수치·성과)은 코드로 확인할 수 없어 측정 방법을 묻는 재료이며, `role`(팀 안의 역할·기여 범위)은 `hr_manager`의 재료다.
   - `claim_text`는 원문 주장을 한국어 한 문장으로 옮긴 것이다. 원문에 없는 기술·수치를 더하지 않는다.
   - `tech_tags`는 그 주장에 이름이 나온 기술만, 최대 5개다.
   - `line_id`는 주장이 적힌 줄(두 줄에 걸치면 시작 줄)이다.
5. **검증과 실패**: schema 위반은 `ContractError("schema")`, 이번 요청에 없는 줄 ID는 `ContractError("semantic")`으로 공통 호출 계층의 validator 안에서 거절한다([0028](0028-domain-category-evidence-id.md)과 같은 방식). 한 항목이라도 위반하면 호출 전체를 실패로 기록하고 Claim을 저장하지 않는다. 실패해도 분석 run은 실패시키지 않으며 Claim이 없는 상태로 면접을 진행한다. 주장이 없는 문서(`claims: []`)는 성공이다.
6. **Claim은 사실이 아니다**: 추출 단계에서 진위·지지 상태를 판정하지 않는다. 확인은 면접 중 기존 Evidence와 `claim_checks`로 한다. 코드와 다르거나 코드에서 찾지 못해도 거짓으로 단정하지 않고 확인 질문으로 다룬다(비공개 레포·다른 브랜치·회사 코드일 수 있다).
7. **`confidence`는 비워 둔다**: 모델이 스스로 매긴 신뢰도는 근거가 없어 요청하지 않고 NULL로 저장한다.
8. **version**: task `doc_claims`, prompt `doc_claims_v1`(`ai/prompts/doc-claims-v1.md`), schema version `1`.

## 이유

- 줄 ID 선택은 0028에서 실호출로 효과를 확인한 방식이다. 모델이 원문을 옮겨 쓰다 바꾸는 문제를 피하고, 원문 위치를 코드로 확정한다.
- 한 항목 위반 시 전체 실패로 두는 이유: 기록된 실패는 오류 조회로 추적할 수 있지만, 조용히 버린 항목은 남지 않는다. 0028 실측(500건)에서 ID 방식의 검증 실패는 0건이었다. 실패가 잦으면 위반 항목만 버리는 방식으로 바꾼다.
- 확인 방법 기준 4종은 면접에서 어떻게 다룰지(코드 비교, 측정 방법 질문, 역할 질문)와 바로 연결된다. 2종(확인 가능·불가)은 단순하지만 어느 Persona의 재료인지 구분하지 못한다.
- 사용자 확인 화면은 Claim 품질을 높이지만 W11~W13 일정에 새 화면이 없다. 내부 전용으로 두고 사용자에게 보이는 영향(질문)으로 품질을 판단한다.

## 영향

- AI: `ai/src/devon_ai/llm_tasks/doc_claims.py`(요청 생성, 줄 ID 검증·줄 번호 복원), `ai/prompts/doc-claims-v1.md`, 테스트. [내부 계약](../contracts.md)에 `doc_claims_v1`을 추가한다.
- BE 확인 필요 (BE 담당):
  - 호출 위치. 분석 단계 순서([0010](0010-sprint1-interface-runtime-decisions.md))는 바꾸지 않고 `doc_extract` 단계에서 문서가 있을 때 호출하는 안을 제안한다. 같은 문서 row는 한 번만 추출하고 다시 호출하지 않는다.
  - BE adapter `backend/app/llm_tasks/doc_claims.py`(현재 예정 위치 docstring만 있음): prompt 로드·호출·`document_claims` 저장(`claim_text`·`claim_type`·`tech_tags`·`paragraph_no`, `confidence`=NULL).
  - `seed_prompt_versions.py`에 `doc_claims` 등록.
  - `claim_type` 값 집합이 정해졌으므로 CHECK 제약 추가 여부(모델 주석: "값 집합은 Sprint 2 claim 추출 구현 때 확정한다").
- Director·면접 확인 필요 (Director 담당): `Context`에 Claim 목록을 넘기는 필드, `BasisKind`에 문서 Claim 추가, 질문에 쓴 Claim을 `interview_turns.claim_ids`에 기록하는 방식.
- FE·공개 API·DB 스키마 변경 없음.
- 비용: 포트폴리오가 있는 분석 run당 LLM 호출 1회(schema 오류 재시도 포함 최대 2회). 입력은 최대 50,000자(`documents_max_text_chars`)다.
- 검증 한계: 실제 모델 호출과 추출 품질 평가는 하지 않았다. 실측 결과는 [구현 기록](../implementation.md)에 둔다.

## 대체 관계

- AI-L22의 남은 결정 중 Claim schema·추출 대상·원문 위치·검증 상태(추출 단계 미판정)·사용자 확인(하지 않음)을 정한다. 추출·사용 시점의 BE 연결, `document_claims` FK·보존, 문서와 코드 충돌의 `evidence_conflicts` source는 위 확인 필요 항목과 함께 남는다.
- 0010의 "문서 claim 추출은 Sprint 2로 넘긴다" 중 포트폴리오 Claim 추출을 채운다. 자소서 기반 Claim은 여전히 범위 밖이다.
