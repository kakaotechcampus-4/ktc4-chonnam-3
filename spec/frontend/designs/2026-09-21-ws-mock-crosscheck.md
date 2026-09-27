# WS 목 ↔ 면접 화면 교차 검증

- 상태: Proposed
- 작성일: 2026-09-21
- 대상: PR #46(`feature/msw-failure-and-ws`) × PR #33·#34(`feature/interview-prepare`, `feature/interview-screen`)
- 검증 브랜치: `feature/ws-mock-crosscheck`
- 참조: `frontend/docs/api-spec.md` #18, `spec/frontend/designs/2026-09-21-ws-mock.md`

## 왜 했나

WS 목과 면접 화면이 **서로 모르는 채로 같은 주에 각각 만들어졌다.**
목은 계약 문서만 보고, 화면은 계약 문서만 보고 구현했다.
둘이 실제로 맞물리는지는 합쳐서 돌려보기 전에는 알 수 없다.

두 브랜치를 한 브랜치에 합치고 브라우저에서 화면을 직접 조작해 확인했다.

## 먼저 — 회의 안건의 전제 정정

> "MSW에 WS 목이 없다 … MSW는 ws 링크 핸들러를 지원하니 추가 가능"

**PR #46에 이미 있다.** `frontend/src/mocks/ws/`(4파일, msw `ws.link()` 기반)이고 9/21에 올렸다.
안건이 본 `frontend/src/mocks/` 목록은 develop 기준이라 아직 반영되지 않은 상태다.

따라서 오늘 논할 것은 "WS 목을 만들지"가 아니라 **"만들어진 목과 화면이 맞는지, 어느 순서로 머지할지"**다.

## 합친 결과

충돌은 `frontend/src/types/api.ts` **한 곳**뿐이었다. 두 브랜치가 각각 WS 메시지 타입을 계약에 맞게 고쳤기 때문이다.

`types/contract.ts`는 되살아나지 않았고(refactor/mocks의 삭제가 유지됨) 목 핸들러도 자동 병합됐다.

## 독립적으로 일치한 것

양쪽이 서로를 참조하지 않고 같은 결론에 도달했다. 계약 문서가 제 역할을 했다는 뜻이다.

| 항목 | WS 목 | 면접 화면 | 결과 |
| --- | --- | --- | --- |
| 클라이언트 메시지 | `prepareRetry` · `answer{text}` | 동일 | 일치 |
| 서버 메시지 8종 | `prepareStep`·`prepareCompleted`·`answerReceived`·`thinking`·`evidenceCheck`·`question`·`interviewEnd`·`error` | 동일 | 일치 |
| `error` 필드 | `reason`·`code`·`step`·`recoverable`·`occurredAt` | 동일 | 일치 |
| WS 경로 | `${BASE}/ws/interviews/{sessionId}` | `api.interviewSocketUrl` 동일 | **일치 — D9 해소** |
| 준비 4단계 순서 | `analyze_repo`→`build_persona`→`set_criteria`→`compose_question` | 동일 | 일치 |
| `answer`에 turn 미포함 | 서버가 "현재 턴"에 저장 | 훅 주석에 같은 전제 | 일치 |

`types/api.ts` 충돌은 `error`를 `WsErrorMessage = { type: 'error' } & InterviewLastError` 별칭으로 남겨 해소했다.
WS 오류와 조회 스냅샷의 `lastError`는 같은 정보이므로 타입으로 묶어 두면 한쪽만 바뀌는 사고를 막는다.

## 발견한 불일치 — D14

**준비 실패 세션에 WS가 연결될 때 서버가 오류를 다시 보내면 재시도가 끝나도 실패 배너가 남는다.**

재현 경로:

1. 화면은 `preparing_failed`를 **REST 스냅샷**(`lastError`)으로 그린다. WS는 열지 않는다.
   (`enabled: status === 'preparing' || (status === 'preparing_failed' && retried)`)
2. "다시 시도"를 누르면 `setError(null)` 후 비로소 WS를 연다.
3. 목이 연결 시점에 `error`를 되보낸다 → 화면이 방금 지운 오류가 되살아난다.
4. `prepareRetry`가 처리돼 `prepareCompleted`가 와도, 오류를 지우는 코드가 없어 배너가 남는다.

화면에서 실제로 재현했다. 체크리스트는 "첫 질문 구성 완료"로 바뀌는데 실패 배너와 "다시 시도" 버튼이 그대로 남았다.

**조치** — 목에서 연결 시 오류 재전송을 제거했다. 계약의 복구 경로가 REST 스냅샷이고(#18),
이 연결은 `prepareRetry`를 받기 위한 것이므로 상태를 되밀 이유가 없다.

**팀 결정이 필요하다.** 실서버가 같은 순서로 보내면 화면은 똑같이 막힌다.

- (a) 서버는 재연결한 클라이언트에 `lastError`를 다시 보내지 않는다 — 지금 목의 동작
- (b) 화면이 새 시도의 첫 `prepareStep`에서 `error`를 비운다 — 방어적으로 함께 하는 편이 안전하다

(a)만 하면 스냅샷 없이 붙은 클라이언트는 실패 사유를 못 본다. (b)만 하면 서버 구현에 순서 제약이 남는다.
둘 다 하는 것을 제안한다.

## 화면으로 확인한 동작

브라우저에서 실제 화면을 조작해 확인했다.

| # | 시나리오 | 결과 |
| --- | --- | --- |
| C1 | 면접 생성 → 준비 화면 진입 → 4단계 진행 | "레포 · JD 분석 중" → 4개 모두 "완료" |
| C2 | `prepareCompleted` 후 "면접 시작하기" 활성화 → 진행 화면 이동 | 통과 |
| C3 | 진행 화면 첫 질문 | "질문 1 · 인사팀", 잔여 14:33, 0/2000 |
| C4 | 답변 제출 → 다음 질문 | `answerReceived` → "다음 질문을 만들고 있어요" → "질문 2 · 개발팀" |
| C5 | `evidenceCheck` 배너 | "근거 확인 중 · payment-service / CacheConfig.java" |
| C6 | 준비 실패 seed 진입 | "첫 질문을 준비하지 못했어요" + ✓✓✓! 체크리스트 + `ERR_QUESTION_GEN_TIMEOUT` · `occurredAt` |
| C7 | "다시 시도" | **D14 수정 전: 배너 잔존 / 수정 후: 배너 해제 → "첫 질문 구성 중" → "완료" → "면접 시작하기"** |
| C8 | `ws-repo-unreachable`(`recoverable: false`) | "선택한 레포에 접근할 수 없어요" + `ERR_REPO_UNREACHABLE`, "다시 시도" 버튼 없이 "레포 다시 선택하기"만 |

C6의 제목은 `FAILURE_TITLE[error.reason]` 조회 결과다.
PR #46에서 seed `lastError.reason`을 한국어 문장에서 `question_gen_timeout`으로 고치지 않았다면 이 제목은 나오지 않았다.

C8은 목의 `CLOSE_GRACE_MS`(오류 전송 후 50ms 뒤 종료)가 없으면 성립하지 않는다.
훅이 `recoverable: false`를 봐야 `sessionClosedRef`를 세워 재연결을 멈추는데, 같은 틱에 닫으면 그 메시지를 받지 못하고 2초마다 영원히 재연결한다.

## 남은 위험

| # | 항목 | 내용 |
| --- | --- | --- |
| R1 | 머지 순서 | PR #33·#34는 `00524cd` 기준이라 develop보다 17커밋 뒤에 있다. 먼저 develop을 받아 충돌을 화면 담당자가 확인하는 편이 안전하다 |
| R2 | `ANSWER_MAX_LENGTH` 중복 | 화면(`InterviewScreen.tsx`)과 목(`ws/protocol.ts`)에 2000이 각각 있다. 계약 값이므로 한 곳에 두어야 한다 |
| R3 | 목 db 초기화 | 새로고침하면 진행 중 면접이 사라진다. 화면을 URL로 직접 열어 테스트하려면 seed가 필요하다. 지금 seed에는 `preparing` 상태가 없다(시간 기반이라 즉시 `in_progress`가 된다) |
| R4 | 핸드셰이크 인증 | 목은 쿠키 검증을 재현하지 않는다. 401·409는 실서버에서 처음 검증된다 |

## 검증

| 항목 | 결과 |
| --- | --- |
| `npx tsc -b --force` · `npm run lint` | 통과 |
| 스모크 스크립트 | 86건 PASS / 0 FAIL |
| 화면 시나리오 C1~C8 | 통과 (C7은 D14 수정 후) |

미실행: 자동화 테스트, 핸드셰이크 인증, 동시 접속, 실서버 연동.

## 제안

1. **PR #46을 먼저 머지한다.** 화면 브랜치가 목 위에서 검증된 상태가 된다.
2. PR #33·#34는 develop을 받아 `types/api.ts` 충돌을 해소한다. 해소안은 이 브랜치에 있다.
3. D14를 (a)+(b)로 확정하고 `api-spec.md` #18에 재연결 시 서버 동작을 한 줄 명시한다.
4. R2를 정리한다.
