# AI 후속 기능 경계

작성일: 2026-09-12. 상태: **Proposed**.

이 문서는 Sprint 1 이후 검토할 AI 확장 항목과 현재 구현 경계를 분리한다. 미래 방향을 기록할 뿐 새 API, 공개 payload, DB column·table, provider, 모델, 일정 또는 완료 상태를 승인하지 않는다.

관련 문서: [AI 아키텍처](../architecture.md), [내부 계약](../contracts.md), [검증](../verification.md), [AI 기준선](../decisions/0001-ai-baseline.md).

원본: [BE 아키텍처](../../../spec/backend/architecture.md), [문서 명세](../../../spec/backend/features/documents.md), [면접 명세](../../../spec/backend/features/interview.md), [리포트 명세](../../../spec/backend/features/report.md), [FE 분석 명세](../../../spec/frontend/features/analysis.md), [FE 면접 명세](../../../spec/frontend/features/interview.md), [FE 리포트 명세](../../../spec/frontend/features/report.md), [계약 이관](../../../spec/shared/contracts/migration.md), [DB 명세](../../../backend/docs/db-schema.md).

## Sprint 1 기준선

- 면접은 텍스트 WebSocket이다. 사용자가 제출한 `answer.text`를 기존 AnswerAnalysis와 Director 의미 처리 경로에 전달한다.
- 문서 preview는 PDF·DOCX·TXT·MD에서 텍스트와 GitHub URL을 추출한다. 선택 문서가 존재해도 Claim을 생성하거나 `document_claims` row를 만들지 않는다.
- `domain_lead`는 검수·version 관리되는 `domain_question_frames` seed를 사용한다. 외부 도메인 자료 검색이 있어야만 동작하는 Persona가 아니다.
- 스캔 이미지 PDF와 일반 이미지의 OCR·공고 판독은 지원하지 않는다.
- `report_disagreements`는 Sprint 1 migration 작성 시 포함해야 하지만 API와 row 생성은 하지 않는다. FE 이의 제기 동작도 활성화하지 않는다.
- 음성/STT/TTS column·table을 만들지 않는다. 현재 DB 명세가 제외한 `audio_uri`, `transcript_confidence` 같은 필드를 미리 추가하지 않는다.

## 확장별 경계

| 항목 | Sprint 1 기준선에 포함된 것 | 미래 검토 범위 | 지금 확정하지 않는 것 |
| --- | --- | --- | --- |
| 음성·STT·TTS | 텍스트 질문, 단일 텍스트 답변, 기존 의미 분석 | 입력 녹음, 전사, 질문 음성 출력, 실패·복구·보존 정책 | provider, voice ID, 오디오 형식, wire event, 저장 column/table, 브라우저 권한 UX |
| 문서 Claim | preview의 추출 텍스트·GitHub URL, `document_claims` migration 포함·row 생성 없음 | 자소서·포트폴리오 Claim 추출, 원문 연결, 문서와 코드의 충돌 검토 | Claim schema, 생성 시점, 신뢰도, document conflict API, 자동 사실 판정 |
| 외부 도메인 자료 검색 | Sprint 1 `domain_question_frames` seed | 출처가 검수된 외부 자료를 별도 retrieval 입력으로 제공하는 방식 | 검색 provider, corpus, 최신성 주기, 인용 형식, 권한, pgvector 사용 여부 |
| 이미지 공고 판독 | Wanted URL의 텍스트 공고 수집 | 동일 공고 URL 경로에서 이미지 본문 판독, 원문·구조 추출·품질 검증 | 지원 format, OCR provider, 실패 reason, 이미지 원본 저장 |
| 리포트 이의 제기 | `report_disagreements` migration 포함·row/API 없음, Sprint 1 버튼 비활성 | 사용자 제출, persona별 중복 방지, 검토·응답·상태 표시 | 공개 endpoint/payload, 처리 SLA, 자동 재채점, 점수 변경 정책 |

## 음성의 의미 처리 재사용

위 표는 단계별 요구사항이며 현재 테이블·화면·기능이 구현돼 있다는 뜻은 아니다. 실제 구현 상태는 [원본 검토](../source-audit.md)를 따른다.

음성 확장의 목표는 기존 면접 의미를 다른 입력·출력 채널로 전달하는 것이다. 검수된 최종 전사 텍스트는 가능한 한 현재의 `answer.text`와 같은 AnswerAnalysis, Evidence 보강, Director 판단 경로를 재사용한다. 채널별 Controller가 권한·길이·순서·중복·보존을 처리하고, 의미 평가 로직을 음성 전용으로 복제하지 않는다.

이 원칙은 전사 수정 UX, 중간 transcript 이벤트, 오디오와 텍스트의 원본 관계, 저장 책임을 정한 계약이 아니다. provider의 realtime 기능이나 별도 STT/TTS 조합 중 어느 것도 선택하지 않는다. 실제 provider·API model ID·비용·지연·한국어 품질을 비교한 뒤 공통 계약과 FE 상태를 함께 결정해야 한다.

## Claim과 이미지 입력

Sprint 1의 `doc_extract`와 문서 preview를 Claim 추출로 해석하지 않는다. 현재 문서는 면접 추천을 돕는 텍스트·GitHub URL 신호이며, 자기소개서나 포트폴리오의 사실 주장을 구조화하지 않는다.

후속 Claim은 원문 위치, 문서 version, 사용자 발언과의 구분, 검증 상태를 잃지 않아야 한다. 문서에 적혔다는 사실과 코드로 확인됐다는 사실을 구분하며, 충돌을 발견해도 사용자에게 거짓이라고 단정하지 않는다. 이미지·OCR 입력도 같은 원문 연결과 품질 한계를 가져야 하며, 인식 실패를 빈 Claim이나 부정 평가로 바꾸지 않는다.

Claim·OCR을 도입할 때는 기존 `answer_vs_code`와 새 문서 충돌의 source를 분리하고, `document_claims` FK·row 생성 시점·보존 정책을 BE migration과 함께 검토한다. 이 문서는 새 schema나 endpoint를 제안하지 않는다.

이미지 공고는 URL 수집 경로의 확장이다. JD 본문 직접 입력·독립 이미지 업로드를 새 입력 기능으로 추가하지 않는다. 공고 이미지 판독 지원이 스캔된 모든 사용자 문서의 OCR 지원까지 자동으로 확정하는 것도 아니다.

## 외부 도메인 자료

Sprint 1 `domain_lead`는 [도메인 질문 프레임](domain-frames.md)만으로 질문 관점을 구성할 수 있다. 따라서 외부 검색 부재를 Sprint 1 준비 실패로 처리하지 않는다.

미래 retrieval은 출처·사용 권한·적용 지역·기준 시점·검수자를 확인한 자료만 Context 후보로 제공한다. 검색 결과와 seed frame, JD 요구사항, 사용자 프로젝트 Evidence를 서로 다른 출처로 유지한다. 특히 법률·규제·의료 자료는 모델의 일반 지식이나 단일 검색 결과를 정확성 보증으로 사용하지 않고 별도 전문가 검토 경계를 둔다.

후속 외부 자료 조회에서 실시간 공개 웹 검색, 고정 corpus, 일반 DB 검색, vector 검색 중 어느 방식을 쓸지는 미정이다. [0002 결정](../decisions/0002-sprint1-vector-search.md)은 Sprint 1 vector 검색·extension 선설치를 제외하며, Sprint 2 도입을 승인하지 않는다. 외부 자료 기능을 설명하기 위해 extension이나 embedding table을 먼저 만들지 않는다.

## 리포트 이의 제기

Sprint 1 리포트는 실제 문답과 근거를 보존해 생성하되 이의 제기 제출은 받지 않는다. table이 있다는 이유로 endpoint나 row를 만들지 않고, 비활성 FE 버튼을 동작하는 기능으로 보고하지 않는다.

후속 구현 전에는 제출 단위, persona 식별, 중복 방지, 검토 책임, 사용자에게 보일 상태, 개인정보 보존, 피드백이 원문·평가·점수에 미치는 영향을 함께 결정해야 한다. 이의 제기가 자동 재채점이나 원문 수정 권한을 의미하지 않는다. 점수 공식과 scale이 `PENDING_TEAM`인 동안 이 기능으로 임의 점수 변경 규칙을 만들지 않는다.

## 결정과 일정 경계

각 확장은 관련 FE·BE·공통 계약 결정, threat/privacy 검토, 실패 상태, fixture, 실제 provider 검증을 거친 뒤 구현한다. 기존 [내부 계약](../contracts.md)의 Proposed 필드를 공개 계약이나 물리 schema로 자동 승격하지 않는다.

W10~W11을 숨은 보충 작업 기간으로 사용하지 않는다. 이 문서의 항목은 기존 일정의 빈칸을 채우는 할당이 아니며, 승인된 Sprint 2 계획과 소유자가 생기기 전에는 구현 backlog 상태로도 단정하지 않는다.

## 검증 기준

- Sprint 1 테스트와 완료 보고에 음성, Claim row, 외부 도메인 retrieval, 이미지 OCR, 이의 제기 API를 포함하지 않는다.
- 문서 preview와 Claim 추출, seed frame과 외부 retrieval, 텍스트 의미 처리와 음성 channel 처리를 각각 구분한다.
- 확장으로 들어온 실패·미발견·낮은 인식 품질을 사용자 역량이나 사실 오류로 자동 변환하지 않는다.
- provider·모델·format·API·DB·점수 정책을 명시적 결정 없이 고정하지 않는다.
- 실제 확장 검증은 [AI 검증](../verification.md)의 계약, 모델, 통합, 전체 서비스 단계를 분리해 기록한다.
