# task-10 — interview 구현 (Sprint 1, 텍스트)

> 필요: task-07 (`shared/api.ts`, 인증 가드, 재연동 배너)
> 근거: `spec/frontend/features/interview.md`

## 목표

WebSocket 기반 텍스트 면접 준비~진행 화면을 구현한다. 음성(Sprint 2)은 범위 밖이다.

2026-09-22 로컬의 `InterviewPrepare.tsx`·`InterviewScreen.tsx`는 빈 화면 골격이다. 열린 PR #33/#34의 구현은 미병합 작업이므로 로컬 완료와 구분한다. 아래 항목은 구현·연결·검증 대기이며 문서 정리만으로 완료 처리하지 않는다.

## 작업

- WS 클라이언트 모듈 (연결·재연결·메시지 파싱) — 연결 URL에 `/api` 프리픽스 직접 포함 (`shared/api.ts` 래퍼를 안 거침, `spec/frontend/architecture.md` "`/api` 프리픽스" 참고)
- 세션 상태 store (라이브러리 미확정 — store 또는 Context + reducer)
- 5a2-v2 준비 체크리스트 4단계
- 면접 준비 실패 화면
- 면접 준비 실패 `다시 시도`는 `POST /interviews/{id}/prepare/retry` REST 호출
- 답변 입력창 (최대 2000자) + 제출 버튼
- `answer` 전송(`turn`, `text`) → `answerReceived` 수신까지 제출 중 상태 유지, 다음 `question`까지 입력창 잠금
- `error.reason` 9종 분기 (Sprint 1 목록) + `recoverable` 처리
- `status === 'preparing_failed'` 복구: `GET /interviews/{id}`의 `lastError`로 WS 재연결 없이 면접 준비 실패 배너 렌더
- `onclose` 재연결 순서 (GET으로 로그인 세션·turns 확인 → 화면 상태 복구 → WS 재연결). `401 unauthenticated`는 refresh 없이 캐시 정리·로그인 이동
- `turns` 복구 렌더링
- `remainingSeconds` 타이머 + 서버값 덮어쓰기
- `evidenceCheck` 배너 + 30초 타임아웃
  - 30초 타이머는 상태로 두지 않고 `useRef` + `setTimeout`으로 관리한다. 다른 서버 메시지 수신 시 타이머를 clear한다
- 이탈 확인 모달
- `GET /interviews/{id}` 응답의 `answerMode`로 분기하는 구조로 작성한다 (Sprint 1은 항상 `text`지만 Sprint 2에서 `voice` 추가 시 이 값 무시하지 않게)

Sprint 2 대상이라 이번에 만들지 않는 것: 마이크·스피커 점검 섹션, `MediaRecorder` 녹음, `answerStart`/오디오 바이너리/`answerEnd`, `transcript` 표시, TTS 재생, `stt_failed`/`tts_failed` 처리.

## 완료 조건

- [ ] WS 클라이언트 모듈 (연결·재연결·메시지 파싱)
- [ ] 세션 상태 store
- [ ] 5a2-v2 준비 체크리스트 4단계
- [ ] 면접 준비 실패 화면
- [ ] `POST /interviews/{id}/prepare/retry` 호출
- [ ] 답변 입력창 (2000자 제한) + 제출
- [ ] `answer` 전송(`turn`, `text`) → `answerReceived` 제출 상태 해제, 다음 `question`까지 입력 잠금
- [ ] `error.reason` 9종 분기 + `recoverable` 처리
- [ ] `preparing_failed` 새로고침 복구 — `lastError`만으로 면접 준비 실패 배너 렌더
- [ ] `onclose` 재연결 순서 (GET → 상태 복구 → 재연결); 세션 만료·유실은 로그인 이동
- [ ] `turns` 복구 렌더링
- [ ] `remainingSeconds` 타이머 + 서버값 덮어쓰기
- [ ] `evidenceCheck` 배너 + 30초 타임아웃
- [ ] 이탈 확인 모달
- [ ] `npm run build` 통과
- [ ] `npm run lint` 통과

## 커밋

```
feat: add text-based interview preparation and session screens
```
