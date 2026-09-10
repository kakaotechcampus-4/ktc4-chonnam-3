\# 회의 내용



> 잡담 뺴고 다 적기

> 



\# \*\*FE 역할 분담 · 주차별 일정 · 위험 요소\*\*



> 작성일: 2026-09-01

> 

> 

> 프로젝트: DEVON — 개발자 음성 모의면접 서비스

> 

> 기간: W4\~W13 · 3 스프린트 · 프론트엔드 3명

> 

> 개발 사이클: 수요일 PR 제출 → 목·금 리뷰(동시에 다음 작업 진행) → 토요일 수정·머지

> 

> 관련: DEVON 프론트엔드 기술 기획서 · DEVON 인터페이스 명세

> 



\---



\## 1. 분담 기준



| 기준 | 내용 |

| --- | --- |

| 난이도 기준 분할 | 화면 수가 아니라 공수로 나눔. 5b-v2 하나가 나머지 9개를 합친 난이도 |

| 5b-v2는 층으로 3인 분할 | 통신 / 상태 / 화면 — 파일이 겹치지 않아 병렬 가능 |

| 역할 고정하지 않음 | 단일 실패점 방지 + 세 명 모두 실시간·오디오 경험 |

| 충돌 최소화 | W5에 공통 파일 완성·동결 → 이후 각자 폴더에서만 작업 |



\---



\## 2. 폴더 구조 · 소유



\### 구조 원칙 — 기능별 분리



파일을 종류(components / hooks / pages)로 나누지 않고 \*\*화면 기능 단위\*\*로 묶는다.



> 채택 근거: 화면 10개 · 3인 협업 규모에서는 기능별이 물리적 격리를 만들어 충돌을 원천 차단한다.

> 

> 

> 

> |  | 종류별 | 기능별 (채택) |

> | --- | --- | --- |

> | 화면 하나 작업 시 | 3개 폴더를 오감 | 폴더 1개 |

> | 3인 동시 작업 | 전원이 같은 3개 폴더를 만짐 | 각자 자기 폴더만 |

> | 화면 삭제 시 | 여러 폴더에서 찾아 지움 | 폴더 하나 삭제 |



\### 폴더 소유



```

src/

&#x20; features/

&#x20;   auth/          B          1 로그인

&#x20;   home/          B          3b 홈(빈 상태) · 3 홈 대시보드

&#x20;   mypage/        C          7 마이페이지

&#x20;   analysis/      B · C      B: 4-2-v2, 4-3-v2 / C: 4-v2, 5a-v2

&#x20;   report/        C          5c-v2 면접 리포트

&#x20;   interview/     3인 공동    5b-v2 면접 진행 (W7\~W10, 내부 층 분리)

&#x20; shared/          A가 W5 구축 → 이후 공동, PR 리뷰로 통제

&#x20; routes.tsx       W5 동결 후 변경 없음

```



`analysis/`만 두 사람이 나눠 쓰지만 \*\*파일이 화면별로 다르므로\*\* 충돌 위험은 낮다.



```

features/analysis/

&#x20; JobInput.tsx        C   4-v2

&#x20; RepoSelect.tsx      C   5a-v2

&#x20; Analyzing.tsx       B   4-2-v2

&#x20; AnalysisFailed.tsx  B   4-3-v2

```



\### 파일을 어디에 둘지 판단



| 질문 | 위치 |

| --- | --- |

| 이 화면만 쓰나 | 그 화면 폴더 |

| 여러 화면이 쓰나 | `shared/` |



처음엔 화면 폴더에 두고, 다른 화면에서도 필요해지면 그때 `shared/`로 옮긴다. 미리 공통화하면 실제로 쓰이지 않는 추상화가 쌓인다.



\---



\## 3. shared/ 주의사항



`features/`는 담당자별로 격리되지만 \*\*`shared/`는 세 명이 모두 만지는 유일한 지점\*\*이다. 여기만 규칙이 필요하다.



```

shared/

&#x20; api.ts              W5에 20개 함수 완성 → 동결

&#x20; queryKeys.ts        W5에 전부 완성 → 동결

&#x20; components/         계속 추가됨 ← 유일한 충돌 지점

&#x20;   Button.tsx

&#x20;   Card.tsx

&#x20;   ErrorBanner.tsx

```



\### 동결 대상 — W5에 완성 후 변경 없음



| 파일 | 미리 만들 수 있는 근거 |

| --- | --- |

| `api.ts` | 엔드포인트 20개가 명세에 확정 |

| `queryKeys.ts` | 위와 동일 |

| `routes.tsx` | 화면 10개가 확정 → 빈 컴포넌트로 미리 등록 |

| `tailwind.config.js` | 프로토타입 문서에 색·radius 값 존재 |

| `types/api.ts` | W4에 3인 공동 작성 |



`credentials: 'include'`는 `api.ts` 한 곳에만



각자 `fetch`를 직접 쓰면 누군가는 빠뜨리고, 그게 W8 로그인 통합 때 전 화면 401로 터진다.



\### barrel export 금지



```tsx

// ❌ 셋이 이 파일에서 매번 충돌

// shared/components/index.ts

export { Button } from './Button';

export { Card } from './Card';



// ✅ import 경로 직접 — 새 컴포넌트는 새 파일 생성이라 충돌 없음

import { Button } from '@/shared/components/Button';

```



\### 규칙



| 항목 | 내용 |

| --- | --- |

| 파일 하나에 컴포넌트 하나 | `Button.tsx`, `Card.tsx` |

| `index.ts` barrel export | \*\*금지\*\* |

| import 경로 | 직접 지정 (`@/shared/components/Button`) |

| `api.ts` · `queryKeys.ts` 변경 | W5 이후엔 별도 PR로 분리 — 영향 범위가 넓어 리뷰 우선순위가 다름 |

| 토요일 머지 순서 | `shared/` 포함 PR을 \*\*먼저\*\* 머지 |



\---



\## 4. interview 폴더 — 층 분리



5b-v2 하나에 통신·상태·화면이 몰려 있어 한 명이 하기엔 크고, 셋이 나누면 충돌한다. \*\*데이터가 흐르는 방향으로 3층으로 자른다.\*\*



```

서버 (WebSocket)

&#x20;  ↓

A  통신·미디어 층    서버와 대화, 마이크·스피커

&#x20;  ↓  상태를 내보냄

B  상태 층           화면이 쓰기 좋은 형태로 가공

&#x20;  ↓  상태를 내보냄

C  화면 층           받아서 그림

```



\### 파일 소유



```

features/interview/

&#x20; types.ts                  계약 — W7 페어 세션에서 확정, 변경 시 3인 합의

&#x20; useInterviewSocket.ts     A   WS 연결 · 메시지 송수신 · 재연결

&#x20; useAudioRecorder.ts       A   마이크 녹음 → 오디오 Blob

&#x20; useTTSPlayer.ts           A   TTS 오디오 재생

&#x20; interviewStore.ts         B   A의 결과를 화면용 상태로 가공

&#x20; InterviewScreen.tsx       C   전체 레이아웃

&#x20; InterviewerAvatar.tsx     C   면접관 3명 · 발언 중 강조

&#x20; Caption.tsx               C   자막 표시 · 토글

```



\*\*파일이 전부 다르므로 셋이 같은 폴더에서 동시에 작업해도 Git 충돌이 없다.\*\*



\### types.ts가 계약인 이유



세 명이 공유하는 유일한 파일. 이것이 확정되면 각자 독립적으로 개발할 수 있다.



```tsx

export type InterviewPhase = 'idle' | 'recording' | 'processing' | 'speaking';

export type InterviewerRole = 'tech\_lead' | 'senior\_dev' | 'manager';



export type InterviewState = {

&#x20; phase: InterviewPhase;

&#x20; currentSpeaker: InterviewerRole | null;

&#x20; caption: string | null;

&#x20; remainingSec: number;

&#x20; connectionStatus: 'connected' | 'reconnecting' | 'failed';

&#x20; captionEnabled: boolean;

};

```



| 담당 | 이 타입으로 할 수 있는 것 |

| --- | --- |

| A | 이 상태를 만들어내는 통신 로직 |

| B | 이 형태로 가공하는 스토어 |

| C | \*\*이 타입만 보고 화면 개발\*\* — A·B가 없어도 목업 상태로 가능 |



C가 가장 큰 이득을 본다. WebSocket이 없어도 `phase: 'speaking'`을 하드코딩해 화면을 만들 수 있다.



\### W7 페어 세션이 필요한 이유



한 명이 `types.ts`를 정하면 나중에 안 맞는다. 층마다 필요한 필드가 다르기 때문이다.



| 관점 | 필요한 필드 |

| --- | --- |

| A (통신) | `connectionStatus`, `turn` |

| B (상태) | `phase` — 전이 관리 |

| C (화면) | `currentSpeaker`, `caption`, `remainingSec` |



페어 세션을 건너뛰면 W8에 재작업



"화면에 표시할 게 상태에 없다"는 문제가 나온다. 셋이 앉아 필요한 필드를 다 꺼내놓고 한 번에 정의한다.



`types.ts`는 페어 세션 직후 단독 PR로 즉시 머지



이유는 리뷰가 막기 때문이 아니라, \*\*B·C가 의존하는 파일이 `main`에 없으면 A의 브랜치 위에 자기 브랜치를 쌓아야 하기 때문\*\*이다. 토요일에 A의 PR이 리뷰로 수정되면 B·C 작업도 함께 흔들린다.



\### W12 로테이션의 기반



층이 파일로 갈려 있으므로 인수인계가 "이 파일들을 맡아라"로 끝난다.



| 시기 | A | B | C |

| --- | --- | --- | --- |

| W7\~W10 | 통신 파일 | 상태 파일 | 화면 파일 |

| W12 | 화면 파일 | 통신 파일 | 상태 파일 |



층이 안 나뉘어 있으면 코드가 뒤섞여 로테이션 자체가 불가능하다.



\---



\## 5. 전체 일정



| 주차 | 스프린트 | A | B | C | 마일스톤 |

| --- | --- | --- | --- | --- | --- |

| W4 | — | 기술 기획 · 명세 확정 | 기술 기획 | 기술 기획 | 네이밍 규칙(기술 멘토링 후→ camel 확정됨) · 타입 정의 확정 |

| W5 | 1 | \*\*공통 파일 전부 구축·동결\*\* — 래퍼 · MSW · Query · queryKeys · routes · Tailwind · 배포 파이프라인 | 3b 홈(카카오 로그인 없으므로 구현 안해도됨) · 3 홈(대시보드 레이아웃 포함) | 7 마이페이지 · 4-v2 공고 입력 | — |

| W6 | 1 | \*\*음성 spike\*\* — WS 프로토콜 · 오디오 형식 · 지연 실측 | 4-2-v2 (화면만) · 4-3-v2 | 5a-v2 레포 선택 · 5c-v2 리포트 | 테스트 세션 쿠키 요청 |

| W7 | 1 | 5b-v2 \*\*통신\*\* — WS 연결·메시지 | 5b-v2 \*\*상태\*\* — 스토어 | 5b-v2 \*\*화면\*\* — 아바타 | \*\*v0.1 배포\*\* · 페어 세션(첫 이틀) |

| W8 | 2 | 5b-v2 \*\*오디오 캡처·전송 · TTS 재생\*\* | \*\*1 로그인(소셜 OAuth)\*\* · 인증 상태 관리 | 3 홈 대시보드 데이터 연결 · 마이크 UI | \*\*인증 통합\*\* |

| W9 | 2 | 5b-v2 재연결 · 상태 복구 · 마이크 차단 | 4-2-v2 \*\*SSE 로직\*\* · 폴백 | 7 실연동 · 4-3-v2 분기 완성 | — |

| W10 | 2 | 실시간 실패 처리 · 통합 | 실패 케이스 UI 전면 · 통합 | 실패 UI · 통합 | \*\*v0.2 배포 · 전 기능 완성\*\* |

| W11 | 3 | 중간고사 — 최소 | 중간고사 — 최소 | 중간고사 — 최소 | — |

| W12 | 3 | 음성 실연동 · 보완 | 음성 실연동 · 보완 | 음성 실연동 · 보완 | — |

| W13 | 3 | 통합 | 통합 | 통합 | \*\*v1.0 최종 배포\*\* |



\---



\## 6. 화면 완성 시점



| 화면 | 화면 구성 | 기능 완성 |

| --- | --- | --- |

| 3b 홈(빈 상태) | W5 | W5 |

| 3 홈 대시보드 | W5 (레이아웃) | W8 (데이터 연결) |

| 7 마이페이지 | W5 | W9 (실연동) |

| 4-v2 공고 입력 | W5 | W5 |

| 4-2-v2 분석 중 | W6 (정적) | W9 (SSE) |

| 4-3-v2 분석 실패 | W6 | W9 (분기 완성) |

| 5a-v2 레포 선택 | W6 | W6 |

| 5c-v2 면접 리포트 | W6 | W6 |

| \*\*5b-v2 면접 진행\*\* | W7 | \*\*W7\~W10\*\* |

| 1 로그인 | W8 | W8 |



\---



\## 7. 배포 마일스톤



| 배포 | 시점 | 상태 |

| --- | --- | --- |

| v0.1 | W7 | 화면 9개 클릭 완주 · 로그인 없음(고정 사용자) · 5b-v2 오디오 미구현 |

| v0.2 | W10 | 전 화면·전 기능 완성 · 음성은 BE·AI 완성 시점에 따라 Mock 가능 |

| v1.0 | W13 | 음성 실연동 완료 |



\### v0.1 릴리즈 노트에 명시할 것



| 항목 | 상태 |

| --- | --- |

| 로그인 | 미구현 — 고정 사용자 진입 |

| 3 홈 대시보드 | 분석 패널 미구현 |

| 면접 진행 | WS 통신까지. \*\*오디오 미구현\*\* |



적어두지 않으면 보는 사람이 고장으로 판단한다.



\---



\## 8. 주차별 위험 요소



\### W5 — 인프라 병목



| 위험 | 영향 | 대응 |

| --- | --- | --- |

| \*\*공통 파일이 수요일까지 `main`에 없음\*\* | B·C가 이틀간 착수 못 함 | 라우팅·Tailwind·타입은 \*\*월요일 단독 PR로 즉시 머지\*\* |

| 라우팅·Tailwind 동시 수정 | 충돌 | routes 10개·토큰 전부를 A가 한 번에 완성·동결 |

| 포매터 설정 불일치 | 파일 전체가 변경으로 표시 → 리뷰 불가 | 첫날에 Prettier·ESLint·`.vscode/settings.json` 커밋 |



W5는 머지 순서가 중요



공통 파일이 `main`에 먼저 들어가야 B·C가 그 위에서 작업할 수 있다. 수요일 사이클을 기다리면 이틀을 낭비한다.



\### W6 — spike 결과 의존



| 위험 | 영향 | 대응 |

| --- | --- | --- |

| \*\*왕복 지연 10초 초과\*\* | 대기 UI만으로 해결 불가, 설계 변경 필요 | 실측 후 리액션 음성 선재생 등 검토 |

| Safari 오디오 코덱 미지원 | 지원 범위 축소 | Chrome 전용 선언 |

| \*\*STT/TTS 오디오 형식 미확정\*\* | W8 오디오 구현이 실제 API와 불일치 | AI 담당자와 실제 API로 검증 |

| BE WS 서버 완성 시점 불명 | W7 통신 구현이 Mock 기반이 됨 | 확인 후 필요 시 Mock WS 서버 구축 |



\### W7 — 5b-v2 3인 동시 작업 (최대 충돌 구간)



| 위험 | 영향 | 대응 |

| --- | --- | --- |

| \*\*층 경계가 안 맞아 재작업\*\* | 통신·상태·화면이 어긋남 | 첫 이틀 페어 세션에서 `types.ts` 완전 확정 |

| \*\*`types.ts`가 `main`에 없어 B·C가 A 브랜치에 종속\*\* | 토요일에 A PR이 수정되면 B·C 작업도 흔들림 | 페어 세션 직후 `types.ts`만 단독 즉시 머지 |

| v0.1 첫 배포 실패 | 배포 주 절반 소모 | W5에 빈 화면으로 배포 경로 미리 뚫어둠 |

| SPA 라우팅 404 | 새로고침 시 화면 안 나옴 | 배포 시 rewrite 설정 확인 |



W7 페어 세션이 이 주의 성패를 결정



파일을 나누기 전에 상태 인터페이스를 함께 확정한다. 건너뛰면 세 층이 어긋나 재작업이 발생한다.



\### W8 — 가장 밀도 높은 주



| 위험 | 영향 | 대응 |

| --- | --- | --- |

| \*\*로그인 통합 시 3주치 문제 폭발\*\* | `credentials` 누락 · CORS · 401 처리 없음 | W7까지 테스트 세션 쿠키로 조기 발견 |

| BE 인증 완성이 주 후반 | FE가 붙일 대상 없이 대기 | BE에 OAuth 리다이렉트·콜백 먼저 요청 |

| OAuth 콜백 URL 미등록 | OAuth가 시작조차 안 됨 | GitHub·\*\*카카오\*\* 콘솔에 로컬 + 배포 주소 등록 |

| 오디오·로그인·대시보드 동시 진행 | 한 명이라도 밀리면 W9 압박 | W10을 버퍼로 확보 |



\### W9 — 실시간 로직 집중



| 위험 | 영향 | 대응 |

| --- | --- | --- |

| SSE가 프록시에서 버퍼링됨 | 4-2-v2 실시간 갱신 안 됨 | 폴링 폴백 필수 구현 |

| \*\*WS 재연결·상태 복구 난이도\*\* | 답변 유실 | `GET /interviews/{id}` 응답 스키마 사전 확정 |

| 5b-v2가 A에게 3주 연속 종속 | 막히면 대체 불가 | 교차 리뷰로 백업 인력 확보 |



\### W10 — 전 기능 완성 마감



| 위험 | 영향 | 대응 |

| --- | --- | --- |

| 실패 케이스를 한 주에 | 누락 발생 | W9에 공통 에러 컴포넌트 선구축 |

| 세 명이 실패 UI를 각자 만듦 | 중복·불일치 | B가 공통 컴포넌트 → 나머지가 적용 |

| 밀린 작업이 W11(중간고사)로 넘어감 | W12·W13 압박 | W10 중반에 범위 자를지 판단 |



\### W11\~W13 — 최종 구간



| 위험 | 영향 | 대응 |

| --- | --- | --- |

| \*\*중간고사로 W11 실질 작업 0\*\* | W12·W13 2주만 남음 | W10까지 기능 완성이 전제 |

| Mock 오디오 형식과 실제 STT 불일치 | W12에 오디오 파이프라인 재작업 | W6에 실제 API로 형식 검증 |

| W12 작업량 예상 초과 | W13 최종 배포 압박 | W12는 신규 구현 없음 원칙 유지 |



\---



\## 9. 범위 자르기 우선순위



밀렸을 때 무엇을 먼저 버릴지 \*\*미리 정해둔다.\*\* .



| 순위 | 항목 | 근거 |

| --- | --- | --- |

| 1 | 4-2-v2 SSE | 폴링만으로도 동작함 |

| 2 | 캡션 토글 | 기본 ON 고정으로 대체 |

| 3 | 7 마이페이지 면접 기록 | 홈에 최근 1건만 노출로 축소 |

| 4 | 피드백 이의 제기 | 리포트 열람에는 영향 없음 |

| \*\*절대 안 자름\*\* | 5b-v2 오디오 · 로그인 · 5c-v2 리포트 | 서비스 핵심 흐름 |



\---



\## 10. 상시 위험 요소



| 위험 | 대응 |

| --- | --- |

| \*\*의존 관계가 있는 작업이 브랜치에 쌓임\*\* | 다른 사람이 필요로 하는 파일(타입·공통 코드)은 단독 PR로 분리해 먼저 머지 |

| 토요일에 3개 브랜치가 동시 머지 | 머지 순서 준수 — `shared/` 포함 PR 먼저 |

| PR이 300줄 초과 | 화면 단위로 쪼갬. `shared/` 변경은 별도 PR |

| 리뷰가 "LGTM"으로 형식화 | 리뷰 체크리스트 사용 (아래) |

| 층 간 필드명 어긋남 (타입 에러 안 남) | `types.ts` 변경 시 슬랙 공유 |

| barrel export(`index.ts`)로 인한 충돌 | 금지 — import 경로 직접 지정 |



\### 리뷰 체크리스트



| 항목 | 확인 |

| --- | --- |

| `credentials: 'include'` | 새 API 호출에 붙었나 |

| queryKey | `queryFn`의 변수가 키에 포함됐나 |

| 실패 처리 | 명세의 해당 화면 실패 케이스가 반영됐나 |

| 캐시 무효화 | 변경 API 후 `invalidateQueries` 호출했나 |

| 하드코딩 | 색·간격을 Tailwind 토큰으로 썼나 |



\---



\## 11. 협업 규칙



| 항목 | 규칙 |

| --- | --- |

| 개발 사이클 | 수 PR 제출 → 목·금 리뷰(동시에 다음 작업 진행) → 토 수정·머지 |

| \*\*사이클 예외\*\* | 다른 사람이 의존하는 파일(`types.ts`, 공통 파일)은 즉시 머지 |



\---



\## 12. 외부 의존 항목



| 항목 | 상대 | 마감 | 미확보 시 영향 |

| --- | --- | --- | --- |

| API 필드 네이밍 규칙 | BE | \*\*W4\*\* | W5 MSW 작성 불가 |

| BE 배포 주소 · API 경로 접두사 | BE | W5 | 배포 rewrite 설정 불가 |

| \*\*STT/TTS 오디오 형식\*\* | AI | \*\*W6\*\* | W8 오디오 구현이 재작업 위험 |

| 테스트용 고정 세션 쿠키 | BE | W6 요청 → W7 수령 | W8에 3주치 문제 폭발 |

| BE WebSocket 서버 완성 시점 | BE | W7 전 | Mock WS 서버 자체 구축 |

| W8 로그인 구현 순서 (OAuth 리다이렉트·콜백 우선) | BE | W7 합의 | W8 전반 대기 |

| GitHub · 카카오 콜백 URL 등록 (로컬 + 배포) | BE | W7 | OAuth 시작 불가 |

| WebSocket 프록시 통과 여부 | 자체 검증 | W7 | 도메인 구성 재설계 |

| 엔드포인트별 예시 JSON | BE | W4\~W5 | MSW가 실제 응답과 어긋남 |



\# 개발 내용



> 파일 이름 명시해서 작성하기

> 



\# 트러블 슈팅



> 사소한 것도 적어보기

>




\## 1. 화면 경로 vs API 경로



두 경로는 \*\*완전히 별개.\*\*



|  | 화면 경로 | API 경로 |

| --- | --- | --- |

| 예 | `/interview/:id/session` | `/ws/interviews/{sessionId}` |

| 결정 주체 | \*\*FE 자유\*\* | BE 구현 (합의 필요) |

| 브라우저 주소창 | 표시됨 | 안 보임 |

| 처리 | React Router | 서버 |



프록시 접두사로 갈린다.



```json

{

&#x20; "rewrites": \[

&#x20;   { "source": "/api/:path\*", "destination": "https://<BE>/:path\*" },

&#x20;   { "source": "/(.\*)", "destination": "/index.html" }

&#x20; ]

}

```



`/api`로 시작하지 않으면 전부 화면 경로로 취급되므로 겹칠 일이 없다.



\---



\## 2. 확정 경로 목록



화면 \*\*10개\*\*



| # | 화면 | 경로 | 컴포넌트 파일 | 담당 |

| --- | --- | --- | --- | --- |

| 1 | 로그인 | `/login` | `features/auth/Login.tsx` | B |

| 3 | 홈 대시보드 | `/home` | `features/home/Home.tsx` | B |

| 7 | 마이페이지 | `/mypage` | `features/mypage/MyPage.tsx` | C |

| 4-v2 | 공고 입력 | `/interview/new` | `features/analysis/JobInput.tsx` | C |

| 4-2-v2 | 분석 중 | `/interview/analyzing/:runId` | `features/analysis/Analyzing.tsx` | B |

| 4-3-v2 | 분석 실패 | `/interview/failed/:runId` | `features/analysis/AnalysisFailed.tsx` | B |

| 5a-v2 | 레포 선택 | `/interview/repos/:runId` | `features/analysis/RepoSelect.tsx` | C |

| \*\*5a2-v2\*\* | \*\*면접 준비\*\* | `/interview/:id/prepare` | `features/interview/InterviewPrepare.tsx` | 공동 |

| 5b-v2 | 면접 진행 | `/interview/:id/session` | `features/interview/InterviewScreen.tsx` | 공동 |

| 5c-v2 | 면접 리포트 | `/interview/:id/report` | `features/report/Report.tsx` | C |

| — | 미정의 경로 | `\*` | → `/home` 리다이렉트 | — |



\### 경로 변수



`:` 는 실제 값이 들어오는 자리다. `useParams()`로 꺼낸다.



| 변수 | 값 | 예 |

| --- | --- | --- |

| `:runId` | 분석 run ID | `/interview/analyzing/run\_abc123` |

| `:id` | 면접 ID (`interviewId`) | `/interview/iv\_001/report` |



```tsx

const { runId } = useParams();   // "run\_abc123"

```



`runId`와 `id`의 경계



분석 단계(4-v2 \~ 5a-v2)는 `runId`, 면접 단계(5a2-v2 \~ 5c-v2)는 `id`를 쓴다. `POST /interviews`가 두 단계의 경계다.



\---



\## 3. 경로에 ID를 넣는 이유



\### 새로고침 복구



```

/interview/analyzing              F5 → 어느 분석인지 모름

/interview/analyzing/run\_abc123   F5 → runId 유지, 상태 재조회 가능

```



명세의 "새로고침 복구" 실패 케이스와 직결된다. `runId`가 경로에 있어야 `GET /analysis-runs/{runId}`로 진행 상태를 되살릴 수 있다.



5a2-v2와 5b-v2도 마찬가지로 `GET /interviews/{id}`로 복구한다.



\### 과거 리포트 조회



마이페이지에서 과거 면접을 클릭하면 그 리포트로 이동해야 한다.



```

/mypage → 면접 클릭 → /interview/iv\_001/report

```



\### 링크 공유



URL이 상태를 담으므로 특정 리포트 주소를 그대로 공유할 수 있다.



\---



\## 4. 화면별 API 매핑



경로 이름과 API 이름은 일치하지 않아도 무관하다.



| 화면 경로 | 호출 API |

| --- | --- |

| (전역) | `GET /me` |

| `/login` | `GET /auth/github/login` |

| `/home` | `GET /me/home` · `GET /auth/github/link` |

| `/mypage` | `GET /me/interviews` · `POST /auth/logout` |

| `/interview/new` | `POST /analysis-runs` |

| `/interview/analyzing/:runId` | `GET /analysis-runs/{runId}` · `/events` |

| `/interview/failed/:runId` | `GET /analysis-runs/{runId}` · `GET /auth/github/link` |

| `/interview/repos/:runId` | `GET /analysis-runs/{runId}/result` · `POST /interviews` |

| `/interview/:id/prepare` | WS `/ws/interviews/{sessionId}` · `GET /interviews/{id}` |

| `/interview/:id/session` | WS (연결 유지) · `GET /interviews/{id}` |

| `/interview/:id/report` | `GET /interviews/{id}/report` · `POST /interviews/{id}/retry` · `POST /reports/{id}/feedback-disagreements` |



`/mypage` ↔ `GET /me/interviews` 처럼 이름이 달라도 문제없다.



\---



\## 5. BE에 통보할 것



화면 경로 중 BE가 알아야 하는 것: 



> OAuth 콜백 후 `/home`으로 리다이렉트해주세요.

> 



```

GET /auth/github/callback      → 302 Location: /home

GET /auth/github/link/callback → 302 Location: /home

```



나머지 화면 경로는 BE가 알 필요 없다.



\---



\## 6. routes.tsx



```tsx

import { Routes, Route, Navigate } from 'react-router-dom';



import Login from '@/features/auth/Login';

import Home from '@/features/home/Home';

import MyPage from '@/features/mypage/MyPage';

import JobInput from '@/features/analysis/JobInput';

import Analyzing from '@/features/analysis/Analyzing';

import AnalysisFailed from '@/features/analysis/AnalysisFailed';

import RepoSelect from '@/features/analysis/RepoSelect';

import InterviewPrepare from '@/features/interview/InterviewPrepare';

import InterviewScreen from '@/features/interview/InterviewScreen';

import Report from '@/features/report/Report';



export default function AppRoutes() {

&#x20; return (

&#x20;   <Routes>

&#x20;     <Route path="/login" element={<Login />} />

&#x20;     <Route path="/home" element={<Home />} />

&#x20;     <Route path="/mypage" element={<MyPage />} />

&#x20;     <Route path="/interview/new" element={<JobInput />} />

&#x20;     <Route path="/interview/analyzing/:runId" element={<Analyzing />} />

&#x20;     <Route path="/interview/failed/:runId" element={<AnalysisFailed />} />

&#x20;     <Route path="/interview/repos/:runId" element={<RepoSelect />} />

&#x20;     <Route path="/interview/:id/prepare" element={<InterviewPrepare />} />

&#x20;     <Route path="/interview/:id/session" element={<InterviewScreen />} />

&#x20;     <Route path="/interview/:id/report" element={<Report />} />

&#x20;     <Route path="\*" element={<Navigate to="/home" replace />} />

&#x20;   </Routes>

&#x20; );

}

```



\### 속성 의미



| 속성 | 역할 |

| --- | --- |

| `path` | 어떤 주소일 때 |

| `element` | 무엇을 보여줄지 (컴포넌트) |



`element={<Login />}` — `{}`는 JSX에서 JavaScript 값을 넣는 표시이고, `<Login />`은 컴포넌트다. 문자열이 아니라 컴포넌트를 넘긴다.



`path="\*"` — 위의 어느 경로에도 안 맞으면. `replace`는 브라우저 히스토리를 남기지 않아 뒤로가기로 잘못된 주소에 다시 가지 않게 한다.



\### 라우트 순서 주의



```tsx

<Route path="/interview/new" element={<JobInput />} />

<Route path="/interview/:id/prepare" element={<InterviewPrepare />} />

```



`/interview/new`가 `/interview/:id`보다 \*\*먼저\*\* 와야 한다. React Router v6는 구체적인 경로를 우선하지만, 명시적으로 순서를 지켜두는 편이 안전하다.



\### `@` alias



```

@/features/report/Report  =  src/features/report/Report.tsx

```



`vite.config.ts`와 `tsconfig.json` \*\*양쪽\*\*에 `@` → `src` alias를 설정해야 동작한다. 한쪽만 하면 `npm run dev`는 되고 `npm run build`가 실패한다.



\---



\## 7. main.tsx 연결



`<Routes>`는 `<BrowserRouter>` 안에 있어야 동작한다.



```tsx

import { createRoot } from 'react-dom/client';

import { BrowserRouter } from 'react-router-dom';

import AppRoutes from './routes';

import './index.css';



createRoot(document.getElementById('root')!).render(

&#x20; <BrowserRouter>

&#x20;   <AppRoutes />

&#x20; </BrowserRouter>

);

```



\---



\## 8. 컴포넌트 파일 위치



```

src/features/

&#x20; auth/

&#x20;   Login.tsx                 /login

&#x20; home/

&#x20;   Home.tsx                  /home

&#x20; mypage/

&#x20;   MyPage.tsx                /mypage

&#x20; analysis/

&#x20;   JobInput.tsx              /interview/new

&#x20;   Analyzing.tsx             /interview/analyzing/:runId

&#x20;   AnalysisFailed.tsx        /interview/failed/:runId

&#x20;   RepoSelect.tsx            /interview/repos/:runId

&#x20; interview/

&#x20;   InterviewPrepare.tsx      /interview/:id/prepare

&#x20;   InterviewScreen.tsx       /interview/:id/session

&#x20; report/

&#x20;   Report.tsx                /interview/:id/report

```



\---



\## 9. W5 작업 순서



| 순서 | 작업 | 비고 |

| --- | --- | --- |

| 1 | 빈 컴포넌트 \*\*10개\*\* 생성 | 파일이 없으면 import 실패 |

| 2 | `routes.tsx` 작성 |  |

| 3 | `main.tsx`에 `<BrowserRouter>` 연결 | 빠뜨리기 쉬움 |

| 4 | 각 경로 접속 확인 | 배포 환경에서도 |



빈 컴포넌트는 껍데기로 둔다.



```tsx

// features/mypage/MyPage.tsx

export default function MyPage() {

&#x20; return <div>MyPage</div>;

}

```



W5에 10개를 미리 등록하고 동결한다



`routes.tsx`는 화면을 만들 때마다 라우트를 추가해야 하므로 가장 충돌이 잦은 파일이다. 미리 다 등록해두면 담당자는 자기 컴포넌트 파일 내용만 채우면 되고, 이 파일은 프로젝트 끝까지 건드리지 않는다.



배포 환경 확인 필수



`/interview/new` 등에 직접 접속하거나 새로고침하면 서버에 그런 파일이 없어 404가 난다. `vercel.json`의 `{ "source": "/(.\*)", "destination": "/index.html" }`이 이를 막는다. 배포 후 반드시 확인한다.



\---





\### FE 주차별 역할 분담



\### 수정된 표



| 스프린트 | 주차 | 진영님 | 유석님 | 현솔님 |

| --- | --- | --- | --- | --- |

| 1 | W5 | 인프라 마무리 · \*\*4-v2 공고 입력\*\* | \*\*MSW 핸들러 구축\*\* · 인프라 리뷰 | \*\*3 홈 대시보드\*\* · \*\*6 마이페이지\*\* |

| 1 | W6 | \*\*WS 프로토콜 spike\*\* · \*\*5a2-v2\*\* · 5b-v2 화면 껍데기 | \*\*MSW 실패 케이스\*\* · \*\*WS Mock 방식 결정\*\* | \*\*5a-v2\*\* · \*\*4-3-v2\*\* · \*\*4-2-v2\*\* |

| 1 | W7 | \*\*5b-v2\*\* — 통신 · 상태 · 캡션 · 입력창 | \*\*WS Mock 서버\*\* · 교차 리뷰 | \*\*5c-v2 리포트\*\* |

| 2 | W8 | \*\*STT · TTS 연동\*\* · 5a2-v2 기기 점검 | \*\*1 로그인 화면\*\* · 인증 상태 관리 | 3 홈 데이터 연결 · 6 마이페이지 실연동 |

| 2 | W9 | \*\*재연결 · 상태 복구 · 마이크 차단\*\* · 캡션 토글 | \*\*전 화면 실패 케이스 검증\*\* | \*\*4-2-v2 SSE\*\* · 5c-v2 retry · 피드백 이의 |

| 2 | W10 | \*\*WS 실패 처리 전면\*\* · Evidence 배너 · 통합 | \*\*통합 테스트 주도\*\* · 릴리즈 노트 | 실패 케이스 UI · 통합 |

| 3 | W11 | 중간고사 — 최소 | 중간고사 — 최소 | 중간고사 — 최소 |

| 3 | W12 | \*\*음성 실연동 마무리\*\* · 5b-v2 보완 | 성능·안정성 검증 | 화면 보완 · UI 다듬기 |

| 3 | W13 | 통합 · 최종 배포 | \*\*최종 검증\*\* | 통합 · 배포 |



\---



\### 배포 마일스톤



| 스프린트 | 주차 | 배포 | 상태 |

| --- | --- | --- | --- |

| 1 | W7 | v0.1 | 화면 10개 구성 · 로그인 없음(고정 사용자) · 오디오 미구현 |

| 2 | W10 | v0.2 | 전 화면·전 기능 완성 · 음성은 Mock 가능 |

| 3 | W13 | v1.0 | 음성 실연동 완료 |





\- \*\*최종 엔드포인트 목록\*\*

&#x20;   

&#x20;   ## 최종 엔드포인트 목록

&#x20;   

&#x20;   총 20개.

&#x20;   

&#x20;   | # | 메서드 | 경로 | 구현 방식 | 인증 |

&#x20;   | --- | --- | --- | --- | --- |

&#x20;   | 1 | GET | `/auth/github/login` | 브라우저 이동 | 불필요 |

&#x20;   | 2 | GET | `/auth/github/callback` | 프론트 무관 | 불필요 |

&#x20;   | 3 | POST | `/auth/refresh` | fetch | `refreshToken` |

&#x20;   | 4 | POST | `/auth/logout` | fetch | `accessToken` |

&#x20;   | 5 | GET | `/me` | fetch | `accessToken` |

&#x20;   | 6 | GET | `/auth/github/link` | 브라우저 이동 | `accessToken` |

&#x20;   | 7 | GET | `/auth/github/link/callback` | 프론트 무관 | `accessToken` |

&#x20;   | 8 | GET | `/me/home` | fetch | `accessToken` |

&#x20;   | 9 | GET | `/me/interviews` | fetch | `accessToken` |

&#x20;   | 10 | GET | `/me/repositories` | fetch | `accessToken` |

&#x20;   | 11 | POST | `/analysis-runs` | fetch (multipart) | `accessToken` |

&#x20;   | 12 | GET | `/analysis-runs/{runId}/events` | EventSource | `accessToken` |

&#x20;   | 13 | GET | `/analysis-runs/{runId}` | fetch | `accessToken` |

&#x20;   | 14 | GET | `/analysis-runs/{runId}/result` | fetch | `accessToken` |

&#x20;   | 15 | POST | `/interviews` | fetch | `accessToken` |

&#x20;   | 16 | GET | `/interviews/{id}` | fetch | `accessToken` |

&#x20;   | 17 | GET \*(Upgrade)\* | `/ws/interviews/{sessionId}` | WebSocket | `accessToken` |

&#x20;   | 18 | GET | `/interviews/{id}/report` | fetch | `accessToken` |

&#x20;   | 19 | POST | `/interviews/{id}/retry` | fetch | `accessToken` |

&#x20;   | 20 | POST | `/reports/{id}/feedback-disagreements` | fetch | `accessToken` |

&#x20;   

&#x20;   `shared/api.ts`에 넣지 않는 것: 1, 2, 6, 7 (브라우저 이동 또는 프론트 무관). 3은 인터셉터 내부에서만 호출한다.

&#x20;   

&#x20;   ### 구현 방식별 분류

&#x20;   

&#x20;   | 방식 | 엔드포인트 |

&#x20;   | --- | --- |

&#x20;   | 브라우저 이동 | 1, 6 |

&#x20;   | 프론트 무관 (서버 302) | 2, 7 |

&#x20;   | `fetch` GET | 5, 8, 9, 10, 13, 14, 16, 18 |

&#x20;   | `fetch` POST | 3, 4, 11, 15, 19, 20 |

&#x20;   | `EventSource` | 12 |

&#x20;   | `WebSocket` | 17 |

\- \*\*화면별 API 사용표\*\*

&#x20;   

&#x20;   ## 화면별 API 사용표

&#x20;   

&#x20;   `R` = 조회, `W` = 호출(상태 변경), `S` = 스트리밍 구독

&#x20;   

&#x20;   | 화면 | 코드 | 사용 API |

&#x20;   | --- | --- | --- |

&#x20;   | 로그인 | — | `/auth/github/login` (이동) |

&#x20;   | 홈 | `/home` | `/me/home` R |

&#x20;   | 면접 기록 | — | `/me/interviews` R |

&#x20;   | 공고·문서 입력 | 4-1-v2 | `/analysis-runs` W |

&#x20;   | 분석 진행 | 4-2-v2 | `/analysis-runs/{runId}/events` S · `/analysis-runs/{runId}` R |

&#x20;   | 분석 실패 | 4-3-v2 | `/analysis-runs/{runId}` R · `/analysis-runs` W (재시도) · `/auth/github/link` (이동) |

&#x20;   | 레포 확정 | 5a-v2 | `/analysis-runs/{runId}/result` R · `/me/repositories` R · `/interviews` W |

&#x20;   | 면접 준비 | 5a2-v2 | `/interviews/{id}` R · `/ws/interviews/{sessionId}` S |

&#x20;   | 면접 진행 | 5b-v2 | `/ws/interviews/{sessionId}` S · `/interviews/{id}` R (재연결 복구) |

&#x20;   | 리포트 | 5c-v2 | `/interviews/{id}/report` R · `/reports/{id}/feedback-disagreements` W · `/interviews/{id}/retry` W |

&#x20;   | 전역 | — | `/me` R (인증 가드) · `/auth/refresh` W (인터셉터) · `/auth/logout` W |

&#x20;   

&#x20;   ### 화면별 상세

&#x20;   

&#x20;   \*\*로그인\*\*

&#x20;   

&#x20;   | 항목 | 내용 |

&#x20;   | --- | --- |

&#x20;   | 진입 | 미인증 상태에서 보호 경로 접근 시 |

&#x20;   | 호출 | 버튼 클릭 → `window.location = '/auth/github/login'` |

&#x20;   | 복귀 | 서버가 `/home`으로 302. 실패 시 `/login?error=denied` |

&#x20;   

&#x20;   \*\*홈\*\* `/home`

&#x20;   

&#x20;   | 상태 | 판별 | 화면 |

&#x20;   | --- | --- | --- |

&#x20;   | 동기화 중 | `analysisStatus === 'syncing'` | 레포 수집 중 안내, 폴링 |

&#x20;   | 레포 없음 | `analysisStatus === 'no\_repository'` | 공개 레포 없음 안내 |

&#x20;   | 면접 없음 | `analysisStatus === 'no\_interview'` | 첫 면접 유도 CTA |

&#x20;   | 프로필 있음 | `analysisStatus === 'completed'` | `analysis` 패널 + `recentInterviews` |

&#x20;   | GitHub 재연동 | `403 github\_token\_invalid` | `/auth/github/link`로 이동 유도 |

&#x20;   

&#x20;   \*\*분석 진행\*\* 4-2-v2

&#x20;   

&#x20;   `EventSource`로 `step`·`progress`를 받아 체크리스트를 갱신한다. `completed` 수신 시 5a-v2로 이동, `failed` 수신 시 4-3-v2로 전환한다. `onerror` 발생 시 `/analysis-runs/{runId}`를 1회 호출해 상태를 확인한다.

&#x20;   

&#x20;   \*\*분석 실패\*\* 4-3-v2

&#x20;   

&#x20;   `failureReason`으로 문구와 재시도 가능 여부를 분기한다. `no\_public\_repo`·`user\_not\_found`는 재시도 버튼을 숨긴다. `github\_token\_invalid`는 `/auth/github/link` 이동을 강조한다.

&#x20;   

&#x20;   \*\*레포 확정\*\* 5a-v2

&#x20;   

&#x20;   | 영역 | 필드 |

&#x20;   | --- | --- |

&#x20;   | 좌측 레포 카드 | `repositories\[]` — `name` · `languages` · `topics` · `stars` · `forks` · `commitCount` · `userCommitCount` · `pushedAt` · `recommendReason` |

&#x20;   | 배지 | `candidateSource` (📎 포트폴리오) · `recommended` (AI 추천) |

&#x20;   | 실패 카드 | `status === 'failed'` → 회색 처리 + `errorCode` 문구 |

&#x20;   | 우측 공고 리스트 | `jdRequirements\[]` — `category` 그룹핑, `displayOrder` 순, 읽기 전용 |

&#x20;   | 포트폴리오 안내 | `mentionedRepoCount` ≠ `matchedRepoCount`일 때 표시 |

&#x20;   | 더 보기 | `/me/repositories` — 룰 필터 탈락분 포함 전체 목록 |

&#x20;   | 확정 | `/interviews` W — `repositoryIds` 최대 5개 |

&#x20;   

&#x20;   `recommended: true`인 레포는 기본 체크 상태로 표시한다.

&#x20;   

&#x20;   \*\*면접 준비\*\* 5a2-v2

&#x20;   

&#x20;   `/interviews/{id}` R로 `status === 'preparing'`을 확인한 뒤 WS를 연결한다. `prepareStep`으로 준비 진행률을 표시하고 `prepareCompleted` 수신 시 5b-v2로 전환한다. WS는 5b-v2까지 유지한다.

&#x20;   

&#x20;   \*\*면접 진행\*\* 5b-v2

&#x20;   

&#x20;   | 흐름 | 메시지 |

&#x20;   | --- | --- |

&#x20;   | 질문 수신 | `question` → TTS 오디오 바이너리 → `questionEnd` |

&#x20;   | 답변 전송 | `answerStart` → 오디오 바이너리 → `answerEnd` |

&#x20;   | 수신 확인 | `answerReceived` — 이 메시지 전까지 업로드 중 상태 유지 |

&#x20;   | 전사 표시 | `transcript` |

&#x20;   | 생성 대기 | `thinking` · `evidenceCheck` |

&#x20;   | 종료 | `interviewEnd` → 5c-v2로 이동 |

&#x20;   

&#x20;   `onclose` 시 `/interviews/{id}`를 호출해 토큰을 갱신하고 `turns`로 복구한 뒤 재연결한다. `remainingSeconds`로 클라이언트 타이머를 덮어쓴다.

&#x20;   

&#x20;   `error` 수신 시 `recoverable`로 분기한다. `true`면 해당 턴을 재시도하고, `false`면 세션이 종료되므로 안내 후 이탈한다.

&#x20;   

&#x20;   \*\*리포트\*\* 5c-v2

&#x20;   

&#x20;   | 탭 | 필드 |

&#x20;   | --- | --- |

&#x20;   | 종합리포트 | `headline` · `totalScore` · `summary` · `scores` · `coverage` |

&#x20;   | 면접관별 피드백 | `agentFeedbacks` — `disagreementSubmitted`로 이의 제기 버튼 상태 결정 |

&#x20;   | 면접 기록 | `turns` |

&#x20;   

&#x20;   `202 generating` 수신 시 `retryAfter` 간격으로 폴링한다. `409 report\_unavailable`이면 진행된 턴이 0개이므로 리포트 없이 안내한다.

&#x20;   

&#x20;   ---

&#x20;   

&#x20;   ## 화면 전이

&#x20;   

&#x20;   ```

&#x20;   /login

&#x20;     └─ /auth/github/login → GitHub → /auth/github/callback → /home

&#x20;   

&#x20;   /home

&#x20;     ├─ 면접 기록 목록

&#x20;     │    └─ 완료 면접 선택 → 5c-v2

&#x20;     └─ 새 면접 시작 → 4-1-v2

&#x20;   

&#x20;   4-1-v2  공고·문서 입력

&#x20;     └─ POST /analysis-runs → 202 → 4-2-v2

&#x20;   

&#x20;   4-2-v2  분석 진행

&#x20;     ├─ completed → 5a-v2

&#x20;     └─ failed    → 4-3-v2 ─(재시도)→ 4-2-v2

&#x20;   

&#x20;   5a-v2   레포 확정

&#x20;     └─ POST /interviews → 201 → 5a2-v2

&#x20;   

&#x20;   5a2-v2  면접 준비 (WS 연결)

&#x20;     └─ prepareCompleted → 5b-v2

&#x20;   

&#x20;   5b-v2   면접 진행 (WS 유지)

&#x20;     ├─ interviewEnd → 5c-v2

&#x20;     └─ 이탈         → status='abandoned'

&#x20;   

&#x20;   5c-v2   리포트

&#x20;     └─ POST /interviews/{id}/retry → 201 → 5a2-v2

&#x20;   ```

&#x20;   

&#x20;   `GET /interviews/{id}`의 `status`로 새로고침·재진입 시 도달할 화면을 결정한다.

&#x20;   

&#x20;   | `status` | 화면 |

&#x20;   | --- | --- |

&#x20;   | `preparing` | 5a2-v2 |

&#x20;   | `in\_progress` | 5b-v2 (`turns` 복구) |

&#x20;   | `completed` | 5c-v2 |

&#x20;   | `abandoned` | 안내 후 `/home` |



\---



\# DEVON API 명세



> 필드: camelCase · URL: kebab-case · 에러 reason·enum: snake\_case

> 



\## 공통 규약



| 항목 | 규칙 |

| --- | --- |

| 필드 네이밍 | camelCase |

| 배열 빈 값 | `\[]` — null 금지 |

| 객체 빈 값 | `null` 허용 (명시된 필드만) |

| 날짜 | ISO 8601 문자열 |

| 필드 생략 | 금지 |

| 인증 | JWT — HttpOnly 쿠키 전달. 모든 요청에 `credentials: 'include'` |

| 배포 | FE·BE 단일 CloudFront 배포. same-origin이므로 CORS 설정 불필요, API base URL은 상대경로 |



\### 인증 구조



| 토큰 | 쿠키명 | 만료 | Path |

| --- | --- | --- | --- |

| Access Token | `accessToken` | 15분 | `/` |

| Refresh Token | `refreshToken` | 14일 | `/auth/refresh` |



```

Set-Cookie: accessToken=<jwt>;  HttpOnly; Secure; SameSite=Lax; Path=/;             Max-Age=900

Set-Cookie: refreshToken=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/auth/refresh; Max-Age=1209600

```



Access Token 클레임



```json

{ "sub": "u\_001", "iat": 1757300000, "exp": 1757300900, "jti": "at\_9f2c1b" }

```



리프레시 토큰은 서버 DB에 `jti`·상태·만료 시각을 저장하고, 갱신 시 로테이션한다. 폐기된 `jti`가 재사용되면 해당 사용자의 모든 리프레시 토큰을 무효화한다.



GitHub 토큰(`github\_accounts.access\_token\_encrypted`)은 JWT에 담지 않는다. 서버가 조회한다.



\### enum



```

analysisStatus:   syncing | no\_repository | no\_interview | completed

interviewStatus:  preparing | in\_progress | completed | abandoned

runStatus:        running | completed | failed

stepKey:          doc\_extract | repo\_select | repo\_detail | jd\_fetch

&#x20;                 | jd\_extract | repo\_analyze | match\_score

prepareStepKey:   analyze\_repo | build\_persona | compose\_question | set\_criteria

stepStatus:       pending | running | completed

repoStatus:       succeeded | partial | failed

candidateSource:  rule\_filter | portfolio | both

jdCategory:       required | preferred | responsibility

persona:          tech\_lead | hr\_manager | domain\_lead

scoreKey:         project\_understanding | technical\_reasoning | problem\_solving

&#x20;                 | communication | contribution\_clarity | company\_job\_fit

reasonType:       factual\_error | insufficient\_basis | overly\_harsh

&#x20;                 | unclear\_intent | other

```



\### 에러 응답 (모든 4xx·5xx 공통)



```json

{

&#x20; "error": {

&#x20;   "reason": "github\_token\_invalid",

&#x20;   "message": "GitHub 재연동이 필요해요.",

&#x20;   "retryAfter": 30

&#x20; }

}

```



`reason`은 종류가 많으므로 union으로 고정하지 않고 `string`으로 둔다.

`retryAfter`는 optional.



\### 인증 에러 reason



| reason | 코드 | 의미 | 프론트 처리 |

| --- | --- | --- | --- |

| `unauthenticated` | 401 | `accessToken` 쿠키 없음 | `/login` 이동 |

| `access\_token\_expired` | 401 | 서명 유효, `exp` 초과 | `/auth/refresh` 1회 → 원 요청 재시도 |

| `access\_token\_invalid` | 401 | 서명 불일치·변조 | 전체 clear → `/login` |

| `refresh\_token\_invalid` | 401 | 리프레시 만료·재사용 감지 | 전체 clear → `/login` |

| `account\_suspended` | 403 | `users.status = 'suspended'` | 정지 안내 |

| `account\_withdrawn` | 403 | `users.status = 'withdrawn'` | 재가입 불가 안내 |

| `github\_token\_invalid` | 403 | `github\_accounts.token\_status`가 `expired`·`revoked` | GitHub 재연동 유도 |



\### 401 인터셉터 정책



```

401 수신

├─ reason === 'access\_token\_expired'

│   ├─ 갱신 진행 중이면 → 그 Promise를 await (single-flight)

│   ├─ 아니면 → POST /auth/refresh

│   ├─ 성공 → 원 요청 1회 재시도

│   └─ 실패 → queryClient.clear() → /login

└─ 그 외 → queryClient.clear() → /login

```



재시도는 1회만. 갱신은 single-flight(로테이션 충돌 방지). `/auth/refresh` 자신은 인터셉터 제외.



\### CSRF



`SameSite=Lax`로 방어한다. 상태 변경 요청은 모두 POST이며 `Lax`는 cross-site POST에 쿠키를 보내지 않는다. CSRF 토큰은 도입하지 않는다. `Strict`는 GitHub 콜백에서 돌아오는 top-level GET에 쿠키가 실리지 않아 쓰지 않는다.



\---



\## 엔드포인트 목록



| 메서드 | 경로 | 구현 방식 |

| --- | --- | --- |

| GET | `/auth/github/login` | 브라우저 이동 |

| GET | `/auth/github/callback` | 프론트 무관 |

| POST | `/auth/refresh` | fetch |

| POST | `/auth/logout` | fetch |

| GET | `/me` | fetch |

| GET | `/auth/github/link` | 브라우저 이동 |

| GET | `/auth/github/link/callback` | 프론트 무관 |

| GET | `/me/home` | fetch |

| GET | `/me/interviews` | fetch |

| GET | `/me/repositories` | fetch |

| POST | `/analysis-runs` | fetch (multipart) |

| GET | `/analysis-runs/{runId}/events` | EventSource |

| GET | `/analysis-runs/{runId}` | fetch |

| GET | `/analysis-runs/{runId}/result` | fetch |

| POST | `/interviews` | fetch |

| GET | `/interviews/{id}` | fetch |

| GET \*(Upgrade)\* | `/ws/interviews/{sessionId}` | WebSocket |

| GET | `/interviews/{id}/report` | fetch |

| POST | `/interviews/{id}/retry` | fetch |

| POST | `/reports/{id}/feedback-disagreements` | fetch |



> 브라우저 이동 경로는 `shared/api.ts`에 넣지 않는다. `<a href>` 또는 `window.location`으로 처리한다.

> 



> `sessionId`·`session\_limit\_exceeded`·`already\_connected`의 "세션"은 면접 세션(`interview\_sessions`)을 뜻한다. 인증 세션은 존재하지 않는다.

> 



\---



\## GET /auth/github/login



Request — 없음



Response `302`



```

Location: https://github.com/login/oauth/authorize

&#x20;           ?client\_id=<client\_id>

&#x20;           \&redirect\_uri=<callback>

&#x20;           \&scope=read:user%20user:email

&#x20;           \&state=<random>

Set-Cookie: oauthState=<random>; HttpOnly; Secure; SameSite=Lax; Path=/auth/github; Max-Age=600

```



| 항목 | 값 |

| --- | --- |

| `scope` | `read:user`, `user:email` (Private 레포 미지원이므로 `repo` 불필요) |

| `state` | 서버 생성 랜덤값 — `oauthState` 쿠키에 저장 (CSRF 방어) |



\---



\## GET /auth/github/callback



Request (Query)



```

?code=abc123\&state=x7f2a9

```



| 필드 | 필수 | 비고 |

| --- | --- | --- |

| `code` | ✅ | 1회용, 약 10분 유효 |

| `state` | ✅ | `oauthState` 쿠키값과 대조 |

| `error` | ❌ | 사용자 동의 거부 시 |



Response `302`



```

Location: /home

Set-Cookie: accessToken=<jwt>;  HttpOnly; Secure; SameSite=Lax; Path=/;             Max-Age=900

Set-Cookie: refreshToken=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/auth/refresh; Max-Age=1209600

Set-Cookie: oauthState=; Max-Age=0; Path=/auth/github

```



동의 거부 시



```

Location: /login?error=denied

```



성공 시 `initial\_sync` 잡을 큐에 넣고 즉시 302한다. 레포 수집 완료를 기다리지 않는다.



> 반드시 쿼리를 제거한 주소로 302한다. `?code=`가 남으면 새로고침 시 재사용이 발생하고, GitHub은 code 재사용을 탈취로 판단해 이미 발급한 토큰까지 무효화한다.

> 



| 코드 | reason |

| --- | --- |

| 400 | `invalid\_state` · `invalid\_code` |

| 403 | `account\_suspended` · `account\_withdrawn` |

| 502 | `provider\_unavailable` |



\---



\## POST /auth/refresh



Request — 없음 (`refreshToken` 쿠키만 사용)



Response `204 No Content`



```

Set-Cookie: accessToken=<new\_jwt>;  HttpOnly; Secure; SameSite=Lax; Path=/;             Max-Age=900

Set-Cookie: refreshToken=<new\_jwt>; HttpOnly; Secure; SameSite=Lax; Path=/auth/refresh; Max-Age=1209600

```



갱신 시 리프레시 토큰도 새로 발급하고 이전 `jti`는 폐기한다.



Response 실패



| 코드 | reason |

| --- | --- |

| 401 | `refresh\_token\_invalid` |

| 403 | `account\_suspended` · `account\_withdrawn` |



\---



\## POST /auth/logout



Request — 없음



Response `204 No Content`



```

Set-Cookie: accessToken=;  Max-Age=0; Path=/

Set-Cookie: refreshToken=; Max-Age=0; Path=/auth/refresh

```



리프레시 토큰은 서버 DB에서 삭제한다. 액세스 토큰은 무효화하지 않으며 남은 유효기간(최대 15분)까지 서명이 유효하다. 이미 만료된 상태여도 `204`로 응답한다 (멱등). GitHub 토큰은 삭제하지 않는다.



\---



\## GET /me



Response `200 OK`



```json

{

&#x20; "name": "김개발",

&#x20; "avatarUrl": "https://avatars.githubusercontent.com/u/12345",

&#x20; "githubLinked": true

}

```



| 필드 | 타입 | null |

| --- | --- | --- |

| `name` | string | ❌ |

| `avatarUrl` | string | ✅ |

| `githubLinked` | boolean | ❌ |



`name`은 `users.display\_name` (GitHub `name`, 없으면 `login`).



Response `401` — `unauthenticated` · `access\_token\_expired` · `access\_token\_invalid`



\---



\## GET /auth/github/link



GitHub 토큰 무효 시 재연동. DEVON 로그인 상태는 유지되고 GitHub 토큰만 갱신된다.



Request — 없음



Response `302`



```

Location: https://github.com/login/oauth/authorize?...\&state=<random>

Set-Cookie: oauthState=<random>; HttpOnly; Secure; SameSite=Lax; Path=/auth/github; Max-Age=600

```



Response `302` → `/login` — `accessToken`이 없거나 만료된 경우



> 이 경로는 브라우저 이동이므로 401 인터셉터가 동작하지 않는다. 만료 시 JSON 401이 아니라 `/login`으로 302한다.

> 



\---



\## GET /auth/github/link/callback



Request (Query) — `code`, `state` (login 콜백과 동일)



Response `302`



```

Location: /home

Set-Cookie: oauthState=; Max-Age=0; Path=/auth/github

```



`github\_accounts.token\_status`를 `valid`로 갱신한다. 액세스 토큰 쿠키는 재발급하지 않는다.



Response `409` — `github\_already\_linked`



\---



\## GET /me/home



Response `200 OK`



```json

{

&#x20; "name": "김개발",

&#x20; "githubLinked": true,

&#x20; "repositoryCount": 5,

&#x20; "analysisStatus": "completed",

&#x20; "analysis": {

&#x20;   "basedOnRepoCount": 2,

&#x20;   "languages": \[

&#x20;     { "name": "TypeScript", "ratio": 42 },

&#x20;     { "name": "Java", "ratio": 31 }

&#x20;   ],

&#x20;   "projectTypes": \["백엔드 API 서버", "결제·트랜잭션"],

&#x20;   "roleSummary": "2개 레포의 README와 커밋 이력을 종합하면 백엔드 API 설계와 DB·캐시 최적화를 가장 자주 맡았습니다."

&#x20; },

&#x20; "recentInterviews": \[

&#x20;   {

&#x20;     "id": "iv\_001",

&#x20;     "position": "Backend Developer",

&#x20;     "companyName": "토스뱅크",

&#x20;     "totalScore": 81,

&#x20;     "completedAt": "2026-09-01T15:20:00Z"

&#x20;   }

&#x20; ]

}

```



| `analysisStatus` | 의미 | `analysis` | `recentInterviews` |

| --- | --- | --- | --- |

| `syncing` | `initial\_sync` 진행 중 | `null` | `\[]` |

| `no\_repository` | 공개 레포 없음 | `null` | `\[]` |

| `no\_interview` | 레포는 있으나 확정 면접 없음 | `null` | `\[]` |

| `completed` | 프로필 생성됨 | 객체 | 배열 |



| 필드 | 타입 | null |

| --- | --- | --- |

| `name` | string | ❌ |

| `githubLinked` | boolean | ❌ |

| `repositoryCount` | number | ❌ |

| `analysisStatus` | AnalysisStatus | ❌ |

| `analysis` | AnalysisPanel | ✅ |

| `analysis.basedOnRepoCount` | number | ❌ |

| `analysis.languages\[].name` | string | ❌ |

| `analysis.languages\[].ratio` | number | ❌ |

| `analysis.projectTypes` | string\[] | ❌ |

| `analysis.roleSummary` | string | ❌ |

| `recentInterviews\[].id` | string | ❌ |

| `recentInterviews\[].position` | string | ❌ |

| `recentInterviews\[].companyName` | string | ✅ |

| `recentInterviews\[].totalScore` | number | ✅ |

| `recentInterviews\[].completedAt` | string | ✅ |



`analysis`는 `user\_profile\_summaries` 1행을 그대로 매핑한다.



Response `403` — `github\_token\_invalid`



\---



\## GET /me/interviews



Request (Query)



```

?page=1\&size=20

```



| 필드 | 타입 | 필수 | 기본값 |

| --- | --- | --- | --- |

| `page` | number | ❌ | 1 |

| `size` | number | ❌ | 20 |



Response `200 OK`



```json

{

&#x20; "interviews": \[

&#x20;   {

&#x20;     "id": "iv\_001",

&#x20;     "position": "Backend Developer",

&#x20;     "companyName": "토스뱅크",

&#x20;     "repositoryNames": \["project-a", "payment-service"],

&#x20;     "status": "completed",

&#x20;     "totalScore": 81,

&#x20;     "startedAt": "2026-09-01T15:00:00Z",

&#x20;     "completedAt": "2026-09-01T15:20:00Z"

&#x20;   }

&#x20; ],

&#x20; "total": 12,

&#x20; "page": 1,

&#x20; "size": 20

}

```



| 필드 | 타입 | null |

| --- | --- | --- |

| `interviews\[].id` | string | ❌ |

| `interviews\[].position` | string | ❌ |

| `interviews\[].companyName` | string | ✅ |

| `interviews\[].repositoryNames` | string\[] | ❌ |

| `interviews\[].status` | InterviewStatus | ❌ |

| `interviews\[].totalScore` | number | ✅ |

| `interviews\[].startedAt` | string | ✅ |

| `interviews\[].completedAt` | string | ✅ |

| `total` `page` `size` | number | ❌ |



`startedAt`은 첫 질문 시각이므로 `preparing` 상태에서는 `null`이다.



기록 0건이면 `interviews: \[]`, `total: 0`.



\---



\## GET /me/repositories



5a-v2의 "내 레포 더 보기". 룰 필터 탈락분을 포함한 전체 공개 레포 목록이다.



Request (Query)



```

?page=1\&size=30

```



| 필드 | 타입 | 필수 | 기본값 |

| --- | --- | --- | --- |

| `page` | number | ❌ | 1 |

| `size` | number | ❌ | 30 |



Response `200 OK`



```json

{

&#x20; "repositories": \[

&#x20;   {

&#x20;     "id": "r\_045",

&#x20;     "name": "react-dashboard",

&#x20;     "fullName": "kim/react-dashboard",

&#x20;     "description": "관리자 대시보드",

&#x20;     "primaryLanguage": "TypeScript",

&#x20;     "topics": \["react", "dashboard"],

&#x20;     "stars": 3,

&#x20;     "forks": 0,

&#x20;     "isFork": false,

&#x20;     "isArchived": false,

&#x20;     "pushedAt": "2025-11-02T08:00:00Z"

&#x20;   }

&#x20; ],

&#x20; "total": 167,

&#x20; "page": 1,

&#x20; "size": 30

}

```



| 필드 | 타입 | null |

| --- | --- | --- |

| `repositories\[].id` | string | ❌ |

| `repositories\[].name` | string | ❌ |

| `repositories\[].fullName` | string | ❌ |

| `repositories\[].description` | string | ✅ |

| `repositories\[].primaryLanguage` | string | ✅ |

| `repositories\[].topics` | string\[] | ❌ |

| `repositories\[].stars` | number | ❌ |

| `repositories\[].forks` | number | ❌ |

| `repositories\[].isFork` | boolean | ❌ |

| `repositories\[].isArchived` | boolean | ❌ |

| `repositories\[].pushedAt` | string | ✅ |

| `total` `page` `size` | number | ❌ |



`repo\_pushed\_at` 내림차순. `fetch\_level='list'`인 레포는 `languages`·`commitCount`가 아직 없으므로 이 응답에 포함하지 않는다.



Response `403` — `github\_token\_invalid`



\---



\## POST /analysis-runs



`analysis\_jobs` 1행(`job\_type='interview\_prep'`)을 생성한다.



Request `multipart/form-data`



| 필드 | 타입 | 필수 | 상한 |

| --- | --- | --- | --- |

| `jobUrl` | text | ✅ | — |

| `coverLetter` | file (.pdf/.docx) | ❌ | 10MB |

| `portfolioFile` | file | ❌ | 20MB |

| `portfolioUrl` | text | ❌ | — |



> `Content-Type` 헤더를 직접 지정하지 않는다. 브라우저가 boundary와 함께 자동 생성해야 한다.

> 



Response `202 Accepted`



```

Location: /analysis-runs/run\_abc123

```



```json

{ "runId": "run\_abc123" }

```



Response 실패



| 코드 | reason |

| --- | --- |

| 400 | `job\_url\_required` · `unsupported\_site` · `url\_unreachable` |

| 409 | `run\_in\_progress` (응답에 `runId` 포함) |

| 413 | `file\_too\_large` |

| 415 | `unsupported\_media\_type` |



> 공고 수집·추출 실패는 잡 생성 후 발생하므로 `202`로 응답하고 `failureReason`으로 전달한다. `unsupported\_site`(어댑터 없는 사이트)와 `url\_unreachable`만 잡 생성 전에 판별 가능하므로 `400`이다.

> 



> 동일 `jobUrl`이 7일 이내에 `success`로 파싱된 이력이 있으면 `job\_postings` 행을 재사용한다. 프론트에서 구분할 필요는 없다.

> 



\---



\## GET /analysis-runs/{runId}/events



SSE · `text/event-stream`



```jsx

new EventSource(`/analysis-runs/${runId}/events`, { withCredentials: true })

```



```

data: {"type":"step","key":"jd\_extract","status":"completed"}



data: {"type":"progress","value":57}



data: {"type":"completed"}



data: {"type":"failed","reason":"github\_token\_invalid"}

```



| type | 필드 |

| --- | --- |

| `step` | `key` (StepKey), `status` (StepStatus) |

| `progress` | `value` (number, 0\~100) |

| `completed` | — |

| `failed` | `reason` (string) |



인증은 연결 수립 시 1회 검증한다. 연결 유지 중 액세스 토큰이 만료되어도 스트림을 끊지 않는다.



> `EventSource`는 응답 바디를 읽을 수 없어 `onerror`에서 상태 코드를 알 수 없다. 401 판별이 필요하면 `GET /analysis-runs/{runId}`를 1회 호출해 확인한다.

> 



\---



\## GET /analysis-runs/{runId}



Response `200 OK`



```json

{

&#x20; "runId": "run\_abc123",

&#x20; "status": "running",

&#x20; "steps": \[

&#x20;   { "key": "doc\_extract",  "status": "completed" },

&#x20;   { "key": "repo\_select",  "status": "completed" },

&#x20;   { "key": "repo\_detail",  "status": "completed" },

&#x20;   { "key": "jd\_fetch",     "status": "completed" },

&#x20;   { "key": "jd\_extract",   "status": "running" },

&#x20;   { "key": "repo\_analyze", "status": "pending" },

&#x20;   { "key": "match\_score",  "status": "pending" }

&#x20; ],

&#x20; "progress": 57,

&#x20; "failureReason": null,

&#x20; "estimatedSeconds": 20

}

```



| 필드 | 타입 | null |

| --- | --- | --- |

| `runId` | string | ❌ |

| `status` | RunStatus | ❌ |

| `steps\[].key` | StepKey | ❌ |

| `steps\[].status` | StepStatus | ❌ |

| `progress` | number | ❌ |

| `failureReason` | string | ✅ |

| `estimatedSeconds` | number | ✅ |



> 분석 실패도 HTTP 200이다. `status: "failed"` + `failureReason`으로 판단한다.

> 



`failureReason` 값 (`analysis\_jobs.error\_code`)



| 값 | 화면 처리 | 재시도 |

| --- | --- | --- |

| `no\_public\_repo` | 안내만 — 재시도 버튼 숨김 | ❌ |

| `user\_not\_found` | 안내만 | ❌ |

| `rate\_limited` | 대기 시간 안내 (`retryAfter`) | 시간 후 |

| `github\_token\_invalid` | GitHub 재연동 강조 | 재연동 후 |

| `jd\_fetch\_failed` | 공고 URL 입력창 강조 | ✅ |

| `jd\_extraction\_failed` | 공고 URL 입력창 강조 | ✅ |

| `not\_a\_job\_posting` | "채용 공고가 아닌 것 같아요" | ✅ |

| `doc\_extract\_failed` | 첨부 파일 안내 | ✅ |

| `llm\_timeout` | "분석이 지연되고 있어요" | ✅ |



> `jd\_fetch\_failed`는 페이지 수집 실패, `jd\_extraction\_failed`는 LLM 추출 실패다. 재시도 성공률이 다르므로 구분한다.

> 



> 레포 일부만 분석 실패한 경우는 잡 실패가 아니다. `status: "completed"`로 응답하고 개별 레포의 `status`·`errorCode`로 전달한다.

> 



Response `410` — `run\_expired`



\---



\## GET /analysis-runs/{runId}/result



Response `200 OK`



```json

{

&#x20; "runId": "run\_abc123",

&#x20; "position": "Backend Developer",

&#x20; "companyName": "토스뱅크",

&#x20; "jdRequirements": \[

&#x20;   {

&#x20;     "id": "req\_003",

&#x20;     "category": "required",

&#x20;     "text": "Redis 등 캐시 시스템 운영 경험",

&#x20;     "displayOrder": 3

&#x20;   },

&#x20;   {

&#x20;     "id": "req\_007",

&#x20;     "category": "preferred",

&#x20;     "text": "대용량 트래픽 처리 경험",

&#x20;     "displayOrder": 7

&#x20;   }

&#x20; ],

&#x20; "mentionedRepoCount": 3,

&#x20; "matchedRepoCount": 2,

&#x20; "repositories": \[

&#x20;   {

&#x20;     "id": "r\_001",

&#x20;     "name": "project-a",

&#x20;     "fullName": "kim/project-a",

&#x20;     "description": "Spring Boot 기반 결제 API 서버",

&#x20;     "languages": \[

&#x20;       { "name": "Java", "ratio": 68 },

&#x20;       { "name": "TypeScript", "ratio": 21 }

&#x20;     ],

&#x20;     "topics": \["spring-boot", "redis"],

&#x20;     "stars": 12,

&#x20;     "forks": 3,

&#x20;     "commitCount": 142,

&#x20;     "userCommitCount": 138,

&#x20;     "pushedAt": "2026-06-14T09:12:00Z",

&#x20;     "status": "succeeded",

&#x20;     "errorCode": null,

&#x20;     "recommended": true,

&#x20;     "candidateSource": "both",

&#x20;     "recommendReason": "공고의 Redis 캐싱 경험과 직접 연관돼요.",

&#x20;     "matchScore": 92,

&#x20;     "matchedRequirementIds": \["req\_003", "req\_007"]

&#x20;   }

&#x20; ]

}

```



| 필드 | 타입 | null |

| --- | --- | --- |

| `runId` | string | ❌ |

| `position` | string | ❌ |

| `companyName` | string | ✅ |

| `jdRequirements\[].id` | string | ❌ |

| `jdRequirements\[].category` | JdCategory | ❌ |

| `jdRequirements\[].text` | string | ❌ |

| `jdRequirements\[].displayOrder` | number | ❌ |

| `mentionedRepoCount` | number | ❌ |

| `matchedRepoCount` | number | ❌ |

| `repositories\[].id` | string | ❌ |

| `repositories\[].name` | string | ❌ |

| `repositories\[].fullName` | string | ❌ |

| `repositories\[].description` | string | ✅ |

| `repositories\[].languages\[].name` | string | ❌ |

| `repositories\[].languages\[].ratio` | number | ❌ |

| `repositories\[].topics` | string\[] | ❌ |

| `repositories\[].stars` | number | ❌ |

| `repositories\[].forks` | number | ❌ |

| `repositories\[].commitCount` | number | ✅ |

| `repositories\[].userCommitCount` | number | ✅ |

| `repositories\[].pushedAt` | string | ✅ |

| `repositories\[].status` | RepoStatus | ❌ |

| `repositories\[].errorCode` | string | ✅ |

| `repositories\[].recommended` | boolean | ❌ |

| `repositories\[].candidateSource` | CandidateSource | ❌ |

| `repositories\[].recommendReason` | string | ✅ |

| `repositories\[].matchScore` | number | ✅ |

| `repositories\[].matchedRequirementIds` | string\[] | ❌ |



`jdRequirements`는 `category`로 그룹핑해 `displayOrder` 순으로 표시한다. 상한 20개.



`recommended: true`는 최대 5개다.



| `candidateSource` | 배지 |

| --- | --- |

| `rule\_filter` | 없음 |

| `portfolio` | 📎 포트폴리오 |

| `both` | 📎 포트폴리오 |



`mentionedRepoCount`는 포트폴리오에서 파싱한 GitHub URL 개수, `matchedRepoCount`는 그중 실제 레포로 매칭된 개수다. 두 값이 다르면 "포트폴리오에 언급된 3개 중 2개를 찾았어요"로 안내한다. 매칭 실패는 정상 상황이며 오류로 처리하지 않는다.



`repositories\[].status`가 `failed`면 카드를 회색 처리하고 `errorCode`별 문구를 띄운다. `matchScore`·`recommendReason`은 `null`이다.



| `errorCode` | 문구 | 재시도 |

| --- | --- | --- |

| `llm\_timeout` | "분석이 지연되고 있어요" | 자동 1회 |

| `parse\_failed` | "분석이 지연되고 있어요" | 자동 1회 |

| `input\_too\_large` | "정보가 부족해요" | ❌ |

| `no\_readme` | "정보가 부족해요" | ❌ |

| `github\_token\_invalid` | "GitHub 재연동이 필요해요" | 재연동 후 |



`status: "partial"`은 카드를 표시하되 `matchScore`를 낮게 반영한 상태다. 별도 문구는 띄우지 않는다.



Response 실패



| 코드 | reason |

| --- | --- |

| 409 | `not\_ready` |

| 410 | `run\_expired` |



\---



\## POST /interviews



`interview\_sessions`(`status='preparing'`)와 `session\_repositories`를 생성한다.



Request



```json

{

&#x20; "runId": "run\_abc123",

&#x20; "repositoryIds": \["r\_001", "r\_002"]

}

```



| 필드 | 타입 | 필수 | 상한 |

| --- | --- | --- | --- |

| `runId` | string | ✅ | — |

| `repositoryIds` | string\[] | ✅ | 5개 |



Response `201 Created`



```json

{

&#x20; "sessionId": "sess\_xyz789",

&#x20; "interviewId": "iv\_001"

}

```



Response 실패



| 코드 | reason |

| --- | --- |

| 400 | `no\_repository\_selected` · `invalid\_repository` · `too\_many\_repositories` |

| 409 | `session\_limit\_exceeded` |

| 410 | `run\_expired` |



\---



\## GET /interviews/{id}



5a2-v2(준비)와 5b-v2(진행)가 공유한다.



Response `200 OK`



```json

{

&#x20; "id": "iv\_001",

&#x20; "sessionId": "sess\_xyz789",

&#x20; "status": "in\_progress",

&#x20; "position": "Backend Developer",

&#x20; "companyName": "토스뱅크",

&#x20; "repositoryNames": \["project-a", "payment-service"],

&#x20; "currentTurn": 3,

&#x20; "totalTurns": 9,

&#x20; "remainingSeconds": 177,

&#x20; "turns": \[

&#x20;   {

&#x20;     "turn": 1,

&#x20;     "persona": "tech\_lead",

&#x20;     "question": "project-a에서 Redis를 캐시로 도입한 이유를 설명해주세요.",

&#x20;     "answer": "상품 조회 성능을 높이기 위해 캐시로 사용했습니다."

&#x20;   },

&#x20;   {

&#x20;     "turn": 2,

&#x20;     "persona": "domain\_lead",

&#x20;     "question": "금융권이라 캐시에 개인정보가 담기면 규제 대상이 됩니다. 데이터 민감도를 고려해보신 적 있나요?",

&#x20;     "answer": null

&#x20;   }

&#x20; ]

}

```



| 필드 | 타입 | null |

| --- | --- | --- |

| `id` | string | ❌ |

| `sessionId` | string | ❌ |

| `status` | InterviewStatus | ❌ |

| `position` | string | ❌ |

| `companyName` | string | ✅ |

| `repositoryNames` | string\[] | ❌ |

| `currentTurn` | number | ❌ |

| `totalTurns` | number | ❌ |

| `remainingSeconds` | number | ❌ |

| `turns\[].turn` | number | ❌ |

| `turns\[].persona` | Persona | ❌ |

| `turns\[].question` | string | ❌ |

| `turns\[].answer` | string | ✅ |



`totalTurns`는 `max\_turns`, `remainingSeconds`는 `planned\_duration\_sec - elapsed\_sec`다. 서버 시각 기준이므로 재연결 시 클라이언트 타이머를 이 값으로 덮어쓴다.



Response `404` — `not\_found`



\### status에 따른 화면 처리



| `status` | `currentTurn` | 화면 |

| --- | --- | --- |

| `preparing` | `0` | 5a2-v2 준비 화면 — `turns: \[]` |

| `in\_progress` | `1+` | 5b-v2 — `turns`로 복구 |

| `completed` | — | 5c-v2 리포트로 이동 |

| `abandoned` | — | "중단된 면접이에요" 안내 후 홈 |



`abandoned`인 경우 마지막 턴은 `answer: null`로 남는다.



\---



\## GET (Upgrade) /ws/interviews/{sessionId}



5a2-v2에서 연결하고 5b-v2까지 유지한다.



핸드셰이크 Request



```

GET /ws/interviews/sess\_xyz789 HTTP/1.1

Upgrade: websocket

Connection: Upgrade

Cookie: accessToken=<jwt>

```



Response `101 Switching Protocols`



인증은 핸드셰이크 시 1회 검증한다. 연결 유지 중 액세스 토큰이 만료되어도 연결을 끊지 않는다. 재연결 시에는 핸드셰이크를 다시 하므로, `onclose` 후 `GET /interviews/{id}`를 호출해 토큰을 갱신하고 `turns`를 확보한 다음 재연결한다.



\### 클라이언트 → 서버



```json

{ "type": "answerStart" }

```



```

(오디오 바이너리 — 일괄 1회 전송)

```



```json

{ "type": "answerEnd" }

```



오디오 포맷



| 항목 | 값 |

| --- | --- |

| 컨테이너·코덱 | `audio/webm; codecs=opus` |

| 샘플레이트 | 48000 Hz |

| 채널 | 1 (mono) |

| 최대 길이 | 180초 — 초과 시 `answer\_too\_long` |



\### 서버 → 클라이언트



```json

{ "type": "prepareStep", "key": "compose\_question", "status": "running" }

{ "type": "prepareCompleted" }

{ "type": "answerReceived" }

{ "type": "transcript", "text": "상품 조회 성능을 높이기 위해 캐시로 사용했습니다." }

{ "type": "thinking" }

{ "type": "evidenceCheck", "repository": "project-a", "file": "CacheConfig.java" }

{ "type": "question", "persona": "tech\_lead", "text": "TTL을 600초로 설정한 근거가 있나요?", "turn": 3 }

{ "type": "questionEnd" }

{ "type": "interviewEnd" }

{ "type": "error", "reason": "stt\_failed", "recoverable": true }

```



`question` 메시지 뒤에 TTS 오디오 바이너리가 이어지고, `questionEnd`로 종료를 알린다.



| type | 필드 |

| --- | --- |

| `prepareStep` | `key` (PrepareStepKey), `status` (StepStatus) |

| `prepareCompleted` | — |

| `answerReceived` | — |

| `transcript` | `text` (string) |

| `thinking` | — |

| `evidenceCheck` | `repository` (string), `file` (string) |

| `question` | `persona` (Persona), `text` (string), `turn` (number) |

| `questionEnd` | — |

| `interviewEnd` | — |

| `error` | `reason` (string), `recoverable` (boolean) |



`answerReceived`는 서버가 오디오 수신을 완료했다는 신호다. `answerEnd` 전송 후 이 메시지를 받기 전까지 업로드 중 상태를 유지한다.



`error.reason` 값



| reason | `recoverable` | 화면 처리 |

| --- | --- | --- |

| `stt\_failed` | `true` | 같은 턴 재답변 |

| `tts\_failed` | `true` | 질문 텍스트만 표시하고 진행 |

| `answer\_too\_long` | `true` | 같은 턴 재답변 |

| `question\_failed` | `true` | 자동 1회 재시도 |

| `prepare\_failed` | `false` | 준비 실패 안내 후 홈 |

| `repo\_unreachable` | `false` | "레포에 접근할 수 없어요" |

| `github\_token\_invalid` | `false` | GitHub 재연동 유도 |



`recoverable: false`면 서버가 세션을 종료하고 연결을 닫는다.



`evidenceCheck` 배너는 `evidenceCheck` 외 다른 서버 메시지를 수신하면 해제한다. 30초간 메시지가 없으면 타임아웃으로 해제한다.



핸드셰이크 실패



| 코드 | 상황 |

| --- | --- |

| 401 | `accessToken` 쿠키 없음 · 만료 · 변조 |

| 409 | 이미 종료된 면접 세션 · `already\_connected` |



> `already\_connected`는 이전 연결이 살아 있는 경우다. 새로고침 재연결을 막지 않도록 서버는 기존 연결을 종료한 뒤 신규 연결을 허용한다.

> 



\---



\## GET /interviews/{id}/report



Response `200 OK`



```json

{

&#x20; "interviewId": "iv\_001",

&#x20; "position": "Backend Developer",

&#x20; "positionLabel": "토스뱅크 백엔드 개발자",

&#x20; "totalScore": 74.5,

&#x20; "headline": "김개발님은 프로젝트 이해도가 돋보이는 지원자입니다.",

&#x20; "summary": "사용자가 직접 선택한 project-a · payment-service 두 레포를 근거로 질문이 구성되었습니다.",

&#x20; "scores": \[

&#x20;   { "key": "project\_understanding", "label": "프로젝트 이해도", "score": 88 },

&#x20;   { "key": "technical\_reasoning", "label": "기술적 사고력", "score": 79 },

&#x20;   { "key": "problem\_solving", "label": "문제 해결력", "score": 83 },

&#x20;   { "key": "communication", "label": "커뮤니케이션", "score": 80 },

&#x20;   { "key": "contribution\_clarity", "label": "기여도 명확성", "score": 76 },

&#x20;   { "key": "company\_job\_fit", "label": "기업·직무 적합성", "score": 82 }

&#x20; ],

&#x20; "agentFeedbacks": \[

&#x20;   {

&#x20;     "persona": "tech\_lead",

&#x20;     "tags": \["Architecture", "Trade-off"],

&#x20;     "strengths": \[

&#x20;       "project-a에서 Redis를 도입한 배경과 전체 아키텍처 변화는 명확하게 설명했습니다."

&#x20;     ],

&#x20;     "improvements": \[

&#x20;       "TTL을 600초로 설정한 근거는 다른 대안과 비교해 구체적으로 제시하지 못했습니다."

&#x20;     ],

&#x20;     "disagreementSubmitted": false

&#x20;   },

&#x20;   {

&#x20;     "persona": "hr\_manager",

&#x20;     "tags": \["협업", "기여도"],

&#x20;     "strengths": \[

&#x20;       "결제 모듈에서 본인이 담당한 범위를 구체적으로 설명했습니다."

&#x20;     ],

&#x20;     "improvements": \[

&#x20;       "팀원과의 의사결정 과정은 충분히 드러나지 않았습니다."

&#x20;     ],

&#x20;     "disagreementSubmitted": false

&#x20;   },

&#x20;   {

&#x20;     "persona": "domain\_lead",

&#x20;     "tags": \["도메인", "기업 적합성"],

&#x20;     "strengths": \[

&#x20;       "결제 도메인의 정합성 요구를 이해하고 있었습니다."

&#x20;     ],

&#x20;     "improvements": \[

&#x20;       "금융권 규제 관점의 고려가 부족했습니다."

&#x20;     ],

&#x20;     "disagreementSubmitted": false

&#x20;   }

&#x20; ],

&#x20; "coverage": {

&#x20;   "totalRequirements": 8,

&#x20;   "coveredRequirements": 5,

&#x20;   "uncoveredRequirements": \["Kafka 운영 경험", "Kubernetes 기반 배포 경험"]

&#x20; },

&#x20; "turns": \[

&#x20;   {

&#x20;     "turn": 1,

&#x20;     "persona": "tech\_lead",

&#x20;     "question": "project-a에서 Redis를 캐시로 도입한 이유를 설명해주세요.",

&#x20;     "answer": "상품 조회 성능을 높이기 위해 캐시로 사용했습니다."

&#x20;   }

&#x20; ],

&#x20; "repositoryNames": \["project-a", "payment-service"],

&#x20; "completedAt": "2026-09-01T15:20:00Z"

}

```



`scores`는 6개, `agentFeedbacks`는 3개 고정.



| 필드 | 타입 | null |

| --- | --- | --- |

| `interviewId` | string | ❌ |

| `position` | string | ❌ |

| `positionLabel` | string | ❌ |

| `totalScore` | number | ❌ |

| `headline` | string | ❌ |

| `summary` | string | ❌ |

| `scores\[].key` | ScoreKey | ❌ |

| `scores\[].label` | string | ❌ |

| `scores\[].score` | number | ❌ |

| `agentFeedbacks\[].persona` | Persona | ❌ |

| `agentFeedbacks\[].tags` | string\[] | ❌ |

| `agentFeedbacks\[].strengths` | string\[] | ❌ |

| `agentFeedbacks\[].improvements` | string\[] | ❌ |

| `agentFeedbacks\[].disagreementSubmitted` | boolean | ❌ |

| `coverage.totalRequirements` | number | ❌ |

| `coverage.coveredRequirements` | number | ❌ |

| `coverage.uncoveredRequirements` | string\[] | ❌ |

| `turns\[].turn` | number | ❌ |

| `turns\[].persona` | Persona | ❌ |

| `turns\[].question` | string | ❌ |

| `turns\[].answer` | string | ✅ |

| `repositoryNames` | string\[] | ❌ |

| `completedAt` | string | ❌ |



`positionLabel`은 회사명이 포함된 표시용 문구다. `coverage`는 `company\_job\_fit` 점수의 근거로 함께 표시한다.



\*\*탭 구조\*\*



| 탭 | 필드 |

| --- | --- |

| 종합리포트 | `headline` · `totalScore` · `summary` · `scores` · `coverage` |

| 면접관별 피드백 | `agentFeedbacks` |

| 면접 기록 | `turns` |



Response `202 Accepted` — 생성 중



```json

{ "status": "generating", "retryAfter": 3 }

```



Response `409` — `report\_unavailable` (진행된 턴 0개)



\---



\## POST /interviews/{id}/retry



원본 면접 세션의 `runId`·레포 조합을 복사해 새 세션을 만든다.



Request — 없음



Response `201 Created`



```json

{

&#x20; "sessionId": "sess\_new456",

&#x20; "interviewId": "iv\_002"

}

```



성공 시 `/interview/iv\_002/prepare`로 이동한다.



Response 실패



| 코드 | reason |

| --- | --- |

| 409 | `original\_not\_completed` · `repository\_unavailable` · `session\_limit\_exceeded` |

| 410 | `run\_expired` |



`repository\_unavailable`은 원본 레포가 삭제·private 전환된 경우다.



\---



\## POST /reports/{id}/feedback-disagreements



Request



```json

{

&#x20; "persona": "tech\_lead",

&#x20; "reasonType": "factual\_error",

&#x20; "comment": "TTL 근거를 설명했는데 반영되지 않았습니다."

}

```



| 필드 | 타입 | 필수 |

| --- | --- | --- |

| `persona` | Persona | ✅ |

| `reasonType` | ReasonType | ✅ |

| `comment` | string (최대 500자) | ❌ |



`reasonType` 화면 표기



| 값 | 표기 |

| --- | --- |

| `factual\_error` | 사실과 다름 |

| `insufficient\_basis` | 근거 부족 |

| `overly\_harsh` | 과도한 평가 |

| `unclear\_intent` | 질문 의도 불명확 |

| `other` | 기타 |



Response `204 No Content`

Response `409` — `already\_submitted`



제출 단위는 `(reportId, persona)`다.



\---



\## queryKey 매핑



| 경로 | queryKey |

| --- | --- |

| `GET /me` | `\['me']` |

| `GET /me/home` | `\['home']` |

| `GET /me/interviews?page=N` | `\['interviews', { page }]` |

| `GET /me/repositories?page=N` | `\['repositories', { page }]` |

| `GET /analysis-runs/{runId}` | `\['analysis-run', runId]` |

| `GET /analysis-runs/{runId}/result` | `\['analysis-run', runId, 'result']` |

| `GET /interviews/{id}` | `\['interview', id]` |

| `GET /interviews/{id}/report` | `\['interview', id, 'report']` |



계층 구조라 `\['interview', id]`를 무효화하면 하위 `report`까지 함께 무효화된다.



`POST /auth/refresh`는 queryKey를 갖지 않는다. 인터셉터 내부에서만 호출한다.



\## 캐시 무효화



| 시점 | 무효화 |

| --- | --- |

| `POST /interviews` | `interviews` |

| `POST /interviews/{id}/retry` | `interviews` |

| 면접 완료 (리포트 생성) | `home`, `interviews` |

| 피드백 이의 제출 | `interview(id).report` |

| `GET /auth/github/link/callback` 복귀 | `me`, `home` |

| `POST /auth/logout` | 전체 `clear()` |

| `POST /auth/refresh` 성공 | 없음 |

| `POST /auth/refresh` 실패 | 전체 `clear()` |



\---



\## 변경 이력



| 일자 | 변경 |

| --- | --- |

| 2026-09-08 | `stepKey` 4개 → \*\*7개\*\* (`doc\_extract` · `repo\_select` · `repo\_detail` · `jd\_fetch` · `jd\_extract` · `repo\_analyze` · `match\_score`) |

| 2026-09-08 | `agentRole` → \*\*`persona`\*\*, 값 `senior\_developer`/`manager` → \*\*`hr\_manager`/`domain\_lead`\*\* |

| 2026-09-08 | 에러 reason `jd\_parse\_failed` → \*\*`jd\_fetch\_failed`/`jd\_extraction\_failed`\*\* |

| 2026-09-10 | \*\*인증 방식 Redis 세션 + 쿠키 → JWT + HttpOnly 쿠키\*\* (Access 15분 / Refresh 14일) |

| 2026-09-10 | \*\*`POST /auth/refresh` 신규 추가\*\*, 리프레시 토큰 로테이션·재사용 감지 |

| 2026-09-10 | \*\*쿠키명 `session` → `accessToken` / `refreshToken`\*\*, OAuth `state` 저장 위치 세션 → `oauthState` 쿠키 |

| 2026-09-10 | \*\*인증 에러 reason 신설\*\*: `access\_token\_expired` · `access\_token\_invalid` · `refresh\_token\_invalid` · `account\_suspended` · `account\_withdrawn` |

| 2026-09-10 | 에러 reason `token\_invalid` → \*\*`github\_token\_invalid`\*\* (DEVON JWT와 구분) |

| 2026-09-10 | \*\*배포 CloudFront 통합\*\* — same-origin이므로 CORS 불필요, API base URL 상대경로 |

| 2026-09-10 | `interviewStatus`에 \*\*`preparing`\*\* 추가, `abandonedQ` 오타 수정 → `abandoned` |

| 2026-09-10 | `analysisStatus`에 \*\*`syncing`\*\* 추가 (`initial\_sync` 진행 중) |

| 2026-09-10 | `jdRequirements` `string\[]` → \*\*객체 배열\*\* (`id`·`category`·`text`·`displayOrder`) — `category` 그룹핑·커버리지 계산에 필요 |

| 2026-09-10 | `/analysis-runs/{runId}/result`의 `repositories`에 \*\*`fullName`·`description`·`topics`·`stars`·`forks`·`commitCount`·`userCommitCount`·`pushedAt`·`status`·`errorCode`·`candidateSource`·`matchedRequirementIds` 추가\*\*, `languages` `string\[]` → 비율 객체 배열 |

| 2026-09-10 | \*\*`mentionedRepoCount`·`matchedRepoCount` 추가\*\* (포트폴리오 레포 매칭 안내) |

| 2026-09-10 | \*\*`GET /me/repositories` 신규 추가\*\* ("내 레포 더 보기") |

| 2026-09-10 | `POST /interviews` `repositoryIds` \*\*상한 5개\*\*, `too\_many\_repositories` reason 추가 |

| 2026-09-10 | WS \*\*`answerReceived` 메시지 추가\*\*, `error`에 \*\*`recoverable`\*\* 필드 추가, 오디오 포맷 명시 |

| 2026-09-10 | WS `error.reason`에 \*\*`repo\_unreachable`\*\* 추가 |

| 2026-09-10 | 리포트에 \*\*`positionLabel`·`coverage` 추가\*\* |

| 2026-09-10 | SSE에 \*\*`progress`\*\* 이벤트, `GET /analysis-runs/{runId}`에 \*\*`progress`\*\* 필드 추가 |

