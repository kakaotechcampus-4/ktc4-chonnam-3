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

## 2026-09-28 — Task 9 Wanted 저장·재사용과 문서 Preview

기준: develop `7e54047`, 인증 선행 [#57](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/57)
`0bd0ccd`. [#44](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/44) `a0c1ba7`의
문서 추출기와 테스트를 재사용했다. 기존 develop의 Wanted 수집·요구사항 변환은 유지한다.
저장·동시성 선택은 [결정 기록](decisions/0001-task09-persistence.md)을 따른다.

### 변경 범위

- `POST /api/documents/preview`: 기존 세션 인증을 사용한다. PDF/DOCX/TXT/MD, 실제 파일
  20MiB 상한, 저장된 사용자 소유 문서 ID와 `succeeded/partial/failed` 응답을 구현했다.
  추출은 threadpool에서 실행하고 파일은 닫는다. 바이너리·claim row는 보관하지 않는다.
- 본문 및 PDF/DOCX 링크 대상에서 GitHub 저장소 목록을 먼저 얻는다. 이후 URL 주변·프로젝트
  헤딩 중심으로 보관 텍스트를 축약한다. 초기 설정 `DOCUMENTS_MAX_TEXT_CHARS=50000`은
  기존 정책 수치를 인용한 것이 아니라 이번 구현의 조정 가능한 기본값이다.
- 손상 파일·스캔 PDF·빈 파일은 추출 실패로 저장한다. NUL 제거·부분 추출·축약은 partial로
  표시한다. 손상 링크 메타데이터, DOCX 본문 구조, 본문에서 사용하지 않는 관계 및 PDF 간접
  URI를 보완했다. 예상하지 못한 코드·DB 오류는 공통 500으로 전달한다.
- `posting_service.get_or_fetch_posting()`은 Wanted URL을 정규화하고 7일 이내 성공본을
  재사용한다. 재수집 내용이 같으면 공고·요구사항 ID를 유지하고 확인 시각만 갱신한다.
  바뀌면 공고·요구사항을 한 transaction으로 새로 저장해 과거 run·면접 참조를 보존한다.
- 외부 HTTP 호출 뒤 짧은 PostgreSQL URL별 transaction lock에서 자료를 다시 확인해
  동시 요청의 중복 확정을 막는다. 수집·요구사항 변환 실패는 기존 성공 자료를 덮어쓰지 않는다.
  `raw_payload`에는 전체 HTTP JSON 대신 어댑터의 원문 그룹·출처 스냅샷을 저장한다.
- 새 `0002_posting_versions` migration에서 URL UNIQUE를 조회 인덱스로 바꾼다.
  기존 `0001_initial`은 수정하지 않았다. 여러 버전이 있으면 자료를 삭제하는 대신
  downgrade를 거절한다.
- Preview는 file만 받는 공개 계약을 유지하므로 JD 키워드 축약 설명을 수정했다.
  FE 실행 코드와 7단계 worker 구현은 이번 변경에 포함하지 않는다.

### 실행 결과

Windows·Python 3.12·uv locked 환경에서 전용 PostgreSQL 15와 Redis를 사용했다.
GitHub·Wanted HTTP는 mock fixture를 사용했으며 LLM은 호출하지 않았다.

| 검증 | 결과 |
| --- | --- |
| `backend`: 전체 pytest | 617 passed, skip 0 |
| 문서 API·추출·GitHub URL 집중 검증 | 98 passed; 네 형식·용량 경계·실제 세션/DB 저장·손상 문서 포함 |
| 공고 저장·재사용 집중 검증 | 14 passed; 최초/만료 동시 요청·이전 run/면접 참조·실패 보존·원자 rollback 포함 |
| 새 migration | 기존 행/FK 보존, 두 버전 저장, 위험한 downgrade 거절, 정상 downgrade→upgrade 통과 |
| Alembic 모델 비교 | `alembic check` 통과 |
| Ruff check·format, mypy app | 통과; format 213개, mypy 126개 파일 |
| 의존성 | `uv sync --locked --group dev` 통과 |
| 공통 계약 검사 | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |
| 독립 코드 검토 | DOCX 손상 구조·미참조 링크·PDF 간접 URI를 재현 후 수정; 추가 중요 결함 없음 |

신규 핵심 사례는 수정 전 실패를 확인한 뒤 다시 통과시켰다. 최초 전체 실행의 설정 비교 실패는
검증 runner가 `DATABASE_URL`을 불필요하게 주입한 원인이었으며, `TEST_DATABASE_URL`만 쓰도록
실행 환경을 고친 후 위 전체 결과를 확인했다. 공통 계약 검사는 부분 형식 검사이고,
실제 Wanted 사이트 응답·브라우저 E2E·운영 배포를 검증한 결과는 아니다.

### 후속 연결

- 실제 개발 환경에는 새 의존성을 동기화하고 `alembic upgrade head`를 적용해야 한다.
  검증용 DB 외의 사용자 DB에는 migration을 실행하지 않았다.
- Task 11에서 `get_or_fetch_posting()` 결과의 ID를 run에 고정하고
  `get_posting_requirements()`를 연결한다. 단계 상태·큐·SSE·문서 소유권을 포함한 run 생성은
  해당 작업에서 구현한다. 이 기록은 분석 전체 흐름의 완료를 뜻하지 않는다.
- 기존 지시로 보류한 FE 업로드 형식·자소서 제외 변경은 후속 작업이다. OCR, DOCX 머리말·꼬리말
  및 중첩 표 확장도 구현 범위 밖이며, Preview에서 JD/LLM을 호출하지 않는다.

### PR 준비 시 확인한 선행 변경과 보류

- 한국어 주석으로 파일 전용 요청·세션 소유권, 추출/DB 실행 경계, 실패 문서 저장,
  원래 URL 표기 보존, 7일 경계와 공고 버전 정렬 이유를 보완했다. 기능 동작은 유지했다.
  게시할 원본 작업 폴더에서 위 617개 전체 테스트와 Ruff·format·mypy·공통 계약 검사를 다시 통과했다.
- [#45](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/45) 최신 `e3cc0c7`의
  포트폴리오 필터 예외는 이 브랜치에 포함하지 않았다. 별도 임시 통합본의 기존 테스트는
  617개가 통과했지만, 문서 URL과 수집한 full_name의 대소문자 차이를 검사한 추가 사례는
  6개 실패했다. private 제외 확인 1개는 통과했다. 사용자는 이 검토 뒤 현재 Task 9의
  게시를 지시했으며, 후보 매칭 수정·관련 명세 문구·BE ADR `0001` 번호 중복은 후속으로 남긴다.
- [#77](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/77)의 요구사항 목록 기호·20개
  배분 변경과 [#74](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/74)의 도메인 판정도
  미반영이다. 병합 후 내용 비교·캐시 및 도메인 저장 연결을 확인해야 한다.
- develop 대상으로 PR을 작성하므로 미병합 #57의 기존 변경도 비교에 보인다. 이번 변경의
  기준은 `0bd0ccd`이며 선행 범위와 분리해 검토한다. 기존 `0001_initial`은 develop과 동일하다.
