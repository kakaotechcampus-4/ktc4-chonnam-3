# 음성 면접 진행 화면(5b-v2) 설계

상태: Proposed
작성일: 2026-10-05
제안: FE (진영)
결정 필요: BE·AI — 계약은 [공통 0007](../../shared/decisions/0007-voice-interview-contract.md)에서 검토

## 배경

Sprint 2부터 면접은 음성으로만 진행한다. 준비 화면(5a2-v2)의 마이크·스피커 점검과 마이크 미확인 시 시작 차단은 `feature/interview-voice-check`에서 반영했다. 이 문서는 진행 화면을 음성으로 바꾸는 FE 설계다. WS·REST 계약 변경은 0007에 두고 여기서는 반복하지 않는다.

STT·TTS 모델은 미정이다. FE는 특정 모델에 묶이지 않게 만들고, BE 없이 MSW mock으로 개발한다.

## 범위

포함

- 진행 화면 음성 전환: 질문 음성 재생, 답변 녹음·전송, 실시간 자막, 최종 전사 표시, 실패 복구
- 질문 번호의 메인·꼬리질문 표시, 다시 듣기 안내 팁
- 타입, `useInterviewSocket` 바이너리 전송, MSW WS·질문 음성 mock과 실패 시나리오
- Playwright 테스트

제외

- BE의 WS 오디오 처리, STT·TTS 연동, Redis 보관, AI의 다시 듣기 판단 (0007 확인 항목)
- 실서버 연동 검증 (BE 작업 이후)

## 화면

기존 5b-v2 배치를 유지한다. 텍스트 입력창 자리에 실시간 자막, 제출 버튼 자리에 녹음 버튼이 들어간다. 면접관 표시, 남은 시간, 질문 텍스트 표시 토글, 종료 확인 모달, 근거 확인 배너는 그대로다.

- 질문 번호: 꼬리질문을 포함한 턴 번호와 전체 턴 수 9(`totalTurns`)를 쓴다([0007](../../shared/decisions/0007-voice-interview-contract.md) 결정 6). 예: 2턴이 메인 질문이면 `질문 2 / 9`, 이어지는 꼬리질문은 `질문 3 / 9 · 꼬리질문 1`, `질문 4 / 9 · 꼬리질문 2`. 메인 질문 수와 꼬리질문 총수는 진행에 따라 달라져 표시하지 않는다.
- 다시 듣기 버튼은 두지 않는다. 화면 옆 빈 공간에 팁을 상시 표시하고, 좁은 화면에서는 질문 영역 아래로 내린다.
  > **Tip** 질문을 다시 들으려면 면접관에게 다시 들려달라고 답변하셔도 좋아요.
- 자막: 확정 부분은 검은 글자, 임시 전사(`transcriptPartial`)는 회색. 최종 전사로 교체한 뒤 "최종 전사로 평가해요"를 붙인다.

## 턴 상태

```
듣기 ──답변 시작──▶ 녹음 ──답변 끝내기/180초──▶ 전사 중 ──transcript──▶ 제출 완료 ──question──▶ 다음 턴 듣기
  ▲                  │                          │
  └──── 실패 ◀───────┴──────────────────────────┘
```

| 상태 | 질문 영역 | 자막 영역 | 버튼 |
| --- | --- | --- | --- |
| 듣기 | 재생 중 🔊. 질문 텍스트는 표시 설정을 켰거나 음성 실패 시만 | "답변 시작을 누르고 말해주세요" | `답변 시작`. 질문 음성 재생 중에도 누를 수 있고 누르면 재생을 멈춘다 |
| 녹음 | 같음 | 실시간 자막 + 레벨 바 + `0:42 / 3:00` | `답변 끝내기` (빨강) |
| 전사 중 | 같음 | 마지막 자막을 흐리게 + "답변을 정리하고 있어요…" | 없음 |
| 제출 완료 | 같음 | 최종 전사 | 없음. 기존 `thinking`·`evidenceCheck` 표시 |
| 실패 | 같음 | 원인별 안내 | `다시 답변하기` → 같은 턴의 듣기 |

같은 턴의 `question`이 다시 오면(다시 듣기) 어느 상태든 그 턴의 듣기로 돌아가 질문 음성을 처음부터 재생한다.

실패 안내

| 원인 | 판단 | 안내 |
| --- | --- | --- |
| 녹음·전사 중 WS 끊김 | FE | 연결이 끊겨 답변이 저장되지 않았어요 · 다시 답변해주세요 |
| `stt_failed` | 서버 | 음성을 글로 바꾸지 못했어요 · 다시 답변해주세요 |
| `stt_failed` + `empty_transcript` | 서버 | 목소리가 인식되지 않았어요 · 마이크를 확인하고 다시 답변해주세요 |
| 녹음 중 마이크 트랙 종료 | FE | 마이크 연결이 끊겼어요 · 확인 후 다시 답변해주세요 + 마이크 배지·`다시 확인` |
| `답변 시작` 시 마이크를 열 수 없음 | FE | 녹음 시작 안 함, 마이크 배지·`다시 확인`. 듣기 유지 |

`answerReceived` 전에 끊기면 실패로 본다. 실패해도 남은 시간은 흐른다. 질문 음성 실패(`audioUrl` 없음·재생 오류)는 실패가 아니며 질문 텍스트를 보여 주고 진행한다.

새로고침 복구: `GET /interviews/{id}`의 마지막 턴 `answer`가 `null`이면 듣기, 있으면 제출 완료로 시작한다. 녹음 중 새로고침이었다면 연결 끊김 안내를 함께 띄운다.

## 구성 단위

| 단위 | 역할 |
| --- | --- |
| `useAnswerRecorder` (신규) | 마이크 열기, `MediaRecorder` 250ms 조각을 `onChunk`로 전달, 레벨, 180초 자동 종료, 트랙 종료 시 `onMicLost`. 레벨 계산·오류 구분은 `useMicCheck`의 것을 재사용 |
| `useQuestionAudio` (신규) | `<audio>` 하나로 `audioUrl` 재생·정지. `null`·재생 오류면 `failed` |
| `useInterviewSocket` (수정) | 바이너리 전송 추가. 끊긴 동안 텍스트 메시지는 기존처럼 대기열에 두고, **오디오 조각은 버린다** |
| `InterviewScreen` (수정) | 턴 상태·자막·실패 안내 조립. 텍스트 초안·재전송 로직 제거, `answerReceived` 확인 로직 유지 |
| `types/api.ts` (수정) | 0007 메시지, `AnswerMode = 'voice'` |

녹음 형식은 `audio/webm;codecs=opus`를 우선하고, 지원하지 않는 브라우저는 그 브라우저의 기본 형식을 `mimeType`에 담는다.

### `feature/interview-voice-check` 의존

- 준비 화면에서 고른 마이크를 진행 화면에서 쓰도록 장치 id를 `localStorage`의 `devon.micDeviceId`에 저장한다(`devon.showQuestionText`와 같은 방식).
- 마이크 상태 문구(`MIC_BADGE`)를 두 화면이 함께 쓰도록 `useMicCheck.ts` 옆으로 옮긴다.
- 두 작업은 그 브랜치가 develop에 병합된 뒤 rebase하고 진행한다. 그 전에는 타입·mock·소켓·질문 음성부터 진행한다.

## MSW mock

- WS: `answerStart`·오디오 조각·`answerEnd`를 받는다. 수신 중 약 1초마다 준비된 문장을 `transcriptPartial`로 늘려 보내고, 종료 시 `transcript`를 보낸 뒤 기존 흐름(`answerReceived` → `thinking` → `question`)을 잇는다. `question`에 `mainIndex`·`followUpDepth`·`audioUrl`을 넣는다.
- `question-audio`: 코드로 만든 짧은 WAV를 응답한다. 저장소에 오디오 파일을 넣지 않는다.
- 시나리오 추가(`scenarios.ts`): `ws-stt-failed`, `tts-unavailable`(question-audio 500), `no-partial`(임시 전사 없음), `ws-repeat-request`(다음 답변을 다시 듣기 요청으로 보고 "다시 한 번 말씀해 주시겠어요?"를 전사한 뒤 같은 턴의 `question`을 다시 보냄). 다시 듣기 판단은 mock에서 이 시나리오로만 흉내 내며 AI 판단 규칙을 정하지 않는다.

## 검증

Playwright + MSW. `getUserMedia`는 기존 테스트처럼 바꿔 끼운다. 결과는 mock 기준이며 실제 STT·TTS·BE 연동을 검증하지 않는다.

| 시나리오 | 확인 |
| --- | --- |
| 정상 한 턴 | 질문 수신 → 재생 → `답변 시작` → 서버가 `answerStart`·조각·`answerEnd` 수신 → 회색 자막 → 최종 전사 → 다음 질문 |
| `no-partial` | 녹음 중 자막 없이 "전사 중…" → 최종 전사 |
| `tts-unavailable` | 질문 텍스트 표시를 꺼도 질문 텍스트가 보이고 답변은 정상 진행 |
| `stt_failed` / `empty_transcript` | 원인별 안내, `다시 답변하기` 후 같은 턴으로 `answerStart` |
| 녹음 중 WS 끊김 | 실패 안내, 재연결 후 같은 턴 재답변 |
| 녹음 중 마이크 끊김 | 실패 안내·`다시 확인`, 녹음·마이크 해제 |
| 180초 | 시계 진행 후 `answerEnd` 자동 전송 |
| 다시 듣기 | 같은 턴 `question` 재수신 시 듣기 상태·재생 재시작 |
| 꼬리질문 표시 | 턴 번호 기준 `질문 4 / 9 · 꼬리질문 2`, 9턴째 응답 뒤 종료 |
| 새로고침 복구 | 마지막 턴 `answer` 유무로 듣기·제출 완료 |
| 화면 이탈 | 마이크·오디오 해제 |

수동 확인: 실제 마이크로 레벨 바·mock 자막, Chrome·Edge·Firefox의 `MediaRecorder.mimeType` 기록(Safari는 환경이 있을 때).

검증 명령: `npm run lint`, `npm run build`, `npm test`(frontend), `python3 .claude/scripts/check_contracts.py`(루트).
