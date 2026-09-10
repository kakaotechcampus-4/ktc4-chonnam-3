# FE 검토 필요 사항

작성일: 2026-09-10

이 문서는 백엔드가 임의로 확정하지 않고 FE 결정이 필요한 항목만 모은다. 전체 변경/확정 기록은 `report.md`를 본다.

## 1. 면접 WS 식별자

결정 필요:

```text
WS를 /ws/interviews/{interviewId}로 붙일지,
별도 sessionId를 발급해서 /ws/interviews/{sessionId}로 붙일지
```

현재 백엔드 가능안:

- `interviewId` 통일: 라우팅/복구 단순, Redis lock은 `ws:lock:{interviewId}`.
- `sessionId` 유지: 실시간 연결 단위 분리, Redis 매핑 `rt:{sessionId} -> interviewId, userId` 필요.

FE가 확인할 지점:

- `/interview/:id/prepare`, `/interview/:id/session`, `/interview/:id/report`의 `:id` 의미.
- 새로고침 후 `GET /interviews/{id}`로 WS 재연결 정보를 다시 받을지.
- `already_connected` 처리 UX.

## 2. 텍스트 WS의 `questionEnd`

Sprint 1은 텍스트-only로 확정됐다.

기본 서버 메시지:

- `answerReceived`
- `thinking`
- `evidenceCheck`
- `question`
- `interviewEnd`
- `error`

결정 필요:

```text
텍스트 질문에도 questionEnd 이벤트를 유지할지 제거할지
```

Sprint 2 음성/TTS 스트리밍에서는 `questionEnd`가 다시 필요할 수 있다.

## 3. 이탈/복구/abandoned 판정

결정 필요:

- WS `disconnect`만으로 `abandoned` 처리할지.
- heartbeat/lock 만료 후 자동 abandoned 처리할지.
- 사용자가 새로고침 후 돌아왔을 때 복구할 수 있는 상태 범위.
- `abandoned_at_turn` 기록 기준.
- Sprint 1에 주기 job을 넣을지 Sprint 2로 미룰지.

백엔드 현재 보류:

- `interview_abandoned` 이벤트도 이 결정 전까지 보류.

## 4. DEVON JWT 전달 방식

확정된 점:

- GitHub access token은 FE에 노출하지 않는다.
- BE가 GitHub token을 암호화 저장하고 GitHub API를 대행한다.
- DEVON API 인증에는 BE가 만든 자체 JWT를 쓴다.

결정 필요:

```text
DEVON JWT를 HttpOnly cookie에만 둘지,
응답 body에도 내려줄지
```

함께 결정할 것:

- FE `credentials: include` 강제 여부.
- DEVON JWT refresh를 둘지 여부. GitHub OAuth refresh token은 현재 사용하지 않는다.
- CSRF 대응 범위.

## 5. Portfolio GitHub URL 매칭 실패 노출

백엔드가 내부적으로 저장할 값:

- `mentionedRepoCount`
- `matchedRepoCount`
- unmatched URL 정규화 결과 또는 내부 로그

결정 필요:

- 사용자에게 개수만 보여줄지.
- 상세 URL을 보여줄지.
- 기본 UI에서는 숨길지.

개인 문서 안의 외부 repo URL이 그대로 노출될 수 있어 FE UX/개인정보 관점 결정이 필요하다.

## 6. `preparing_failed` 표시

백엔드는 준비 실패를 `abandoned`와 분리하기 위해 DB status `preparing_failed`를 둔다.

결정 필요:

- FE `InterviewStatus`에 `preparing_failed`를 추가할지.
- 기존 실패 화면 reason으로만 처리할지.
- 준비 실패 후 재시도 버튼/뒤로가기 UX를 어떻게 둘지.
