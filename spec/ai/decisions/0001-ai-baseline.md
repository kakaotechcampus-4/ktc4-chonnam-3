# 0001 AI 구현 기준선

- 상태: Accepted
- 날짜: 2026-09-12
- 관련 PR: 없음
- 검토자: 현재 사용자 승인

## 맥락

AI 구현을 위한 자료가 `context/AI.md`, `ForAI.md`, `report.md`, 공통 계약, BE 명세, 기존 AI 초안에 흩어져 있다. 특히 작업 트리의 `context/AI.md`는 Persona, 통신 방식, 종료 전략, Domain·음성 단계에 대해 현재 `FIX` 계약과 다른 변경안을 포함한다. 구현자가 이 내용을 한 문서처럼 합치면 승인되지 않은 기능과 enum을 고정할 위험이 있다.

검토 시점은 `feature/spec-ai-docs` 브랜치의 `8dabd55`이며, `context/AI.md`의 미커밋 변경은 보존했다. 구체적인 근거와 충돌은 [AI 명세 원본 감사](../source-audit.md)에 기록한다.

## 결정

AI 구현 문서는 다음 기준선을 따른다.

1. 사용자의 현재 지시와 승인 범위를 최우선으로 한다.
2. `spec/shared/contracts`와 `spec/shared/glossary`, Sprint 1 `FIX` 기능 명세, `report.md`의 확정 항목을 구현 기준으로 사용한다.
3. `context/*`는 원래 비전과 변경 제안을 이해하는 자료로 보존한다. 기준선과 다른 내용은 자동 채택하지 않는다.
4. `PENDING_FE`, `PENDING_AI`, `PENDING_TEAM`과 Proposed 내부 계약은 구현값으로 확정하지 않는다.
5. 현재 기준선의 핵심은 텍스트 WebSocket 면접, 단일 Director와 세 Persona, 9턴 정책, 제한된 Evidence 검색, 근거 기반 리포트다.
6. Persona enum은 `tech_lead`, `hr_manager`, `domain_lead`다. 별도 Strategist Agent나 Senior Developer Persona를 추가하지 않는다.
7. Sprint 1 LLM 기준선은 설정·seed의 `5.5 Luna`다. 실제 provider/API model ID와 구조화 출력 적합성은 검증 전제이며 임의로 정하지 않는다.
8. 음성·STT·TTS는 Sprint 2다. 상세 음성 계약과 provider는 이 결정에 포함하지 않는다.
9. pgvector와 report score 공식은 각각 `PENDING_AI`, `PENDING_TEAM`으로 유지한다.

이 결정은 새 API, DB 테이블, 내부 JSON key, 모델 성능 임계값을 승인하지 않는다. [AI 내부 계약](../contracts.md)의 상세 구조는 Proposed이며 BE 검토 후 별도 승인해야 한다.

## 이유

- 최신 계약 이관표가 항목별로 `FIX`와 `PENDING`을 구분한다.
- `report.md`는 충돌을 검토한 뒤 확정한 내용을 날짜와 함께 기록한다.
- `context/AI.md` 자체도 일부 내용을 적용안·별도 결정으로 표시하며, 루트와 BE 작업 지침은 context를 구현 원본으로 사용하지 않도록 한다.
- 고정 기준과 미결정을 분리해야 Claude가 구현 편의를 위해 enum, 점수, provider, vector schema를 발명하지 않는다.

## 영향

- [AI 아키텍처](../architecture.md), 기능 명세, [내부 계약](../contracts.md), [검증 기준](../verification.md)은 이 기준선과 상태 표기를 사용한다.
- 기존 `spec/ai`의 모델 미확정 문구와 Persona 명칭은 최신 기준에 맞춰야 한다.
- 공통 API나 DB에 영향을 주는 변경은 `spec/shared/decisions` 또는 관련 팀 결정 기록으로 승격하고 소비 팀 검토를 거친다.
- `context/AI.md`의 변경안을 채택하려면 영향받는 FIX 명세와 계약을 먼저 변경한다.

## 미결정과 후속 결정

- pgvector/embedding 도입 여부, model, dimension, chunk, 재색인, 저장소
- Report 점수 기준, 스케일, 가중치, 합산과 필수 number 계약 처리
- 실제 Luna provider/API model identifier와 task별 schema 적합성
- Domain frame의 구체 문구와 품질 수용기준
- Evidence Retriever의 Sprint 2 확장과 `unverified` 처리 기준
- 음성 provider, voice ID, 오디오 형식, 전사 정정, 보존·삭제·재생, 채널 전환
- Proposed 내부 LLM 계약의 DB/API 채택 여부

다음 표는 구현자가 선택해야 하는 지점을 구체화한 검토 목록이다. 기준선 승인에 포함된 세부 결정은 아니다.

| 결정 | 필요한 합의·근거 | 합의 전 가능한 작업 |
| --- | --- | --- |
| 실제 model 연결 | provider, 호출 가능한 model ID, 인증 설정, task별 schema 적합성·사용량 확인 | provider 독립 mock, 계약·실패 검사 |
| 내부 계약 저장 | Question Contract·analysis·decision·feedback의 JSONB key/version, 실패 raw output 저장 위치와 보존 | Proposed fixture와 순수 변환 |
| Director 실행 제한 | Tool·재작성·재계획·timeout budget, SDK/gateway/worker 재시도 책임 | 설정 검증과 제한 소진 fake test |
| JD 신호 선행관계 | 7개 step과 첫 후보 ranking의 JD 신호 의존성 정리 | 독립 JD 변환·ranking 입력 검증 |
| L2 부분 검증 | 항목 하나라도 실패하면 전체 L2 실패인지, 검증된 1~5개 subset을 허용할지와 repo status·preparing_failed 매핑 | 유효/무효 notable area fixture, 잘못된 근거 차단 |
| 디렉터리 Evidence | notable area가 디렉터리인 경우 파일 열거 방식·깊이·개수·byte 상한 | 단일 파일/ref 검사 |
| 추천 점수 | 산식·정렬·미계산 표현; optional/nullable matchScore와 FE 동작 일치 | 근거 연결, 실패/미계산 구분 |
| WS 제출·복구 | 제출 식별자, stale 답변, 준비 실패/재시도, reconnect, sessionId | 현 메시지의 단일 연결 상태 검사 |
| 질문·평가 검증 | 정성 label, 원문 근거, 검증 불가·재계획 처리, 수용 임계값 | 검수용 대조 사례와 형식 검사 |
| 리포트 공개 성공 | 승인된 점수 또는 FE·BE 공통 계약 변경; 생성 가능 종료 상태 | narrative·근거 연결, lazy job mock |
| 리포트 재실행 | lock 만료와 별개인 durable attempt 상태·재enqueue·중복 저장 제약 | 실패/지연 worker 시나리오 |
| 품질·원문 운영 | 데이터셋 검수·분리, 비용/latency 목표, 원문 접근·보존 | 비식별 fixture와 실행 기록 형식 |

공통 API 상태·enum·새 필드는 소비 팀과 함께 결정하고, 내부 구현 방식은 AI·BE의 해당 경계에서 검토한다. 보류가 있는 기능의 전체 성공을 주장하지 않되 합의된 독립 기능 작업까지 중단하지 않는다.

## 대체 관계

이전 AI 결정 기록을 대체하지 않는다. 이후 기준선이 바뀌면 이 문서를 수정해 과거 결정을 지우지 말고, 후속 결정에서 `Superseded` 관계를 명시한다.
