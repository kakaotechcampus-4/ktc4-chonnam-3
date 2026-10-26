# 0007 음성 전용 면접 전환 — WS·REST 계약 변경

- 상태: Proposed
- 날짜: 2026-10-05
- 작성: 진영 (FE)
- 검토자: BE·AI (검토 대기)
- 관련 PR: 없음 (FE 설계·mock 작업 PR에서 연결 예정)
- 관련 설계: [FE 음성 면접 설계](../../frontend/designs/2026-10-05-voice-interview.md)

## 맥락

Sprint 1 면접은 텍스트 전용이다(`answerMode: "text"`, [migration.md](../contracts/migration.md) "Sprint 1 면접 입력 텍스트-only"). Sprint 2부터 텍스트 면접을 없애고 음성으로만 진행한다. 음성 계약은 [AI 후속 기능 AI-L21](../../ai/features/extensions.md)에 "Sprint 2 착수 전 AI·FE·BE·팀이 결정"으로 남아 있고, 현재 FE 명세의 Sprint 2 참고안(`answerStart`·오디오·`answerEnd`·`transcript`·`questionEnd`)은 확정된 계약이 아니다.

면접 준비 화면의 마이크·스피커 점검과 마이크 미확인 시 시작 차단은 `feature/interview-voice-check`에서 먼저 반영했다. 이 결정은 진행 화면의 답변·질문 음성 계약을 정한다.

WS 계약 원본은 `openapi.yaml`이 위임한 `frontend/docs/api-spec.md` #18이다. 이 ADR이 Accepted 되면 그 문서와 `openapi.yaml`, BE migration을 함께 갱신한다.

## 결정

### 1. 답변 방식

- `AnswerMode` 값을 `["text"]`에서 `["voice"]`로 바꾼다. 필드는 유지한다. DB `interview_sessions.answer_mode` 기본값·CHECK도 `voice`로 바꾼다.
- 텍스트 답변 `answer { turn, text }`를 제거한다.
- 사용자의 다시 녹음 기능은 두지 않는다. 실패했을 때만 같은 턴에 다시 답변한다.

### 2. WS 메시지

클라이언트 → 서버

| 메시지 | 형태 | 설명 |
| --- | --- | --- |
| `answerStart` | `{ "type": "answerStart", "turn": 3, "mimeType": "audio/webm;codecs=opus" }` | 답변 시작. `mimeType`은 브라우저 `MediaRecorder` 결과 그대로 |
| 오디오 조각 | WS binary frame | 녹음 중 일정 간격(FE 기본 250ms)으로 전송. 간격은 계약으로 고정하지 않음 |
| `answerEnd` | `{ "type": "answerEnd", "turn": 3 }` | 답변 종료. 사용자가 누르거나 180초가 지나면 FE가 보냄 |

서버 → 클라이언트

| 메시지 | 형태 | 설명 |
| --- | --- | --- |
| `question` | `{ "type": "question", "persona": "tech_lead", "text": "...", "turn": 3, "mainIndex": 2, "followUpDepth": 1, "audioUrl": "/api/interviews/{id}/turns/3/question-audio" }` | 기존 필드에 `mainIndex`(메인 질문 순번, 1부터), `followUpDepth`(메인 0, 꼬리질문 1..), `audioUrl` 추가. TTS 완료를 기다리지 않고 바로 보낸다 |
| `transcriptPartial` | `{ "type": "transcriptPartial", "turn": 3, "text": "..." }` | **선택.** STT가 스트리밍을 지원할 때만 보냄. 표시 전용이며 이후 값이 앞 값을 대체한다 |
| `transcript` | `{ "type": "transcript", "turn": 3, "text": "..." }` | 최종 전사. 서버가 `answer_text`로 저장하는 값이며 평가에 쓰인다 |
| `answerReceived`·`thinking`·`evidenceCheck`·`interviewEnd`·`error` | 기존과 같음 | |

- `questionEnd`는 도입하지 않는다. 기존처럼 `question`이 질문 전달 완료를 뜻한다.
- 같은 턴의 `question`이 다시 오면 **다시 듣기**다(아래 5).

### 3. 실패와 복구

- `answerReceived` 전에 답변이 끊기면 실패이고, 같은 턴에 다시 답변한다. 남은 시간은 계속 흐른다.
- 새 error reason `stt_failed`(`recoverable: true`)를 추가한다. 전사 결과가 비면 `details.cause = "empty_transcript"`.
- 같은 턴으로 `answerStart`가 다시 오면 서버는 그 턴의 미완료 오디오를 버리고 새로 받는다.
- 답변 수신 중 오디오가 일정 시간(제안 10초) 없으면 서버가 미완료 오디오를 버린다.
- 녹음 중 WS가 끊기면 서버는 미완료 오디오를 버린다. 재연결 후 `GET /interviews/{id}`의 마지막 턴 `answer`가 `null`이므로 FE가 다시 답변하게 한다.
- WS 연결(새로고침·재연결 포함) 직후 마지막 턴의 `answer`가 `null`이면 서버는 그 턴의 `question`을 같은 `turn`·`audioUrl`로 다시 보낸다. FE는 이 메시지로 질문 음성 주소를 다시 얻으며, 질문 음성을 위한 REST API·응답 필드는 추가하지 않는다. 마지막 턴 답변이 저장됐고 다음 질문을 만드는 중이면 다시 보내지 않고 기존 흐름대로 다음 `question`을 보낸다. 다시 보낸 `question`은 턴 수에 넣지 않는다.
- 새로고침 직후에는 브라우저 자동재생 정책 때문에 질문 음성이 재생되지 않을 수 있다. 이때는 질문 음성 실패와 같이 FE가 질문 텍스트를 보여 준다.
- `tts_failed` error는 만들지 않는다. 질문 음성이 없거나 재생에 실패하면 FE가 질문 텍스트를 보여 준다. 원인은 서버 로그에 남긴다.
- 최대 답변 길이 180초는 FE와 서버 모두 지킨다.

### 4. 질문 음성 전달·보관

- 새 엔드포인트 `GET /api/interviews/{id}/turns/{turn}/question-audio`. 기존 세션 쿠키로 인증한다. 생성 중이면 완료까지 기다렸다 응답하고, 실패·만료면 오류로 응답한다. `Content-Type`으로 형식을 알린다.
- TTS 결과는 Redis에 TTL(제안 24시간)로 보관한다. 만료 후에는 재생성하거나 텍스트로 대체한다.
- 답변 원본 오디오는 저장하지 않는다. STT로 전달한 뒤 버리고 최종 전사만 `interview_turns.answer_text`에 저장한다.

### 5. 음성으로 다시 듣기

- 다시 듣기 버튼은 두지 않는다. 사용자가 "다시 말씀해 주세요"처럼 답하면 서버 AI가 판단해 같은 `turn`·`audioUrl`로 `question`을 다시 보낸다.
- 이때 `answerReceived`는 보내지 않고, 그 발화를 `answer_text`·분석·턴 수에 넣지 않는다.

### 6. 메인 질문과 꼬리질문 표시

- 면접 질문은 꼬리질문을 포함해 총 9턴으로 고정한다(2026-10-05 팀 결정). 꼬리질문도 1턴으로 센다. [0004](0004-flexible-persona-allocation-restoration.md)의 "정상 9턴"과 같은 뜻이며 0004는 바꾸지 않는다.
- 화면은 `질문 {turn} / {totalTurns}`와 꼬리질문이면 `· 꼬리질문 {followUpDepth}`를 표시한다. `totalTurns`는 기존 의미(전체 턴 수 9) 그대로이며 새 필드를 만들지 않는다.
- `mainIndex`는 같은 메인 질문에 딸린 꼬리질문을 묶는 용도다. 메인 질문 수는 꼬리질문 수에 따라 달라지므로 화면에 분모로 쓰지 않는다.
- `GET /interviews/{id}`의 `turns`에도 `mainIndex`·`followUpDepth`가 있어야 새로고침 후 같은 표시를 복구한다.

## 이유

- **질문 음성을 URL로 전달**: WS binary로 보내면 텍스트 메시지와 짝 맞추기, 새로고침·재연결 시 재전송 메시지, 큰 프레임이 작은 메시지를 지연시키는 문제가 생긴다. URL이면 `<audio>`가 다운로드·재생을 맡고 재연결과 무관하다. 대가는 BE의 보관(Redis TTL)뿐이다.
- **답변을 조각으로 전송**: 녹음이 끝난 뒤 한 번에 보내면 스트리밍 STT를 써도 실시간 자막이 불가능하다. 조각 하나는 opus 기준 약 1KB, 말하는 사용자당 초당 약 4KB로 서버 부하는 작다.
- **`transcriptPartial` 선택**: STT 모델이 미정이다. 스트리밍 여부와 무관하게 FE가 동작하도록 선택 메시지로 둔다. 평가에는 최종 전사만 써서 임시 전사의 부정확성이 점수에 들어가지 않게 한다.
- **`answerCancel` 미도입**: 같은 턴 `answerStart` 재시작과 오디오 없음 타임아웃으로 같은 결과를 얻는다. 메시지 종류를 늘리지 않는다.
- **`AnswerMode`를 `voice` 단일 값으로**: 텍스트 경로를 유지하지 않으면서 필드 소비자를 깨지 않는다. 필드 삭제는 영향이 크다.
- **브라우저 기본 녹음 형식**: PCM 통일은 크기가 약 8배이고 FE 오디오 처리가 복잡하다. `mimeType`을 함께 보내 서버가 형식을 안다.

## 영향

- FE: 진행 화면 음성 전환, 타입·MSW mock 변경. 상세는 관련 설계.
- BE: WS 오디오 수신·STT 중계, 연결 시 답변 전 마지막 턴 `question` 재전송, `question-audio` 엔드포인트, Redis TTS 보관, `answer_mode` migration, `stt_failed` reason, `mainIndex`·`followUpDepth` 응답, 같은 턴 재시작·타임아웃 규칙.
- AI: 다시 듣기 요청 판단, 꼬리질문을 포함한 9턴 안에서 메인 질문·꼬리질문 구조와 `mainIndex`·`followUpDepth` 부여. 9턴·Persona 배분은 [0004](0004-flexible-persona-allocation-restoration.md)를 따른다.
- 계약 문서: `frontend/docs/api-spec.md` #18, `openapi.yaml`(`AnswerMode`, `question-audio`, 상세 조회 응답), `backend/docs/error-reasons.md`(`stt_failed`), [migration.md](../contracts/migration.md) "Sprint 2 면접 입력" 행.
- 되돌리기: Accepted 전에는 FE mock만 바뀐다. 이후 되돌리면 `AnswerMode`와 WS 메시지를 함께 되돌린다.

## BE·AI 확인 항목

1. STT·TTS provider·모델(미정). STT가 webm/opus·mp4/aac를 받는지, 스트리밍 임시 전사가 가능한지. TTS 한국어 지원.
2. 운영 DB에 기존 `answer_mode = 'text'` 세션이 있는지(있다면 migration 처리).
3. 오디오 없음 타임아웃 값, TTS 보관 TTL 값.
4. 다시 듣기 판단 방식(규칙·LLM)과 오판 방지, 비용.
5. ~~메인 질문 수 전달 방식(`totalTurns` 의미 변경 또는 새 필드)과 0004 갱신 여부.~~ 해결: 꼬리질문 포함 총 9턴 고정, `totalTurns` 기존 의미 유지, 0004 변경 없음(위 6).

## 대체 관계

- Sprint 1 텍스트 입력 계약([migration.md](../contracts/migration.md) "Sprint 1 면접 입력 텍스트-only")을 Sprint 2에서 대체한다. Accepted 시 해당 행과 FE 명세의 Sprint 2 참고안을 갱신한다.
