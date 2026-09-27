# BE 구현·검증 기록

구현 범위와 실제 실행 결과를 기록한다. 기능 요구사항은 각 features 문서와 task 문서를 따른다.

## 2026-09-27 — PR #45 GitHub 수집 리뷰 반영

관련 PR: [GitHub 수집 #45](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/45).
검토 기준은 #45 `cbd6bae`, 통합 검증 기준은 develop `aaee6a8`(#50·#67 병합 포함)이다.

### 변경 범위

- `integrations/github/client.py`: Retry-After를 우선하고 primary quota가 소진됐을 때만
  reset을 사용한다. 나머지 제한 응답에는 60초 대기를 전달한다.
- `pipeline/steps/repo_detail.py`: rate limit과 무효 토큰 모두 저장소 순회를 중단하고,
  확보한 데이터와 미호출 저장소의 중단 원인을 보존한다.
- `RepoDetail.repository_inaccessible`: 저장소 단위 languages 404를 명시적으로 전달한다.
  후속 수집에 성공하면 이를 해제한다. 503·timeout·README/브랜치 404만으로 제외하지 않는다.
- `pipeline/steps/repo_select.py`: 제외 후보와 첫 배치 밖의 정상 후보까지 모두 보존한다.
  eligible 후보에서 포트폴리오 최대 3개·기본 순위 최대 5개·기여도 최대 2개를 각각 고른 뒤
  중복 제거하며, 첫 배치의 `batch_no`·`batch_rank`·`selection_reason`을 별도로 표시한다.
  포트폴리오 언급은 필터를 우회하지 않는다. 접근 불가 재분류 시 수집 당시 배치 이력은 유지한다.
- 기여도 순서는 호출부가 근거로 제공한다. 정보가 없거나 후보가 겹쳐 비는 자리는 임의로 채우지
  않는다. 기존 pushed_at 기반 순위를 유지하며 task-10의 종합 점수·기여도 산정·DB 저장은 포함하지 않는다.
- 중복 `pipeline/initial_sync.py`·`workers/tasks/initial_sync.py`는 develop 골격으로 복원하고
  해당 구현 전용 테스트를 제외했다. 토큰 복호화·폐기 상태 영속화·초기 동기화·큐 연결은 #57에서
  통합한다. 이번 분리는 해당 경로의 롤백·부분 저장 문제를 수정 완료했다는 뜻이 아니다.
- 공개 API·DB schema·enum·의존성은 변경하지 않았다. 필요한 오류·선택 경계에 한국어 주석을 추가했다.

### 실행 결과

Windows, Python 3.12, uv locked 환경에서 실행했다. 외부 GitHub 응답은 MockTransport를 사용했다.

| 작업 디렉터리 / 기준 | 검증 | 결과 |
| --- | --- | --- |
| `backend`, 수정한 PR 브랜치 | 전체 pytest, 전용 PostgreSQL 연결 | 384 passed, skip 0 |
| `backend`, develop 통합본 | 전체 pytest, 전용 PostgreSQL 연결 | 385 passed, skip 0 |
| `ai`, develop 통합본 | 전체 pytest | 167 passed |
| `backend`, 양쪽 기준 | Ruff check·format, mypy app | 통과; format 180개, mypy 115개 파일 |
| 루트, develop 통합본 | 공통 계약 검사 | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |
| 회귀 검증 | 수정 전 실패를 확인한 뒤 동일 사례 재실행 | 제한 대기·토큰 중단·접근 증거·후보 보존·배치 규칙 통과 |
| 독립 검토 | 코드·테스트·DB nullable 계약·중복 범위 | 추가 수정이 필요한 결함 없음 |

PostgreSQL은 전용 로컬 테스트 DB의 임시 schema만 사용했다. 새 DB 쓰기 기능을 검증한 것은 아니다.
실제 GitHub 장애·rate limit을 유발하지 않았으며 서비스 전체 연결이나 배포 검증 결과도 아니다.
공통 계약 스크립트는 부분 형식 검사다.

### 후속 연결

- [#57](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/57)은 #45의 dataclass 반환값과
  저장 직렬화를 맞추고, 인증·작업 ID 중심 worker와 수집 기능을 함께 보존해야 한다.
- 상세 수집 호출부는 전체 후보 중 `filter_status='eligible'`이고 `batch_no=1`인 항목을 사용한다.
  기여도 근거 공급·종합 ranking·후속 page 저장은 task-10에서 연결한다.
- [#68](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/68)의 run partial/failed,
  Redis 제한 기록·SSE 연결은 별도 작업이다. README의 중요한 섹션 중심 축약 정책도 후속 범위다.

## 2026-09-28 — PR #57 공통 기반·GitHub 수집 통합과 리뷰 반영

통합 기준: develop `7e54047`, [#45](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/45)
`a327f64`, [#57](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/57) `5ba0d3c`.

### 변경 범위

- `shared/enums.py`의 Reason 한 곳에 OAuth 4개를 추가하고 develop의 상태·메시지 매핑,
  분석·면접·LLM 설정과 DB 제약을 보존했다. 오류 필드 안내·405 Allow·500 request ID와
  #57의 비밀값 제외·세션 쿠키·WebSocket 거부 처리를 함께 유지했다.
- #45의 dataclass·상세 수집·후보 선택과 #57의 공개 목록 검증·중복 제거·페이지 URL 제한을
  통합했다. 초기 저장은 `asdict()`를 사용한다. secondary 403과 헤더 없는 429 모두
  제한으로 분류하고 대기 시간을 전달한다.
- 이전 토큰의 401 처리 중 새 토큰이 저장되면 기존 작업 실패 확정 뒤 최신 유효 토큰을
  재확인해 후속 수집을 예약한다. 활성 작업 제약으로 중복을 막고 Redis에는 작업 ID만 넣는다.
- FE의 세션 종료 차단과 전체 페이지 로그인 전제를 한국어로 명시했다. 비 API 오류는
  원문 대신 고정 분류만 기록하며 정상 취소는 제외한다. 같은 탭의 로그아웃→재로그인을 검증했다.
- Vite의 프록시 연결 실패는 고정 문구로 기록하고 Caddy 런타임 로그의 URI에서는
  OAuth `code`·`state`를 제거하며 Referer도 제외한다. 실제 전달할 쿼리·쿠키·리다이렉트는 유지한다.
- `error-reasons.md`, 배포 문서, FE API 문서는 최신 공통 구조와 공개 콜백 경로에 맞췄다.
  develop의 면접 준비 재시도·WS 계약을 보존했다.

### 실행 결과

Windows·Python 3.12·uv locked 환경에서 전용 PostgreSQL DB와 Redis를 사용했다.
GitHub HTTP는 대체했으며 기존 사용자 서버·DB는 사용하지 않았다.

| 검증 | 결과 |
| --- | --- |
| `backend`: 전체 pytest | 501 passed, skip 0 |
| `backend`: Ruff check·format, mypy app | 통과 |
| `ai`: 전체 pytest | 167 passed |
| `frontend`: lint·build·화면 테스트 | 통과, 34 passed |
| 실제 API·DB·Redis·브라우저 통합 | 1 passed; 재연동·로그아웃 후 같은 탭 OAuth 재로그인 포함 |
| `frontend`: `npm run test:proxy` | 4 passed; 실제 Vite의 정상 전달·502 로그·일반 오류 기록 보존 |
| Caddy 설정·프록시 검사 | validate 통과; 공개/내부 콜백의 정상 전달과 502 로그의 code·state 제거 확인 |
| #64 `85c6a5d`의 면접 모듈·테스트를 별도 복사본에 적용 | 실제 PostgreSQL에서 32 passed; #57에 면접 구현은 추가하지 않음 |
| 전용 DB migration downgrade→upgrade·Alembic check | 통과, 모델과 차이 없음 |
| 공통 계약 검사 | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |

DTO 저장 실패와 재연동 경합은 수정 전 실패를 재현한 뒤 통과했다. 재연동 시점 세 가지,
실제 ARQ의 후속 작업 완료, 불완전한 목록 수집 시 기존 데이터 보존까지 확인했다.
공통 계약 검사는 전체 API 호환성 검증이 아니며, 이번 검증은 실계정 OAuth나 운영 배포 검증이 아니다.

### 후속 연결

- #45를 먼저 병합한 뒤 최신 develop에서 #57의 상태와 검사를 다시 확인한다.
- #64의 `current_user → User`, `get_db`, `app.state.redis: ArqRedis` 인터페이스는 유지한다.
  #64 router 연결과 하위 DB fixture 공용화는 해당 PR에서 진행하며, 다른 테스트의 격리 방식을
  확인하지 않고 fixture를 삭제하지 않는다.
- 프로세스 강제 종료 후 남은 running 작업의 운영 복구, #68 분석 run 연결,
  실계정 OAuth·운영 HTTPS 배포 검증은 이번 완료 범위에 포함하지 않는다.
- develop의 면접 준비 재시도는 직접 `api`를 호출한다. 401 뒤 상태 재조회까지 네트워크 오류로
  실패하면 전역 인증 처리를 거치지 않는 경로는 면접 연결 작업에서 보완한다.
