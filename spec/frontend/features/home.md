# home

상태: 초안 — frontend/md/features/home.md에서 이관.

## 목표 + 화면 구성

로그인 직후 도착하는 화면. GitHub 레포 기반 프로필 요약과 최근 면접 기록을 보여주고 새 면접을 시작시킨다.

| 화면 | 경로 | 구성 |
| --- | --- | --- |
| 홈 | `/home` | 헤더(홈·모의면접 탭, GitHub 연동 배지, 아바타) + 프로필 패널 + 최근 면접 리스트 + `새 면접 시작` CTA |

프로필 패널은 `analysisStatus`에 따라 4가지 상태로 갈린다.

| `analysisStatus` | 화면 |
| --- | --- |
| `syncing` | 레포 수집 중 안내 (스피너), 폴링 |
| `no_repository` | 공개 레포 없음 안내 |
| `no_interview` | 첫 면접 유도 CTA 강조 |
| `completed` | 언어 비율 그래프 + 프로젝트 유형 태그 + 역할 요약문 + 최근 면접 리스트 |

`syncing`·`no_repository`·`no_interview`면 `analysis`는 `null`, `recentInterviews`는 `[]`다.

## 화면 이동 순서

```
/home
  ├─ [새 면접 시작]        → 공고·문서 입력
  ├─ 최근 면접 행 클릭      → 5c-v2 리포트
  ├─ 헤더 아바타 클릭      → 마이페이지
  └─ [GitHub 재연동] 배너  → /auth/github/link (403 github_token_invalid일 때만)
```

## API 연동

| # | 엔드포인트 | queryKey |
| --- | --- | --- |
| 9 | `GET /me/home` | `['home']` |

`/me`와 필드가 일부 겹치지만(`name`, `githubLinked`), 홈에서는 `/me/home` 하나만 호출한다.

### 응답 필드 → 화면 매핑

| 필드 | 화면 위치 |
| --- | --- |
| `name` | 헤더 인사 문구 |
| `githubLinked` | 헤더 "✓ GitHub 연동됨" 배지 |
| `repositoryCount` | 프로필 패널 레포 개수 |
| `analysisStatus` | 패널 상태 분기 |
| `analysis.basedOnRepoCount` | "레포 N개 기반" 문구 |
| `analysis.languages[]` | 언어 비율 그래프 (`name`, `ratio`) |
| `analysis.projectTypes[]` | 프로젝트 유형 태그 |
| `analysis.roleSummary` | 역할 요약 문단 |
| `recentInterviews[]` | 최근 면접 리스트 (`position`, `companyName`, `totalScore`, `completedAt`) |

### 에러

| 코드 | reason | 처리 |
| --- | --- | --- |
| 403 | `github_token_invalid` | 재연동 배너 노출, 패널은 마지막 캐시 유지 |
| 401 | 인증 계열 | 인터셉터 위임 |

### 캐시

| 시점 | 무효화 |
| --- | --- |
| 면접 완료 (리포트 생성) | `home`, `interviews` |
| `/auth/github/link/callback` 복귀 | `me`, `home` |
| `POST /auth/logout` | 전체 `clear()` |

`analysisStatus === 'syncing'`이면 폴링으로 재조회한다. **폴링 간격은 미정 — 팀 결정 필요 (`PENDING_TEAM`).**

## 상태 요구사항

| 상태 | 용도 |
| --- | --- |
| 없음 | 홈은 서버 상태 표시 전용. 로컬 상태 불필요 |

헤더의 탭 활성 상태는 라우터의 현재 경로에서 파생한다. 별도 상태로 두지 않는다.

## 검증 시나리오

- `analysisStatus` 4가지(`syncing`/`no_repository`/`no_interview`/`completed`) 각각 정상 렌더
- 최근 면접 행 클릭 → 리포트 이동
- `새 면접 시작` → 공고 입력 이동
- 403 `github_token_invalid` → 재연동 배너 노출, 패널은 마지막 캐시 유지
