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

[0019 프로필 역할 요약 복원](../../ai/decisions/0019-sprint1-profile-role-summary-restoration.md)에 따라 Sprint 1에서 기존 `analysis.roleSummary` 문자열의 역할 요약을 같은 문단에 표시한다. 일괄 기능 보류 안내로 대체하지 않으며 언어 그래프·프로젝트 유형·패널 상태는 유지한다. 기존 mock 문장은 실제 생성·검증 결과가 아니며 README·커밋만으로 개인 역할을 단정하는 예시는 구현 검증에서 근거 기준에 맞춰 확인한다. 이번 결정은 실제 생성·저장·화면 연결 완료를 뜻하지 않는다.

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

`analysisStatus === 'syncing'`이면 [현재 Home 구현](../../../frontend/src/features/home/Home.tsx)의 3초 간격 폴링을 유지하고, 다른 상태에서는 폴링을 중단한다. 간격 조정이 필요하면 실제 응답 시간·호출량을 확인해 구현 설정으로 조정한다.

## 상태 요구사항

| 상태 | 용도 |
| --- | --- |
| 없음 | 홈은 서버 상태 표시 전용. 로컬 상태 불필요 |

헤더의 탭 활성 상태는 라우터의 현재 경로에서 파생한다. 별도 상태로 두지 않는다.

## 검증 시나리오

- `analysisStatus` 4가지(`syncing`/`no_repository`/`no_interview`/`completed`) 각각 정상 렌더
- `completed`의 역할 문단은 기존 roleSummary 요약을 표시하며 서버의 요약 검증과 실제 응답 연결을 확인함
- 최근 면접 행 클릭 → 리포트 이동
- `새 면접 시작` → 공고 입력 이동
- 403 `github_token_invalid` → 재연동 배너 노출, 패널은 마지막 캐시 유지
