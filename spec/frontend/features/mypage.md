# mypage

상태: 초안 — frontend/md/features/mypage.md에서 이관.

## 목표 + 화면 구성

내 계정 정보와 완료한 면접 이력 전체를 보여준다. 로그아웃 진입점.

| 화면 | 코드 | 구성 |
| --- | --- | --- |
| 마이페이지 | — | `내 정보` 카드 + `면접 이력` 카드 + 하단 로그아웃 |

### 내 정보 카드

| 항목 | 표시 |
| --- | --- |
| 아바타 | 이니셜 또는 `avatarUrl` |
| 이름 | `name` |
| 가입일 | `joinedAt` (YYYY.MM.DD) |
| 아이디 | `loginId` |
| GitHub | `@{github.login}` + "연동됨 · 레포 {publicRepoCount}개" 배지 |

### 면접 이력 카드

헤더: `총 {totalCount}회` · `평균 점수 {averageScore}점`

행 컬럼: 일시 · 공고(회사명 + 직무) · 사용 레포(태그) · 점수(`{totalScore}`/100) · `리포트 보기 →`

`status === 'completed'`만 표시한다.

### 하단

- "계정을 삭제하려면 고객센터로 문의해주세요" 안내 텍스트 (API 없음)
- `로그아웃` 버튼 — 확인 모달 후 처리

## 화면 이동 순서

```
(전 화면) 헤더 아바타 클릭 → 마이페이지
   ※ 진입 시 헤더의 홈·모의면접 탭은 비활성

마이페이지
  ├─ 면접 이력 행 [리포트 보기] → 5c-v2 리포트
  ├─ [로그아웃] → 확인 모달
  │      ├─ 확인 → POST /auth/logout → clear() → /login
  │      └─ 취소 → 모달 닫힘
  └─ 헤더 [홈] → /home
```

## API 연동

| # | 엔드포인트 | queryKey |
| --- | --- | --- |
| 6 | `GET /me/profile` | `['profile']` |
| 10 | `GET /me/interviews` | `['interviews', { page }]` |
| 4 | `POST /auth/logout` | — |

`/me/profile`은 마이페이지 전용으로 새로 만든 엔드포인트다.

### GET /me/profile 응답

```json
{
  "name": "김개발",
  "avatarUrl": "https://avatars.githubusercontent.com/u/12345",
  "loginId": "kimdev",
  "joinedAt": "2026-03-12T04:20:00Z",
  "github": { "linked": true, "login": "kimdev-io", "publicRepoCount": 5 },
  "interviewSummary": { "totalCount": 3, "averageScore": 75 }
}
```

| 필드 | null | 비고 |
| --- | --- | --- |
| `name` | ❌ | |
| `avatarUrl` | ✅ | |
| `loginId` | ❌ | |
| `joinedAt` | ❌ | |
| `github.linked` | ❌ | |
| `github.login` | ✅ | `linked: false`면 `null` |
| `github.publicRepoCount` | ✅ | `linked: false`면 `null` |
| `interviewSummary.totalCount` | ❌ | 완료 0건이면 `0` |
| `interviewSummary.averageScore` | ✅ | 완료 0건이면 `null` |

### GET /me/interviews 응답 필드 → 행 매핑

| 필드 | 컬럼 |
| --- | --- |
| `completedAt` | 일시 |
| `companyName` | 공고 (회사명) |
| `position` | 공고 (직무) |
| `repositoryNames[]` | 사용 레포 태그 |
| `totalScore` | 점수 |
| `id` | `리포트 보기` 링크 대상 |

`total`·`averageScore`는 페이지와 무관한 전체 기준값이다.

### 미구현 — 협의 대기

| 화면 요소 | 상태 |
| --- | --- |
| `정보 수정` 버튼 | **대응 API 없음.** `users`에 희망 직무 컬럼이 없어 편집 대상이 없다. 협의 확정 전까지 버튼 비활성 또는 미노출 (`PENDING_TEAM`) |
| `희망 직무` 필드 | DB 컬럼 없음 |
| 공고 보조 문구 ("Java/Kotlin · 3년 이하") | `job_postings`에 기술 스택·경력 요건 필드 없음 |

## 상태 요구사항

| 상태 | 용도 |
| --- | --- |
| `isLogoutModalOpen` | 로그아웃 확인 모달 열림/닫힘 |
| `page` | 면접 이력 페이지네이션 (URL 쿼리와 동기화 권장) |

## 검증 시나리오

- `avatarUrl`/`github.login` null 케이스 처리
- 면접 이력 0건 empty state
- 이력 페이지네이션 동작
- 로그아웃 확인 모달 동작
- `정보 수정` 버튼 비활성/미노출 확인
