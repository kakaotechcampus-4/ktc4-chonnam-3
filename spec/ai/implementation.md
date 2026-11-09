# AI 구현·검증 기록


<a id="integrated-review-20261110"></a>
## 2026-11-10 #233 전체 리뷰 대응

현재 기준은 develop `d7ca24ea`와 [ADR 0049](decisions/0049-integrated-review-runtime-consistency.md)다. 아래의 최초 통합 게시·#185 제외 기록은 해당 과거 HEAD의 기록으로 보존한다. 현재는 #185·#234·#235를 포함한 최신 기반을 유지하고, 음성·질문 위치·리포트 계약의 자체 보완을 실행 코드에 연결했다. 활성화한 음성 대기 패치 15개와 안내 4개는 게시본에서 제거했으며 기존 #233 원본과 Git bundle에 보존했다. 다른 17개 PR에는 이번 수정을 게시하지 않는다.

### 변경 사항

- 공통 계약·BE 응답·FE 문서의 `answerMode`, 질문·리포트의 `mainIndex`·`followUpDepth`, `already_completed`와 STT 오류를 맞췄다. STT 불가 시 소켓을 유지하는 최신 정책과 FE 명시적 abandon을 보존했다. 질문 복구 ADR은 STT 0011과 구분해 공통 0012로 옮겼다.
- 실제 저장 모드·면접 상태·턴을 STT 전에 검사하고, 녹음 중 상태가 바뀐 경우도 재확인한다. 질문 이어가기는 공급자 오류의 구조화된 원인·허용값으로 판단한다. 선택 보완 검색의 예외는 안전한 실패 결과를 기록하고 질문 진행과 구분하며 실제 취소·저장 오류는 전파한다.
- 같은 공고 입력의 성공 도메인 분류와 최근 실패를 분리한다. 위험한 검색어가 유효한 답변 분석 전체를 무효화하지 않게 하되 실제 Tool 경계의 외부 전송 차단을 유지한다. 문서 claim 예약은 작성자의 절대 만료 시각과 소유 토큰으로 보호한다.
- Report v3·Score v3는 OCR/JD·코드·문서·도구 원문을 신뢰하지 않는 자료로 명시한다. 채점 입력의 근거·도구 결과·보완 자료·JD source notes는 각 턴이 실제 참조한 범위로 제한한다. `@release` 배포 식별자도 같은 v3 경계를 따른다. 기존 v2 본문·기존 버전의 입력 형태를 보존한다.
- 평가 CLI는 UTF-8 LF 지문 형식과 raw 지문을 구분한다. 기존 결과 덮어쓰기 방지·실패 종료 코드·실행 중 checkpoint를 추가했다. 현재 runtime manifest는 Director v8·답변 분석 v6·Report v3·Score v3를 사용한다. 과거 snapshot의 원시 바이트·기준 사례와 당시 manifest는 보존하며 출처 비교 색인과 이전 24개 참조의 실제 지문을 검증한다.
- 평가 컨테이너는 선택 코호트·원본 snapshot·형제 코호트를 같은 상대 구조로 읽기 전용 마운트한다. 제품 이미지에 평가 원문·정답을 넣지 않는다. 코드·프롬프트 이미지와 자료·결과 저장소를 구분한다.
- 기존 migration 0007·0008은 바꾸지 않고 0015에서 실제 음성 0006과 AI 0014를 합류한다. 0016은 CHECK 이름만 정렬한다. 0017은 검증한 프로필 생성 결과를 영속 전달 중 보존하고 0018은 claim lease를 추가한다. 프로필은 실행 600초·lease 630초로 정렬하고 입력·실행 지문이 같은 revision은 성공 요약을 재사용한다. 생성 후 Redis 장애도 유한 전달하며 오래된 소유자는 저장하지 못한다.
- 배포는 migration → 동일 릴리스의 11종 실행 프롬프트 등록 → API·worker 순서다. 프롬프트 등록 실패 뒤 소비자를 시작하지 않는다.
- JD 이미지의 HTTP 다운로드 30초와 전체 인식 360초를 분리했다. 부분 인식의 재시도는 URL별 영속 예약으로 동시 중복 실행을 막고, 동일 원문에서 시간당 최대 3회·60/120초 대기 및 1시간 주기를 적용한다. 실패·취소한 시도도 예산에 남기고 성공한 기존 본문은 보존한다.
- FE는 `crypto.randomUUID`가 없는 환경에서 안전한 난수 기반 UUID v4를 사용하고 네트워크 재확인에도 같은 요청 ID를 유지한다. 텍스트 답변 초과와 음성 초과는 저장 모드에 맞게 같은 턴을 다시 입력한다. 장치 점검의 5초 검증은 가상 시계로 경계를 고정하고 기존 제한을 유지한다.
- 현재 연결의 첫 질문을 받기 전에는 답변 시작을 제한한다. REST 조회 직후 늦게 도착한 WS 질문이 이미 시작한 녹음을 초기화하던 경합을 제거했다. mock 세션의 UUID도 같은 공통 생성기를 사용하며 실제 새 연결에서 답변 가능한 상태까지 검증한다.

### 검증 구분

이번 수정은 모의 공급자와 격리 PostgreSQL·Redis 및 브라우저 자동 검사를 사용한다. 실제 유료 공급자를 새로 호출하지 않으며 실제 사용자 재면접·사람의 품질 평가는 이번 회귀 검사에 포함하지 않는다. 중간 실패·해당 부분 재검증·최종 전체 검증은 구분해서 PR의 현재 HEAD 결과와 원래 리뷰 스레드에 기록한다. 이전 게시의 테스트 수치를 이번 결과로 합산하지 않는다.

### 게시본과 동일한 코드의 확인 결과

| 검사 | 실제 결과·범위 |
| --- | --- |
| AI 전체 | 986개 통과. 실제 공급자 호출이 없는 회귀 검사다. |
| BE 리뷰 집중 경로 | WS·모드·질문 재전달 57개, 리포트 113개, 최종 공고·이미지·도메인 소비자 184개, migration 11개 각각 통과. 부분 집합이 겹쳐 합산하지 않는다. |
| BE·AI 정적 | BE app·scripts Mypy 242소스, AI src·evals Mypy 31소스와 각 팀 Ruff·format 통과. |
| FE 전체 | 첫 질문 수신 경합과 UUID 대체 회귀를 포함한 169개 통과. lint·타입·빌드·프록시 4개도 통과했다. |
| 공통 계약 | 계약 테스트 63개 통과. 별도 스키마 2개·부분 OpenAPI·양성/음성 fixture 7개 검사 통과이며 전체 API 호환 검증을 대신하지 않는다. |
| 실제 Docker 평가 | 최종 런타임·평가 이미지를 새로 빌드하고 네트워크 없이 32·1·8건 입력 검증 통과. 중복 출력·과거 snapshot 누락·형제 코호트 누락은 의도한 종료 코드 2로 거절했다. 현재 코드·프롬프트 307파일과 이미지 지문이 같다. |
| 원본 보존 | 기존 작업 원본 1,229파일, canonical 사례 58개 및 과거 평가 원시 파일 60개 보존. 기존 report v2와 migration 0007·0008도 보존했다. |
| 중간 실행 구분 | FE 최초 전체는 167통과·1실패였고 첫 WS 질문 전 답변 시작 경합을 고쳐 위 169개로 재검증했다. 병렬 Windows BE 전체의 시간 초과를 관찰해 중단했으며 별도 진단에서 첫 공급자 진입 전 10초 대기 초과를 재현했다. 해당 준비 경로 단독 2개는 통과했고 제한을 늘리지 않고 Linux 전체와 최종 CI를 따로 확인한다. |
| Linux 준비 환경 | 최초 host.docker.internal 주소는 테스트의 로컬 DB 안전 검사에서 거절됐다. 테스트를 완화하지 않고 별도 PG15·Redis7과 같은 loopback namespace를 사용하는 최종 환경으로 구분했다. |

최종 전체 검증과 원격 CI는 [#233](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/233)의 현재 HEAD 본문·종합 리뷰에서 통과·실패·미실행을 구분한다. 이 표의 자동 검증을 실제 공급자 품질·실사용·사람 검수 완료로 확대하지 않는다.

- 첫 원격 AI 검사는 985통과·1실패였다. AI 전용 환경에 없는 pytest-asyncio를 신규 테스트가 사용한 것이 원인이었다. 기존 AI 테스트처럼 `asyncio.run`으로 같은 취소·checkpoint 검증을 실행하게 바꾸고 플러그인 자동 로딩을 끈 환경에서 986개를 재통과했다. 제품·의존성·lock 파일은 바꾸지 않았다.
- Linux BE 최초 실행은 754통과·1실패에서 멈췄다. 프로필 작업의 실효 제한은 600초로 같지만 기존 테스트는 명시 등록 전의 `None`을 기대했다. 프로필 등록·명시 600초·lease 630초를 필수 확인하도록 고치고 기존 준비·리포트 1800초 검증을 유지해 4개를 재통과했다. 이어지는 전체 사례 검증은 통과한 nodeID와 나머지 목록의 합집합으로 확인하고 중복 수치를 합산하지 않는다.

---

<a id="integrated-publication-20261110"></a>
## 2026-11-10 기존 17개 PR의 단일 통합 게시

- 사용자 요청에 따라 #212~#219·#222~#230의 신규 구현과 최신 리뷰 수정을 최신 develop에 통합한다.
  기존 PR의 브랜치·본문·상태는 보존하며 새 통합 PR을 추가한다.
- 단일 게시 범위의 결정은 [0047](decisions/0047-integrated-publication-without-voice-input.md)에 기록했다.
  다른 팀원의 미병합 #185 기본 구현은 제외한다. 음성 전용 DB 변경·STT 수신·위치 보강이 필요한
  이번 작업의 추가 코드와 대응 테스트·계약은 `backend/patches/ai-service-voice185/`에 원문 지문과 함께 보존한다.
- 공통 설정·Model Gateway·Director·레포 원문 수집·공식 자료·평가 실행·리포트·질문 복구의
  17개 PR 내부 의존성은 실제 코드와 테스트로 연결한다. 최초 분리 PR의 비활성 패치 보관만으로
  실행 완료를 주장하지 않는다.
- 자체 0007은 실제 0005 기반에 연결하고 0008~0014 체인은 유지한다. 가짜 0006은 추가하지 않는다.
  나중에 #185가 반영되면 실제 두 분기와 보류 보완을 함께 재검증한다.
- 최신 develop의 이벤트·SAVEPOINT·준비 재등록 검증을 유지한다. 준비 복구는 공통 keyset scanner의
  공정성과 claim 재검사를 유지하면서 기존 PAGE_SIZE/MAX_PAGES 설정을 전달한다.
- 기존 캐시 분석값을 유지한 `_source_inventory` 추가와 JD 본문·ID의 명시적 인자를 검사한다.
  임시 자막 표시와 무관한 녹음 복구 검증은 녹음 상태·마이크 수·현재 턴의 저장 표식으로 확인한다.
  검증 조건 삭제·테스트 제외·시간 제한 확대로 통과시키지 않는다.
- 로컬 완전 개발본과 #185를 제외한 실제 게시본의 검사 결과를 구분한다. 실제 모델·STT·Vision·TTS·
  Tavily API는 이번 통합 작업에서 호출하지 않으며 모의 공급자와 격리 PostgreSQL·Redis를 사용한다.
- 최종 실행 결과와 원격 CI는 이 항목의 검증 표 및 새 통합 PR에 기록한다. 초기 실행에서 확인한
  테스트 계약 불일치와 환경 설정 오류를 최종 통과 수치에 섞지 않는다.


### 단일 통합 PR 게시 전 검증

| 범위 | 실제 결과와 한계 |
| --- | --- |
| 게시본 AI 전체 | pytest 972개 통과. 실제 모델 API를 호출한 결과가 아니다. |
| 게시본 BE 정적 | 전체 Ruff·format 통과, app·scripts Mypy 236소스 통과. |
| 게시본 BE 최초 전체 | 934개 통과·10개 실패에서 중단. 캐시 metadata·위치/모드·JD fixture와 페이지 설정 호환성의 불일치를 확인했다. |
| 해당 보완의 재검증 | 캐시 경계 파일 16개, WS·준비 응답 3개, 평가 기회 파일 37개, 수집 예산 파일 8개, 준비 재등록·공통 스캔·lease 34개 각각 통과. 범위가 겹쳐 합산하지 않는다. |
| 게시본 BE 최종 전체 | 격리 PostgreSQL·Redis로 재실행 중. 최종 HEAD의 전체 검사와 원격 CI 결과는 새 통합 PR 검증 표에서 확인한다. |
| 게시본 FE | lint·타입·빌드·프록시 검사 통과. 최초 MSW 161개 통과·1개 실패 후 녹음 상태 검사를 교정했고, 최종 전체 162개 통과. |
| 경계·원문 | #185 대기 패치 12개를 독립 적용·목표 지문 확인. 원본 1229개 파일과 평가 snapshot 원시 바이트 보존. |
| 실제 공급자·실사용·사람 검수 | 이번 통합 검증에서는 미실행. 모의 공급자, 격리 테스트 DB와 Redis를 사용했다. |



### #233 게시 후 #185 경계 회귀 보완

- 전체 재실행에서 2612개 통과·14개 실패·1개 별도 마이그레이션 검사의 미설정을 확인했다.
  실패는 음성 전용 HTTP/WS 검사와 제외한 STT 예제 키의 필수 존재 검사였다.
- VOICE HTTP 회귀 9개와 음성 입력 helper 회귀 9개를 없애지 않고 대응 코드가 필요한 패치에 보존했다.
  현재 TEXT·인증·소유권·과금 차단과 실제 파서 검사를 별도로 실행하며, 미래 패치 적용 뒤에도 유지한다.
- 비공개 연결 값 15종의 빈 값 검사는 유지한다. 현재 필드 13종의 필수 존재와 이후 STT 2종의 필수 존재를 구분한다.
  미설정 STT 키에도 실제 값이 들어오면 거절하고 오류에 값을 노출하지 않는 회귀를 추가했다.
- 해당 수정 후 TTS 범위 21개, WS 파서 3개, 설정 파일 전체 32개가 각각 통과했다.
  완전 개발본에서는 TEXT 6개·VOICE 9개 및 입력 helper 기존 9개·파서 3개가 함께 통과했다.
- 전용 `TASK11_MIGRATION_URL` 검사는 일반 pytest의 미설정 skip과 별도의 migration CI 통과를 구분한다.
  최종 전체 검사·CI 상태는 #233의 현재 HEAD 검증 표를 따른다.


<a id="review-round2-20261109"></a>
## 2026-11-09 재리뷰 후속 수정과 검증

- 범위: #213, #219, #222~#230. #212의 확인 완료와 #216~#218의 이전 수정 기록은 보존한다.
- 원본 전체 작업 1199개 경로는 원시 바이트 지문으로 보존했다. 최신 develop 6caa681a와 별도
  통합 환경을 만들고, 기존 PR 번호와 develop base를 유지하며 신규 수정만 분리한다.
- 공통 기반: 기존 600초 timeout·과거 lease 경로와 새 1770/1800초 작업 예산을 구분한다.
  프롬프트 버전 검사와 모델 출력 검증은 유지하고 fixture·worker 등록 검사를 실제 계약에 맞춘다.
- #222: log_json·request_size의 실제 정의와 활성 호출을 맞추고 문자열 traceback도 정제한다.
  초기화 원문 예외·비밀값·절대경로를 공개 로그에 남기지 않는다. 0042·0044의 색인은 이 PR에 둔다.
- Director: 지원하지 않는 버전은 모델 호출 전 거절하고 v7·v8만 Plan에 복구 피드백을 받는다.
  Review는 독립 검증하며 원문·실제 ID·호출 상한을 유지한다.
- 질문 복구: 진행 상태를 소유자 GET으로 복원하고 같은 requestId를 재확인한다. 영구 오류를 제외하고
  보완 조회 결과를 보존하며 오래된 성공 요청이 현재 연결을 교체하지 못하게 한다.
- 화면·음성: 유한 질문 대기, 실제 MSW 복구, stale 텍스트 응답, voice 전용 재생·합성,
  예산의 기간·근거와 확실한 거절/불명확 소비 정산, timeout 냉각을 보완한다.
- 레포: 안내문·enum 개수/문자·요청 바이트를 함께 제한한다. 전체 inventory는 원문·SHA·지문을
  유지해 안정적으로 저장하고 매턴 context에는 참조·요약만 둔다.
- 평가·리포트: 최신 canonical 29사례와 과거 snapshot 원시 바이트를 유지한다. 과거 계약은 명시 opt-in,
  LinkedRequirement는 기존 3필드이며 누락·null·잘못된 JD 연결은 구분해 검증한다.
- 공식 자료: 0046에 따라 수집 페이지/선택 절을 분리하고 정책 식별·한영 질의·부분 실패·감사를 보완한다.
  실제 Tavily extract는 2회·1크레딧, 7개 catalog 중 4개 저장 성공, 3개는 요청 절 누락으로 미채택했다.
  성공: python-3.12-task-groups, mdn-http-429, naver-commerce-auth, fhir-r4-security.
  미확인: kftc-openbanking-balance, steam-authentication, gtfs-stop-times.
- 로컬 통합 검증: AI·BE·FE, 전용 PostgreSQL·Redis 및 실제 source 크기 경계 검사를 사용한다.
  이 회차에서 GPT·STT·TTS 공급자를 새로 호출하지 않았다. 검사별 실제 명령·HEAD·수치와 남은 의존성은
  각 PR 종합 리뷰에 구분해 남기며, 서로 겹치는 테스트 수를 합산하지 않는다.
- 선행이 없는 게시본은 필요한 구현·호출·회귀를 원자적 후속 패치로 보존한다. 패치의 준비와 기능
  활성화를 구분하며 실제 선행 적용·마이그레이션·현재 HEAD CI 검증 전에는 완료·병합 가능으로 보지 않는다.


## 2026-11-07 — 최종 AI 서비스 통합의 로컬 구현

### 범위와 원본 보존

사용자가 전체 sprint의 최종 서비스로 실행할 수 있도록 AI 파트의 구현을 요청했다.
`develop@13bd98e4af74c977c2db6e367c232fe6209b979b`에서
`feature/ai-final-service-20261107`와 별도 worktree를 구성했다.
선행 #153·#164·#165·#167·#174·#175·#183·#185의 내용을 로컬에서 결합해 연결을 검증하며,
선행 구현을 이번 신규 작성분이나 이미 develop에 병합된 내용으로 표시하지 않는다.
이번 요청은 자동 commit·push·PR 생성·다른 PR 병합의 승인으로 확대하지 않았다.

초기 기능·설계·task·testing 문서는 수정하지 않는다.
추가 정책과 협업 영향은 [ADR 0031 초안](decisions/0031-final-service-runtime-boundaries.md)에,
현재 구현과 검증 범위는 이 절 한 곳에 기록한다.
ADR은 Proposed이며 사용자 구현 요청과 FE·BE·AI 전체 팀의 공유 계약 승인은 구분한다.

### 이번 신규 실행 연결

| 구간 | 실제 연결과 보존 경계 | 주요 코드 |
| --- | --- | --- |
| 공고 도메인 | 공고 수집 뒤 기존 AI 도메인 분류를 연결한다. 원문 근거를 검사하며 실패·근거 부재의 `etc`를 실제 업종의 확정값으로 해석하지 않는다 | `backend/app/features/analysis/posting_domain.py`, `posting_service.py`, `app/llm_tasks/domain_category.py` |
| 레포 원문 | 실제 트리에서 읽을 경로를 선정하고 수집한다. 큰 파일은 원래 줄 범위를 가진 구간으로 나누며, 모델·저장·후속 조회에서 같은 버전과 위치를 사용한다 | `backend/app/features/interview/repository_sources.py`, `source_segments.py`, `app/integrations/github/snapshot.py` |
| 구문 보조 | 전체 Python·JSON·TOML 파일의 정적 구조를 보조한다. 다른 텍스트와 부분 구간은 원문으로 처리하고 전용 해석 부재를 명시한다. 코드를 실행하지 않는다 | `ai/src/devon_ai/source_readers.py`, `llm_tasks/repo_deep.py` |
| 문서 원문 | preview와 별개인 추출 snapshot, 파일·텍스트 해시, 페이지·줄·가능한 좌표와 한계를 저장한다. Native와 Vision 전사를 병합하고 VLM 생성 설명은 별도 보존한다 | `backend/app/features/documents/source_snapshot.py`, `vision_processing.py`, `service.py`, `app/integrations/extract/pdf.py` |
| 문서 선택 | 업로드의 `docType`과 분석 요청의 선택적 `coverLetterDocumentId`를 추가해 두 문서를 명시 선택한다. BE는 소유자·종류·추출 실패를 검사하며 자소서 입력 변경을 중복 판정에 반영한다 | `backend/app/features/documents/router.py`, `app/features/analysis/run_schemas.py`, `service.py`, `app/db/models/analysis.py`, `frontend/src/features/analysis/JobInput.tsx` |
| 문서 Claim | 선택 문서만 면접 준비 중 호출한다. 원문·추출 prompt 버전, 진행·실패·정상 빈 결과를 구분하고 원문 위치를 저장한다. 이전 Claim을 보존하며 현재 입력 집합과 과거 참조 복원을 구분한다 | `backend/app/features/documents/selection.py`, `claims.py`, `app/llm_tasks/doc_claims.py`, `app/db/models/document.py` |
| 보완 근거 | 문서 Claim·시각 설명·외부 자료를 종류·버전·위치·한계와 함께 Context에 넣는다. 문서별·외부 자료별 입력 예산을 배분하고 과거 질문의 인용 검사에는 별도 archive를 사용한다 | `backend/app/features/interview/supplemental_sources.py`, `agent_context.py`, `answer_context.py`, `ai/src/devon_ai/contracts.py` |
| 외부 검색 | 검증된 T3 요청을 단일 Director Tool에서 Tavily Search·Extract로 실행한다. 공식 출처 범위, 금지 질의, 작업·면접 예산, 원문과 검색 상태·캐시를 기록한다 | `backend/app/features/interview/external_knowledge.py`, `app/integrations/search/tavily.py`, `app/db/models/external_source.py`, `ai/src/devon_ai/llm_tasks/answer_analysis.py` |
| 질문·평가 기회 | 확정 질문의 `evaluation_keys`를 추적해 다음 배정을 계산하고 같은 계약을 재검증한다. 질문 배정과 답변 관찰·실제 점수는 구분한다 | `backend/app/features/interview/evaluation_coverage.py`, `question_structure.py`, `director_service.py`, `ai/src/devon_ai/agents/director/runtime.py` |
| 음성·재청취 | 기존 STT·WS 연결에 확정 질문의 TTS URL과 인증된 음성 조회·캐시를 연결한다. 명시 재청취는 답변 저장·턴 소비와 분리하고 정상 모름 답변은 유지한다 | `backend/app/features/interview/question_audio.py`, `question_replay.py`, `router.py`, `ws.py`, `app/integrations/tts/google.py` |
| 무료 TTS 예산 | persona별 음성 설정과 프로젝트·월 문자 예약을 사용한다. 실제 잔여량을 확인한 명시 초기화 없이는 합성하지 않으며 Redis 재시작을 무료량 복구로 간주하지 않는다 | `backend/app/features/interview/tts_budget.py`, `backend/scripts/initialize_tts_budget.py` |
| 리포트·프로필 | 로컬에 결합한 선행 리포트·프로필 경로를 재사용한다. 새 근거·평가 기회와 미관찰 상태의 전달을 보완하며 누락을 임의의 긍정 평가로 채우지 않는다 | `ai/src/devon_ai/llm_tasks/report.py`, `report_score.py`, `backend/app/features/report/service.py` |
| 평가 실행 | 기존 사례·채점기 자료에 실행기와 BE bridge·CLI를 연결한다. 입력과 정답을 분리하고 검수 상태·실패·시도·해시·token·지연을 기록한다 | `ai/evals/eval_runner.py`, `backend/scripts/ai_eval_bridge.py`, `run_ai_evaluation.py` |
| 저장·설정 | 문서 근거·자소서 선택·외부 자료를 위한 모델 및 후속 마이그레이션을 추가한다. 선택 공급자의 환경 설정과 LLM reasoning effort 전달을 실제 호출 경계에서 검증한다 | `backend/migrations/versions/0007_ai_source_provenance.py`, `backend/app/core/config.py`, `app/integrations/llm/client.py` |

### 유지한 동작과 새 협업 계약

- `documentId`는 계속 포트폴리오를 뜻한다. 포트폴리오의 레포 추천 URL 힌트에 자소서 URL을 섞지 않는다.
  자소서를 생략한 기존 요청의 fingerprint 형식도 유지해 진행 중인 기존 작업의 중복 등록을 막는다.
- FE는 파일 업로드에 `docType=cover_letter|portfolio`를 전달하고, 실패해 제외한 문서의 ID는 분석 요청에 넣지 않는다.
  기존 화면의 자소서 PDF/DOCX·포트폴리오 PDF 지원은 유지한다.
  Vision API 경로의 추가 형식 지원을 화면의 공식 지원 확대나 모든 형식 검증 완료로 표현하지 않는다.
- 문서 Claim과 생성 시각 설명, 검색 자료는 실제 개인 기여·성과의 확정 증거가 아니다.
  근거 부족·추출 실패·예산 초과는 지원자 능력의 감점 근거로 바꾸지 않는다.
- 새 공개 계약은 `docType`, `coverLetterDocumentId`, 확정 질문 음성 조회 경로와 관련 WS 필드다.
  OpenAPI·FE 타입·BE 실행의 로컬 정합성과 팀의 최종 계약 승인을 구분하며 관련 팀 검토가 필요하다.
- [#195](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/195)의 공개 점수 nullable 확대는 합의 완료로 기록하지 않는다.
  내부 `not_evaluated` 보존과 공개 응답의 표현 정책은 별도 확인 대상이다.

### 실행 환경과 검사 구분

검증은 원본 서비스 환경을 변경하지 않는 worktree, Python 3.12, 격리 PostgreSQL 17·Redis를 사용한다.
BE 실행·타입 검사에는 이 worktree의 `backend`·`ai/src`를 명시한다.
원본 editable AI 패키지를 섞은 검사는 현재 소스 전체의 검증으로 사용하지 않는다.
FE는 기존 의존성을 재사용하고 공식 배포 해시를 확인한 별도 Node 환경에서 검사한다.

| 종류 | 검증 대상 | 최종 실행 결과 |
| --- | --- | --- |
| 결정적 AI 검사 | 계약·근거 검증, source reader, 평가 실행 경계, 리포트·Director 회귀 | 최종 통합 소스의 AI 전체 680 passed |
| 실제 PostgreSQL·Redis | 선택 문서·Claim·원문·외부 자료 저장, 동시성·소유권·캐시·음성 예산 | BE 전체 2,135개 고유 사례 통과. agents 393, features 836, 공통 905+전용 migration 별도 1. PostgreSQL 17 전용 DB와 Redis DB13/14/15를 분리 |
| 외부 API 대역 | HTTP transport 대역으로 Tavily·Vision·Google TTS·LLM 요청과 오류를 검증 | BE 검사에 포함. SSE 완료·중단·Unicode·예산 회귀, OAuth quota 프로젝트 헤더 포함. 실제 음질 검사와 구분 |
| FE 브라우저·MSW | 두 문서의 실제 화면 업로드·분석 요청, 기존 인증·면접·오류 처리 회귀 | 파일 고정·새 서버·1 worker의 전체 135 passed |
| 정적 검사·build | AI/BE Ruff·format·mypy, FE lint·production build, 공유 계약 검사 | AI/BE Ruff·format·mypy(22/198 source), FE lint/build, Docker build·이미지 내부 manifest 생성 통과. 계약 schema 2개·부분 OpenAPI·fixture 7개 통과 |
| 실제 공급자 | 실제 LLM·GitHub·STT·Vision·Google TTS·Tavily와 전체 서비스 연결 | Elice LLM 합성 입력 9개 task의 호출·계약 검증 성공. 최종 리포트 확장 뒤 질문·답변·리포트 3사례 재실행 성공(검수 전 품질 분모 0). Tavily Search→Extract 1원문·5,816자 성공. 실제 GitHub·STT·Vision·Google TTS 인증·품질은 이번 실행에서 미검증 |

자소서 API는 먼저 신규 필드 거절을, FE는 문서 종류 누락과 다른 자소서의 캐시 충돌을 재현한 뒤 수정했다.
실제 PostgreSQL의 선택 ID 저장·소유권·종류·실패 거절·입력 중복 판정과 MSW 화면 흐름은 별도 검사다.
개발 서버 HMR로 동일 모듈의 인스턴스가 달라진 중간 FE 실행은 최종 회귀 수치에 합산하지 않는다.

통합 검증 중 다음 실제 회귀를 확인해 보완했다.

- SHA를 먼저 확보한 뒤 GitHub 호출 제한·토큰 오류로 중단된 레포가 L1 모델 입력에 들어가
  원래 수집 오류가 `llm_failed`로 바뀌는 문제를 수정했다. 중단 원인과 확보한 SHA·필드는 보존하고
  해당 레포의 새 L1 호출은 하지 않는다. 정상 수집 레포의 분석은 계속 진행한다.
- 기존 저장 경로는 빈 `evaluation_keys`·`external_queries`를 생략해 옛 JSONB 필드 수를 보존한다.
  새로 선언한 값은 저장하며, 옛 저장값의 decode 복원과 새 확장의 유실 방지를 따로 검증했다.
- 스트리밍의 잘린 마지막 프레임·모순된 실패 상태를 성공으로 발행하지 않고,
  JSON 문자열 안의 Unicode 구분자는 SSE 줄 경계로 자르지 않는다.
- 사용자 OAuth TTS 요청에는 예산 대상 quota 프로젝트 헤더를 전달한다.
  이 HTTP 대역 검사는 Cloud 권한·음성 품질·실제 무료 잔여량의 검증과 별개다.

최종 Linux 이미지도 별도로 빌드하고, 테스트용 OAuth 설정을 주입한 로컬 컨테이너에서
`/api/health` 200, 실제 테스트 PostgreSQL `SELECT 1`, Redis `PING`, ARQ worker 기동과
두 reaper 작업의 실행을 확인했다. 실제 GitHub 로그인이나 유료 공급자 검증으로 해석하지 않는다.
전용 DB에서 마이그레이션 최초 upgrade, model/schema 차이 없음, 0007 downgrade·재upgrade도 통과했다.

최종 BE XML과 전체 collection의 2,135개 사례를 대조해 누락·추가·미통과가 없음을 확인했다.
공통 첫 실행의 1 skip은 전용 `task11_migration_test` DB가 없었기 때문이며,
새 전용 DB에서 해당 사례를 별도로 실행해 통과했다. 전체 XML의 skip과 별도 pass를 구분해 보존했다.
매 collection마다 `uuid4()`로 생성되는 두 '알 수 없는 ID' 매개변수만 함수·UUID 형식으로 대응시켰다.
나머지 매개변수 ID는 그대로 대조했다. 중간 실패·중단 결과를 통과 수에 합산하지 않았다.

### 배포·운영 전에 남은 확인

로컬 실행 시 `backend`에서 다음 순서로 설정한다. 명령은 대상 환경 DB·Redis를 사용하므로
실행 전 `.env`의 연결 대상을 확인한다. 이번 통합에서는 별도의 테스트 DB에서만 수행했다.

1. `uv run alembic upgrade head`로 저장 구조를 반영한다.
2. 필요한 `score_criteria`·`domain_question_frames`와 모델 prompt를 환경에 준비한다.
   `uv run python -m scripts.seed_all`의 새 rubric은 비활성 초안이며 자동으로 활성화하지 않는다.
   검수한 6개 rubric과 도메인 프레임이 실제 활성인지 확인한다. 누락 시 임의 기준을 만들지 않고 실패한다.
3. `.env`의 실제 모델과 Gateway 제한을 정하고
   `uv run python -m scripts.configure_ai_runtime --output report/runtime-manifest.json`으로
   9개 task의 모델·본문·상한 manifest를 먼저 확인한다.
   해당 버전과 본문을 사용할 환경에서는 같은 명령에 `--apply`를 추가해 DB에 명시 등록·활성화한다.
   기존 version의 본문·모델이 다르면 충돌이며 덮어쓰지 않고 새 version으로 등록한다.
4. `uv run uvicorn app.main:app`와 `uv run arq app.workers.arq_app.WorkerSettings`를 같은 설정으로 실행한다.
   STT·Vision·Tavily는 필요한 주소·키가 있는 기능만 연결한다. 선택 공급자 미설정은 앱 기동 자체를 막지 않는다.
   STT는 `STT_PROVIDER=mlapi`도 설정하고 실제 서비스의 주소·모델을 사용한다.
5. TTS는 Cloud의 실제 잔여 무료 문자량·진행 중 요청·같은 프로젝트의 다른 사용량을 확인하고
   `scripts.initialize_tts_budget --help`의 명시 초기화 절차를 따른다.
   초기화하지 않으면 유료 합성을 시도하지 않고 질문 텍스트를 유지한다.
   `TTS_PROVIDER=google_cloud`, 인증 정보, 세 역할의 `TTS_VOICE_MAP`, 프로젝트·월 문자 상한을 명시한다.
   `.env.example`의 음성 ID는 설정 예시이며 공급자 자동 활성화나 음질 검수의 증거가 아니다.
6. 평가 실행 예시는
   `uv run python -m scripts.run_ai_evaluation --cases ../ai/evals/service_examples --manifest report/runtime-manifest.json --output report/ai-smoke.json --dry-run`이다.
   실제 호출은 `--execute --max-model-attempts 12`로 한도를 명시한다.
   예시는 합성·미검수 자료라 품질 분모에서 제외한다. #110의 사람 검수와 Judge 교정을 대체하지 않는다.

이번 Elice `gpt-6-luna` 실측에서는 비스트리밍 `max_output_tokens=8192`가 400으로 거절됐고,
공급자가 비스트리밍 2,000 token 상한과 `stream=true` 대안을 응답했다.
상한 2,000의 일반 요청과 `LLM_STREAM=true`·8,192 token 예산의 SSE 요청을 각각 검증했다.
이는 해당 환경의 실행 기록이며 모든 모델·계정에 적용할 고정 제한은 아니다.
검증용 상한은 원본 `.env`를 변경하지 않고 별도 Settings 인자로 적용했다.

해당 공급자에서 검증한 연결 예시는 다음과 같다. 모델은 실제 계정의 설정값을 사용한다.
이는 초기 운용 예시이며 대표 서비스 자료의 지연·비용 측정으로 조정한다.

```dotenv
LLM_STREAM=true
LLM_REASONING_EFFORT=low
LLM_TIMEOUT_SECONDS=60
LLM_MAX_OUTPUT_TOKENS=8192
LLM_MAX_INPUT_BYTES=262144
LLM_MAX_RESPONSE_BYTES=1048576
```

- 환경별 활성 prompt·model 버전과 Gateway 상한, DB 마이그레이션, worker·Redis의 실제 연결을 확인한다.
  로컬의 미병합 선행 결합 상태와 develop 단독 실행을 혼동하지 않는다.
- Elice STT·Vision의 사용 가능한 주소·키·모델·요청/응답을 실제 환경에서 검증한다.
  설정 존재나 대역 응답 통과는 한국어 음성 인식·문서 인식 품질의 검증이 아니다.
- Google Cloud 권한·실제 무료 조건·persona별 음질·자동재생을 확인하고,
  같은 프로젝트의 다른 사용량을 반영한 잔여 문자 예산을 명시 초기화한다.
  내부 카운터가 외부 계정의 비용 0원을 보증한다고 표현하지 않는다.
- Tavily의 실제 공식 출처 적합성·검색 누락·비용·지연과 서로 다른 레포·문서의 품질을 별도 평가한다.
  테스트한 언어·형식·크기를 모든 공개 레포·문서의 지원 보증으로 확대하지 않는다.
- [#110](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/110)의 전체 평가 기준·근거·사람 검수 정답·Judge 교정은
  실행기 구현과 별도다. 실행 성공을 품질·출시 gate 통과나 평가 체계 전체 설계 완료로 판정하지 않는다.
- 게시가 요청되면 보존한 통합 원본에서 이번 신규 변경만 분리하고,
  실제 공통 구현·공유 계약·대응 구현의 의존성과 검증을 각각 명시한다.

## 2026-11-06 — #180·#182·#191·#193·#194 리뷰 후속과 통합 검증

사용자가 #183을 제외한 다섯 PR의 필수·선택 보완, 리뷰 답변과 병합을 승인했다.
각 원본 HEAD와 작업 환경을 보존하고 기존 PR에 후속 커밋만 추가했다. 초기 설계는 수정하지 않았다.

### 변경과 게시 경계

| PR | 이번 후속 보완 |
| --- | --- |
| [#180](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/180) | 단계 설명 0~4 정정, 신규 비활성/기존 활성 유지 설명, 실제 PostgreSQL에서 활성·비활성 rubric 갱신 회귀. 기존 SQL·환산표·활성화 정책은 유지 |
| [#182](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/182) | 미답변 `None`에 양의 단계 1~4를 준 후보를 semantic 실패로 거절. 0/NA·전체 미관찰 key 실패와 이전 6건 수정을 보존 |
| [#191](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/191) | 미조회 사유를 조회 조건 미충족으로 표현. 원인을 임의 추정하지 않고 AI·BE 저장 회귀의 기대값을 동기화 |
| [#193](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/193) | 404·503·실제 수집 deadline의 부분 성공/원문 0개 실패 회귀. 제품 코드는 유지하고 전역 캐시 불변·모델 비재호출을 검사 |
| [#194](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/194) | #182 후속을 merge ancestry로 반영. 동시 task 각각의 실패가 부분 리포트로 반환되지 않으며 별도 callable을 받는지 검사. 다섯 PR의 기록을 이 절 한 곳에 통합 |

#183과 선행 #175, BE #153 등 다른 PR은 이번 수정·병합 대상에서 제외했다.
#194의 선행은 #182다. 선행 병합 뒤 develop 기준 신규 diff·CI를 확인하는 절차를 적용한다.
실제 게시 HEAD와 병합 결과는 각 PR의 원격 commit·review·merge 기록으로 확인한다.

### 이번 실행

기존 Python 3.12 환경에 각 격리 worktree의 BE·AI 소스 경로를 명시했다.
전용 PostgreSQL 17·Redis 컨테이너와 테스트 DB를 사용했으며 실제 서비스 DB나 외부 모델은 호출하지 않았다.

| 범위 | 새 실행 결과 |
| --- | --- |
| #180 seed 3파일 | 실제 PostgreSQL 17에서 17 passed. BE Ruff·format·mypy 통과 |
| #182 수정 전/후 | 양의 단계 반례 8개 실패 후 수정. 관련 74개·AI 전체 552개 통과, BE import 1개 통과 |
| #182 출력 호환 | 실제 AI 생성과 BE #153 `32aec12` 출력 검증기 7개 시나리오 통과. DB 저장 검사가 아님 |
| #191 AI·BE | AI 전체 430개, BE import 1개, 실제 PostgreSQL 경계·9턴 저장 25개 통과. AI·BE 정적 검사 통과 |
| #193 실제 수집·저장 | 관련 3파일 39개 통과. area 필터 제거 변형에서 부분 성공 3개 실패 후 제품 파일 정확 복원 |
| #194 개별 AI | 후속·동시 실패 검사 포함 AI 전체 555개, Ruff·format·mypy 통과 |
| 최신 develop+다섯 변경 결합 AI | 557 passed. Ruff·format·mypy 18개 소스 통과 |
| 같은 결합본 BE 전체 | 1673 passed, 1 skipped, 7 warnings. 격리 PostgreSQL·Redis, 외부 API는 대역 |
| 결합본 BE 정적 검사 | Ruff·format 통과, mypy 163개 소스 통과 |
| 공통 계약 checker | 별도 기존 checker 환경에서 schema 2개·부분 OpenAPI·fixture 7개 PASS. 전체 API 호환성 검사는 아님 |

통합 검증은 `develop@c70c444`에 #180 `0ffab4f`, #182 `1cf8324`, #191 `0601e39`,
#193 `4b38a90`, #194 `9d9b7cf`의 내용을 결합한 tree `5c4c8724ef82c4e5a9d416f9afec328be8666154` 기준이다.
현재 절의 문서 변경은 위 제품 코드·테스트 실행 결과를 바꾸지 않는다.

원격 #191의 최초 `08a11ff` CI는 BE 옛 기대 문구 두 곳으로 2 failed였다. 이를 `0601e39`에서
동기화한 뒤 새 CI가 1664 passed·1 skipped로 통과했다. 최초 실패를 숨기거나 과거 결과로 대체하지 않았다.
다른 새 HEAD의 원격 BE CI도 #180 1667개·#182 1664개·#193 1670개 통과와 migration 성공을 확인했다.

### 남은 서비스 검수

준비 코드 병합을 #110 전체 완료·독립 도메인 검수·rubric 운영 활성화로 보지 않는다.
수정 문구 재판정·실제 모델 일관성·품질·비용·지연, 환경별 prompt 등록,
실제 GitHub·음성 provider·FE 브라우저 전체 서비스는 이번 검증으로 완료 처리하지 않았다.
BE #153의 미답변 테스트 `None` 전달 정합성과 실제 report worker 저장·프로필 연결도 별도 후속이다.
원래 인라인 스레드와 일반 리뷰에 새 커밋·검증·후속 범위를 답했으며 종합 리뷰와 상호 연결한다.

## 2026-10-25 — 미게시 면접 실행과 후속 보완의 Draft 게시

### 원본과 신규 범위

- 원본 tree `c8f2cb5d`와 실제 worktree·index를 보존했다.
  `backup/director-unpublished-before-pr-20261025`는 원본 tree를 보존한 commit을 가리킨다.
- 선행 통합 tree `a4d7c1bf` 대비 원본 신규 36파일을 대조했다. 기게시 신규분 10파일,
  일부 게시 11파일, 전부 미게시 13파일, #131 담당으로 제외·보존한 seed 2파일이다.
  파일 수만이 아니라 함수·수정 구간과 테스트 사례까지 대응시켰다.
- 게시 기준은 `develop@dbd7f890`이다. 기존 #124~#127, #131과 다른 선행 PR은 변경·병합하지 않았다.
  초기 설계는 보존하고 실행 명세는 [#132](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/132),
  미적용 Context·L2 보완은 [#133](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/133)으로 분리했다.

| 구간 | 이번 게시의 배치 |
| --- | --- |
| 준비·Director 실행·WS·앱/worker | 신규 실행 코드와 회귀 검사를 이 구현 PR에 게시 |
| 현재 답변 Context·9번째 답변·수집 한계 | #133의 `agent_context.py`, `answer_context.py` 미적용 패치 |
| L2 예산·호출 기록·base URL·한계 | #133의 `repo_deep.py` 미적용 패치 |
| 기존 Director 생성기의 base URL 한 줄 | #133의 어댑터 미적용 패치 |
| 수집 상한 | #126의 8개 설정은 재게시하지 않고 남은 진행 중 조회 3개와 검증만 추가 |
| 준비 테스트 | #126에 옮긴 2함수·3사례를 제외하고 나머지 함수 AST를 보존 |
| WS·준비·현재 답변의 통합 회귀 | 실행 서비스에 의존하므로 이 구현 PR에 함께 게시 |
| seed 실행·추가 seed 검사 | 이번 변경에서 제외. #131 전담과 로컬 원본 보존 유지 |

#133은 일반 Python 파일에 아직 적용하지 않은 검토 자료다. 패치만 병합해도 기능은 활성화되지
않으며 앱·빌드·CI에서 자동 적용하지 않는다. 정확한 선행 base에서 일반 코드에 적용하고
재검증해야 한다. 선행 구현·DB 모델·migration·의존성·기게시 함수 전체를 복사하지 않았다.

### 게시본 단독 검사

| 검사 | 실제 결과 |
| --- | --- |
| 명세 #132의 부분 계약 검사 | schema 2개·부분 OpenAPI·fixture 7개 통과 |
| 실행 게시본 Ruff·format | 통과, format 260파일 |
| 실행 게시본의 조회 상한 검사 | 3 passed |
| 실행 게시본 전체 pytest | 수집 오류 9건. #82의 모델·#120의 router 등 선행 부재와 기존 seed import 오류 |
| 실행 게시본 mypy | 4파일 30오류, 134 source 검사. 선행 어댑터·모델·Context·REST 타입 부재 |
| 패치 4개 | SHA-256·base/result blob 일치, 정확한 선행에서 적용 검사·적용 후 원본 blob 대조 통과 |
| 원본 보존·범위 | 원본 36파일·index 동일, 신규 PR 간 파일 중복 없음, seed·DB 모델·선행 migration 미포함 |

### 별도 로컬 통합 검증

원본 선행 통합과 이번 코드·패치를 결합한 별도 환경을 사용했다. runtime 함수와 분리한 테스트는
원본 AST와 대조했다. 설정 3개와 #126의 나머지 설정도 원본과 일치한다. seed 오류 해결은
게시하지 않고 #131의 seed 두 파일을 검증 환경에만 연결했다. 외부 모델·GitHub는 대역이며
실제 외부 모델·서비스 DB·사용자 자료에 접근하지 않았다.

- 기존 Python 3.12.14, 새 전용 PostgreSQL 15.19·Redis 7.4.11을 사용했다.
- BE 첫 전체 실행: 1,231 passed·74 setup errors·경고 2개. 74건 모두 분석 fixture의
  `task10_test` DB 이름 조건 위반이며 기능 실패는 없었다. 통과·오류를 합쳐 전체 통과로 쓰지 않는다.
- AI 전체 실행: 295 passed. BE/AI Ruff·format·mypy 통과이며 각각 format 292/52파일,
  type 검사 141/12 source다.
- 올바른 새 `task10_test` DB에서 정확히 그 74개 오류 사례만 재실행해 74 passed를 확인했다.
  첫 전체 445.54초·exit 1과 재실행 108.78초·exit 0을 구분하며, 서로 다른 고유 BE 사례
  1,305개를 검증했다. 한 번의 전체 실행이 모두 통과했다고 표시하지 않는다.
- 각 실행 전후 통합 Python 소스 해시는 같았다. 생성한 두 테스트 DB 삭제·임시 schema 0개·
  연결 0개·DB 목록 복원·Redis/PG 종료와 포트 해제를 확인했다. 기존 서비스는 변경하지 않았다.

검증 보조 스크립트의 첫 Redis 기동은 Cygwin의 config 경로 해석으로 중단됐으며 생성 DB·서버를
정리하고 상대 config 경로로 재실행했다. DB 명명 문제도 보조 환경만 수정했으며 Python 소스는
변경하지 않았다. 실제 결과와 오류 목록은 원본 저장소의
`.claude/scratch/director-remaining-publication-20261025/validation-runtime/`에 보존한다.

### 병합 전 조건과 남은 범위

- Draft다. 필요한 선행·#132 명세·#133 후속 패치의 일반 코드 반영 뒤 최신 base에서 통합 재검증한다.
- #124/#125/#127과 공유하는 계약·설정·결정 색인·구현 기록은 각 신규 구간을 합쳐 보존한다.
  이번 PR의 파일 전체로 다른 PR의 추가 구간을 덮어쓰지 않는다.
- 준비 이벤트·preparing WS 유지·정확한 단계 재개·명시적 이탈 wire·일반 lease/reaper는 미완료다.
  Report·음성·다언어/대형 레포의 의미 품질·실제 모델 평가·배포도 이번 완료 범위가 아니다.

## 2026-10-26 — #134를 BE Task 13·14·15로 분할

### 범위 보존과 배치

- 사용자가 #134를 task별로 나누도록 요청했다. 원격 head `f2da245f`와 기존 브랜치를 보존하고
  `backup/pr134-before-task-split-20261026`을 만들었다. 게시본은 모두 `develop@dbd7f890` 기준이다.
- Task 13은 준비·worker·REST 앱 등록과 기존 준비/등록 검사를, Task 14는 Director·답변 분석·
  근거 조회 상한과 서비스/Context 검사를, Task 15는 WS·연결 인계와 WS 앱 등록/검사를 담당한다.
- 실행 ADR0026과 단일 구현 기록은 Task 14, WS ADR0024와 결정 색인은 Task 15에만 둔다.
  원본 18파일을 빠짐없이 배치하고 일반 파일을 중복 게시하지 않았다.
- `main.py`만 REST 등록 2행과 WS 등록 2행으로 나눴다. Task 14 → Task 13 → Task 15 순서로
  반영하며, 공유 삽입 구간의 충돌은 두 등록을 모두 유지해 해결해야 한다. 합성 결과는 원본과 같다.
- 기존 함수·fixture·decorator·설정·테스트를 보존했다. 원본 6개 테스트 파일의 59사례는 그대로며
  Task 15에 실제 앱의 WS 매칭/이름 경로를 검사하는 1사례만 추가했다.

### 이번 실행과 이전 기록의 구분

위 2026-10-25 절은 원본 #134의 검증 이력이다. 당시 전체 1,305개·AI 295개 결과를 이번 분할본의
새 전체 검사 통과로 사용하지 않는다. 이번에는 분할 합성본의 직접 관련 사례와 등록을 재검증한다.

| 범위 | 실제 검사 결과 |
| --- | --- |
| Task 13 게시본 | Ruff·format 255파일 통과. 전체 pytest 수집 6오류·mypy 2파일 10오류, 선행 모델/라우터/서비스 부재와 기존 seed 오류 |
| Task 14 게시본 | Ruff·format 257파일·조회 상한 3사례 통과. 전체 pytest 수집 3오류·mypy 1파일 15오류, 선행 부재 |
| Task 15 게시본 | Ruff·format 255파일 통과. 전체 pytest 수집 6오류·mypy 1파일 7오류, 선행 부재 |
| 새 선행 결합본 | 원본 59사례+새 WS 등록 1사례, 60 passed·2 warnings·102.52초·exit 0. 원본 6개 테스트 파일 byte 동일 |
| 실제 앱 등록 | REST 4경로·WS 1경로의 공개 매칭 API와 WS 이름 경로 확인. 빈 앱에서 새 검사가 실패하는 negative probe 확인 |
| 결합본 정적 검사 | BE Ruff·format 293파일·mypy 141 source, AI Ruff·format 52파일·mypy 12 source 모두 통과 |
| 공개 계약 형식 | 세 게시본의 계약 파일은 동일·무변경. backend venv는 검사 의존성 부재로 미실행 후 기존 전용 venv 재사용, schema 2개·부분 OpenAPI·fixture 7개 통과. 전체 API 호환성 검증은 아님 |
| 실행 후 정리 | 생성 DB 삭제·임시 schema/연결 0개·DB 목록 복원·PG/Redis 종료·16094/16095 포트 해제 확인 |

첫 결합 검사는 공통 설정 파일 전체 교체로 선행 설정이 누락돼 실행 전 중단됐다. 설정은 선행과
신규 구간을 함께 보존하도록 바로잡았다. 다음 등록 probe는 설치 FastAPI의 포함-router 표현을
평탄한 경로 목록으로 가정해 중단됐다. 실제 등록은 정상이며 공개 matches/이름 경로 API로 검사와
추가 테스트를 정리했다. 원본 서비스 코드는 바꾸지 않았다.

검증 복사 필터가 기존 `features/report` 골격 5파일을 제외한 것도 확인했다. 이전 통합본과 byte가
같은 5파일을 복원하고 BE 정적 검사만 재실행했다. 앞서 실행한 450파일은 그대로이며, 복원 후
455파일도 정적 검사 전후 hash가 같다. 관련 60사례를 전체 1,305개 재실행으로 표시하지 않는다.
실제 모델 호출·AI 전체 테스트는 이번에 실행하지 않았다. 이번 로그와 최종 메타는 원본 저장소의
`.claude/scratch/pr134-task-split-20261026/validation-runtime/`에 보존한다.

### 게시와 후속 조건

세 PR은 모두 Draft이며 선행·#132 명세·#133 미적용 후속 패치의 일반 코드 반영 뒤 재검증해야 한다.
새 PR의 실제 원격 범위를 확인한 뒤 #134와 상호 연결하고 기존 PR만 닫는다. 원본 브랜치는 삭제하거나
재작성하지 않는다. seed·#131, 다른 선행 PR, 기존 미완료 범위는 이번 분할로 변경하지 않는다.

## 2026-10-30 — #135 실행 경계의 새 리뷰 반영

- 원본 `b262298`과 별도 로컬 통합본을 보존했다. 신규 실행 보완만 후속 커밋으로 추가하며
  선행 Context와 공통 설정 필드를 복사하지 않는다. 공유 byte 상한 설명은 공통 PR에 둔다.
- `process_answer`의 답변 저장·T3 성공 후 정상 완료 책임을 명시했다. 기존 WS 송신 경계가
  처리하는 예상 I/O 오류와 예상 밖 콜백 예외·실제 취소를 구분한다. 이미 확정한 답변을
  재전송했다고 모델 작업을 자동 재실행하지 않는다. 종료 비교는 기존 9턴 상수를 재사용한다.
- 내부 scope가 없으면 외부 조회 전에 `evidence_scope_invalid`로 거절한다. 준비 호출자는
  같은 DB 세션과 잠근 최신 면접 행을 받는 비동기 guard를 주입한다. 호출 전과 저장 직전에
  소유권·입력 snapshot을 검사하며 외부 HTTP를 실행하지 않는다. 기본 None 경로는 유지한다.
- 테스트 helper 7개를 공용 모듈로 옮겼다. 기존 테스트 14함수·helper 7개의 AST 본문과
  Settings AST를 보존했고, 설정 문단 제목만 담당 구간에서 정리했다.

| 이번 검증 구성 | 결과 |
| --- | --- |
| 최신 develop + #135 + 정확한 Context01/02, 누락 scope·콜백·취소 | RED 1 failed/4 passed → GREEN 5 passed |
| 최종 비동기 DB guard의 두 저장 경계 | RED 2 failed → GREEN 2 passed, skip0 |
| 최종 API의 기존 None 경로 | 별도 28 passed, skip0 |
| 같은 최종 소스의 BE Ruff·format·Mypy | 통과, format 348파일·type 160 source |

위 2개+28개는 서로 다른 집중 사례다. 앞선 동기 guard 구성의 30개와 mutation 검사는
이전 단계의 이력이며 최종 API의 검증 수치에 더하지 않는다. 전체 결합 결과는 같은 기록의
[공통 검증](#director-review-integration-20261030)에서 관리한다. 외부 모델·운영 배포를 검증한
결과가 아니며 필요한 공통 선행 코드가 develop에 반영되기 전에는 Draft를 유지한다.

## 2026-10-30 — #137 준비 상태와 실제 WS 등록 리뷰 반영

- 원본 `109b8e0`과 별도 로컬 통합본을 보존했다. 준비 중에는 commit된 DB 단계 snapshot과
  변경분을 전달하고, 저장 질문과 `in_progress`를 확인한 뒤 `prepareCompleted`와 질문을 보낸다.
  재연결은 worker나 모델을 다시 실행하지 않는다. 짧은 중간 상태는 조회 간격 안에 합쳐질 수 있다.
- 준비 동안 수신 task를 유지해 조회 timeout 취소로 프레임을 잃지 않게 했다. 첫 질문 전 답변은
  거절한다. stale 답변 검사는 LLM 설정 검사보다 먼저 하며, 설정 로그는 비밀값 없이 필드명만 남긴다.
- realtime 키의 공개 helper는 이미 develop에 있는 service를 수정하는 공통 PR에 둔다.
  이 PR은 그 함수를 사용하며 선행 REST 구현을 복사하지 않는다. 실제 앱 등록 fixture를 사용하고
  REST·WS 등록을 함께 보존한다. 9턴 상수와 기존 ACK 전송 오류 보호도 유지한다.

| 별도 로컬 결합에서 이번 검증 | 결과 |
| --- | --- |
| 준비·재접속·실패·설정 회귀 | 기존 구현에서 5 failed → 같은 5 passed, 실패 복원 1개 추가 |
| 기존 WS·ACK 오류 3종·준비 6개·실제 등록 | 29 passed, skip0 |
| 실제 Uvicorn TCP + Redis의 죽은 owner 잠금 | 1 passed, handshake 30.406초, 명시적인 client 제한 35초 |
| 기존 REST 조회·생성·재시도 | 별도 48 passed, skip0 |
| 최종 proxy token-only·URL-only와 기존 설정 누락 | RED 2 failed/1 passed → GREEN 3 passed, 기존 29개와 일부 중복 |
| Mypy / 변경 Python Ruff·format | 160 source / 5파일 통과 |

선행을 결합한 결과이며 게시본 단독 통과를 뜻하지 않는다. 최종 결합 결과는 같은 기록의
[공통 검증](#director-review-integration-20261030)에서 관리한다. Caddy·브라우저 전체 경로는
미실행이고 nonce를 강제로 덮지 않는다. 명시적 abandon과 열린 소켓 종료·늦은 결과 차단은
공통 ADR0009 및 #143 후속이다. 실제 모델 품질·운영 배포·면접 전체 완료로 확대하지 않는다.

## 2026-10-30 — #136 준비 재개·회수 리뷰 반영

- 준비 네 단계의 완료 입력·L2/Evidence 산출물을 DB checkpoint로 묶는다. 실패 단계부터
  재개하며 완료된 원문 수집·분석을 다시 실행하지 않는다. 선택 run의 bound L1과 고정 SHA를
  비교하고 다른 SHA의 새 분석은 현재 면접을 무효화하지 않는다. 실제 기준 입력 변경은 거절한다.
- 새 owner는 90초 lease를 20초마다 갱신한다. 독립 cron이 만료 작업을 회수하며, lease나
  claim이 없는 이전 행에는 마지막 수정 이후 600초를 둔다. 새 메시지 없는 고착도 실패로
  전환해 REST 재시도를 허용하고 늦은 owner의 질문·준비 결과 저장을 막는다.
- reaper는 Director와 같은 record→interview 순서로 잠근다. 실제 PG의 이전 역전을 재현한
  뒤 최종 코드에서 제거됨을 대조했다. 입력 guard의 SHARE→UPDATE 승격 경합도 최초 UPDATE와
  공통 Context의 Posting→Frame 순서로 보완한다. 준비 설정 오류는 비재시도이며 값 없이 필드명만 기록한다.
- 준비 reaper의 실제 등록은 #136 부모 설정에 둔다. 이미 develop에 있는 배포 analysis worker의
  선택적인 부모 cron 계승은 공통 PR에 둬 선행 worker 전체나 준비 모듈을 복사하지 않는다.
  실제 배포 worker의 함수·cron·max_tries=1·job_timeout=600을 검사한다.

| 이번 집중 검증 | 결과 |
| --- | --- |
| 기존 준비·설정·재개·lease·legacy·동시 실행 | 41 passed, skip0, 119.65초 |
| 최종 reaper의 독립 PG 잠금 대조 | 교차 선점 제거, 회수 1건 |
| BE Ruff·format·Mypy / 부분 계약 검사 | 통과, 163 source / schema 2개·fixture 7개 |

41개는 로컬 explicit-child cron 구성의 검증이다. 게시용 부모 cron 계승과 공통 잠금 보완을
결합한 결과는 [공통 검증](#director-review-integration-20261030)에서 별도로 기록한다.
초기 설계·API·DB 모델은 바꾸지 않는다. 실제 외부 API·배포·SIGKILL 실험을 수행한 결과는 아니다.

## 2026-10-28 — #124 후속 검토의 미실행 조회 범위 보존

- #124의 [새 리뷰](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/124#issuecomment-6447685428)에 대응하는
  실행 보완은 #135에 둔다. #124는 계약 문단 위치만 정리하며 선행 service를 복사하지 않는다.
- 기존 정상 경로에는 이미 나머지 요청을 한 라운드 제한으로 실행하지 않았다는 공통 이유가 있었다.
  이번에는 생략한 허용 요청마다 repo·고정 SHA·path와 턴당 1개 제한 사유를 기록한다.
- 실제 I/O는 첫 요청 하나만 실행한다. 해당 실행의 status·items·searched_scope·error_code는 유지하고,
  생략 범위는 ToolResult.limitations와 저장 요약에 더해 보강 T3·후속 T4에 전달한다.
  조회 시작·취소·도구 오류·보강 실패·다음 질문 확정 뒤에도 이 설명을 보존한다.
- 기존 생성기의 `agent.py`를 유지하는 #126의 별도 `runtime_adapter.py`에서 신규 실행자를 import한다.
  새 API·DB 필드·테이블·조회 loop나 예산 초기화는 추가하지 않는다.

| 구성 | 이번에 직접 실행한 검사 | 결과 |
| --- | --- | --- |
| 수정 전 service와 신규 다중 요청 회귀 | 정상 미발견·도구 오류·보강 실패·취소 | 4 failed, 모두 생략 path 누락 재현 |
| develop `09a6f77` + #125 `23873ef` + #126 실행 연결 + #135 + 로컬 Context 후속 | PostgreSQL service·Context 한계·조회 상한 | 23 passed, skip 0, 최종 별도 adapter 연결 후 99.36초 |
| 같은 최종 로컬 결합 | Mypy app·변경한 Python 4파일 Ruff·format | 152 source 및 4파일 통과 |
| #135 단독 게시 소스 | BE Ruff·format·조회 상한 | 통과, format 257파일·3 passed |
| 같은 단독 게시 소스 | Mypy app | 선행 없는 원래 base 기준 1파일 15오류, 134 source |

로컬 Context 보완은 #133 patch01·02의 정확한 base/result blob과 SHA를 확인해 적용했다.
다른 미적용 패치나 선행 코드는 게시본에 복사하지 않았다. 최종 별도 adapter는 #126 후속 수정본을 사용했다.
게시본과 로컬 결합의 service·신규 회귀 bytes는 같으며 기존 service 테스트·도우미의 AST도 보존했다.
기록의 공용 파일 끝 충돌은 기존 실행 기록 내용을 보존한 배치와 이미 병합된 고정 배분 안내만 정리했다.
최신 develop과 게시 head의 실제 merge-tree는 충돌이 없다. 필요한 #125·#126과 Context 후속의 일반 코드
반영 및 실제 게시본 재검증 전에는 단독 실행 완료로 보지 않는다. 위 검사는 새 집중 검사이며 이전
전체 BE·AI 결과나 실제 외부 모델·GitHub·배포·전체 WS 검증 수치를 재사용하지 않는다.

## 기록 관리 기준

AI 작업의 구현·수정 내역, 코드 위치, 실행 결과와 남은 작업을 관리하는 원본이다.
기능 요구사항·초기 설계·검증 방법은 각 명세에, 지속할 결정의 맥락·이유·영향은
[decisions](decisions/README.md)에 보존한다. 문서 역할은
[ADR 0020](decisions/0020-implementation-record-policy.md)을 따른다.

## 2026-10-29 — #126 병합 후 최신 코드의 CI 검증 경로 보완

- 기준 develop은 `e58fff86ef8c876edb220b5e67dd73b4de01c0db`다. #125·#126·#127·#133이 반영돼 있다.
- 과거 Backend CI `40589589648`은 `09a6f77+d0293ec`의 합성 commit `3db9a486`에서
  #125 runtime 부재의 Mypy2오류로 중단됐고 pytest는 미실행이었다. 해당 실패 이력은 보존한다.
- 현재 두 workflow는 PR만 검사해 병합 뒤 develop의 새 결과가 남지 않았다. 기존 검사·권한·DB를
  유지하며 리뷰 준비 완료 이벤트, develop push, 수동 실행과 이벤트·PR/ref별 동시 실행을 추가한다.
- 최신 소스의 새 격리 venv에서 Mypy159 source·기존/신규 adapter와 예산·패키지 연결10건이 통과했다.
  actionlint1.7.12의 두 workflow 검사와 독립 검토도 통과했다. 독립 검토에서 jobs 원문 일치를 확인했다.
- 새 원격 결과는 후속 CI PR의 실제 head·merge SHA 및 실행 링크로 별도 확인한다. 위 로컬 결과를
  원격 CI 통과로 보고하지 않으며 수동·push 경로는 기본 develop에 변경이 반영된 뒤 사용할 수 있다.
- 이번 범위는 CI 검증 경로다. 수집기 경계 결함·미적용 Context/L2·후속 실행 연결의 결과로 확대하지 않는다.

## 2026-10-26 — 사용자 요청에 따라 PR #107 번호 유지

- 사용자가 #107 번호 유지를 명시해 기존 번호 유지 예외를 적용한다. #107의 원본 `ce24c82`와
  #138 수정본 `be1ff99`를 로컬·원격 백업으로 보존하고 원래 head 브랜치만 정리한다.
- 검증한 #138의 정정 테스트·기록을 가져오며 테스트 파일은 byte/AST 그대로다. 이번 새 변경은
  이 번호 복원 기록뿐이다. #102 본체·공용 fixture·다른 선행 구현을 복사하거나 병합하지 않는다.
- 실제 원격 head가 확인한 `ce24c82`와 같은지 다시 검사하고 그 SHA를 명시한
  `--force-with-lease`로 갱신한다. 다른 사람의 변경이 있으면 덮어쓰지 않는다.
- #107은 다시 열어 develop base·Draft로 유지한다. 원격 head·diff 2파일·커밋별 300행 상한과
  기존 리뷰/댓글 보존을 확인한 다음 #138을 연결하고 병합 없이 닫는다. #138 브랜치는 보존한다.
- 기존 정정 8사례와 결합 AI 309·BE 163사례는 이전 검증 이력이다. 테스트/제품 소스가 같음을
  대조해 보존하며 이번 새 서비스 실행 결과로 표시하지 않는다. 게시본 단독의 #102 fixture
  부재에 따른 8 setup errors도 그대로이므로 필요한 선행 반영 후 재검증해야 한다.
- 앞 절들의 #107 종료·#138 대체는 번호 복원 전 이력이다. 현재 검토·반영 대상은 #107이며,
  다른 관련 PR의 정정 사례·구현 기록 링크도 #107과 원래 head 브랜치로 정리한다.

## 2026-10-26 — #99 동시 변경을 보존한 최신 게시 기준 검증

- 게시 전 #99가 팀원의 `ce1019a`로 갱신된 것을 감지해 push 전에 중단했다. 기존 로컬 수정본과
  새 원격 head를 모두 보존하고 새 head 위에 원문 공백·CRLF·prompt v2 검증과 별도 회귀만 추가했다.
  팀원의 기존 테스트 16사례·v1/v2 prompt·Accepted ADR0028·계약은 byte/blob 그대로다.
- 중복될 로컬 ADR0028·명세 PR은 게시하지 않았다. 현재 명세를 준수하는 구현/검사 보완만 반영한다.
- 이 최신 #99와 #102·#103·정정·최종 #119 및 필요한 #114를 새 환경에 결합해 AI 전체
  **309 passed / BE 고유 163 passed**를 확인했다. AI Ruff·format 52·mypy 12 source,
  BE Ruff·format 262·mypy 133 source, 부분 계약 schema 2개·fixture 7개도 통과했다.
- Python 248파일의 검증 전후 hash가 같고 선택 25파일은 각 수정본과 byte가 같다. 실제 모듈은
  새 통합본 경로이며 contracts의 #119 비도메인 AST와 팀원 DomainPostingInput AST를 보존했다.
- 아래의 322사례는 동시 변경 발견 전 로컬 후보의 검증 이력이다. 최신 게시본의 수치에 합치거나
  최신 원격 head의 결과로 재사용하지 않는다. 원격 최신 반영 후 새 의미 품질 평가는 별도다.
- 결과·원본 대응·명령·노드 목록은 원본 저장소
  `.claude/scratch/ai-pr-reviews-20261026/latest99-full-review-integration-result.json`과 관련 로그에 보존한다.

## 2026-10-26 — AI 리뷰 수정 다섯 PR 최종 결합 검증

- 최신 develop `2ff1acf`에 #99 v2·#102 JD 원문·#103 복구 설명·#107 정정 사례·#119 L2 수정과
  필요한 #114 gateway를 별도 로컬 환경에서 결합했다. 선행을 원격 병합하거나 게시본에 복사하지 않았다.
- AI 전체 322 passed, BE 고유 163 passed다. BE는 import 1·Director 15·gateway 72·설정 50·
  L2 18·도메인 7사례이며 실제 고유 노드 목록을 보존했다.
- AI/BE Ruff·format(51/262파일)·mypy(12/133 source), 부분 계약 schema 2개·fixture 7개가 통과했다.
  실제 모듈 경로가 새 통합본이며 Python 247파일의 검증 전후 hash가 같다. 선택 20파일은 각 최종
  수정본과 byte가 같고 contracts는 #119 비도메인 AST와 #99 도메인 입력 AST를 모두 보존했다.
- 제품 코드는 새 통합본 구성 중 수정하지 않았다. 전체 서비스·DB·실제 모델·GitHub API 호출은
  실행하지 않았다. 기술적 통과를 도메인 분류·면접 판단의 의미 품질로 해석하지 않는다.
- 이 결합 결과를 각 게시본 단독 통과로 표시하지 않는다. #119의 #114 의존과 정정 게시본의 #102
  fixture 부재는 그대로다. #133의 일반 코드 반영과 call_model 기록 hook은 별도 후속이다.
- 결과·정확한 노드·구성·원본 대응은 원본 저장소의
  `.claude/scratch/ai-pr-reviews-20261026/full-review-integration-result.json`과 관련 로그에 보존한다.

## 2026-10-26 — PR #107 기여 정정 질문·이력 일치 보완

- 리뷰 원본 `ce24c82`의 사례 수와 검증 목적을 보존했다. 역할 확인은 실제 역할 질문과 역할 계약,
  직접 구현 전제 정정은 실제 직접 구현 질문과 해당 계약으로 검증된 Question을 구성한다.
- 공용 `conftest.py`와 제품 코드는 바꾸지 않았다. 이 테스트 파일의 도우미에서만 문장과 계약을
  함께 만들고, 실제 분석 모델 payload에 그 문장이 전달되는지 검사한다.
- 최초 답변의 질문도 최초 분석과 HistoryTurn에 같은 문자열을 쓰며, 정정 분석 이후 Director에
  전달하는 이력에는 분석에 사용한 역할 질문을 그대로 넣고 원문 일치를 확인한다.
- 먼저 payload 일치 검사를 추가해 잘못된 질문이 쓰인 기존 4사례의 실패(4 failed / 4 passed)를
  재현했다. 수정 후 원본 8사례, AI 전체 236사례가 통과했다. AI Ruff·format 46파일·mypy
  11 source, BE 패키지 import 1사례와 부분 계약 검사(schema 2개·OpenAPI·fixture 7개)도 통과했다.
- 기존 Python 환경을 사용하고 이 worktree의 AI 소스 경로를 명시했다. 외부 모델·GitHub 호출,
  DB 영구 보존·전체 면접 완주·실제 정정 판단 품질은 실행하지 않았다.
- 기존 #107은 선행 #102 base이므로 원본 브랜치·head와 백업을 보존하고 최신 develop에서
  이번 테스트·기록만 별도 게시한다. 선행 답변 분석·공용 fixture·Director는 복사하지 않으며,
  독립 게시본의 실패와 최신 선행 결합 검증 결과는 아래 후속 기록으로 구분한다.

### 독립 게시본과 최신 선행 결합 검증

- `develop@2ff1acf`의 별도 게시본에는 정정 테스트 248행과 원본 #107 기록 40행·이번 보완 기록만
  옮겼다. #102의 답변 분석 본체·공용 conftest와 기존 테스트는 복사하지 않았다.
- 실제 게시본 Ruff·format 41파일은 통과했다. 정정 8사례는 선행 #102의 `kit` fixture 부재로
  모두 setup error다. 이 실패를 기능 통과로 처리하지 않고 Draft로 게시한다.
- 같은 최신 develop에 #102·#103 수정과 정정 테스트만 결합한 별도 환경에서는 AI 전체
  254 passed·Ruff·format 46파일·mypy 11 source, BE 호출 경계 131 passed와 부분 계약 검사가
  통과했다. 실제 모듈 경로가 해당 통합본이며 Python 238파일의 검증 전후 hash가 같다.
- 통합에서 develop #77 기록과 각 PR의 고유 기록을 함께 보존했다. 이 수치를 독립 게시본의
  통과로 사용하지 않으며 원본 #107은 대체 PR 검증·상호 연결 후 병합 없이 닫는다.

## 2026-10-26 — PR #102 참조 JD 입력과 대조 답변 보완

- 기준은 리뷰 원본 `28e2663`이며 초기 설계·공개 계약·`AnswerAnalysis` 출력 필드는 변경하지 않았다.
- `answer_analysis._referenced_jd`는 질문의 `jd_requirement_ids`와 Contract의 `jd_requirement`
  basis 참조를 합쳐 해당 ID·원문·분류·source field·tech tags만 모델 입력으로 전달한다. 미참조 JD는
  제외한다. 필수 원문 누락·중복 ID는 호출 전에 `answer_analysis_input_invalid`(semantic)로 거절한다.
- `test_answer_analysis.py`에 7사례를 추가했다. Kafka/RabbitMQ 원문 변경이 실제 payload에 반영되고,
  두 참조 경로 각각과 함께 쓸 때 원문 유실을 허용하지 않는지 검사한다. 공용 질문 helper는 변경하지 않았다.
- 길고 틀린 답변에 실제로 "별도 갱신 없이도 캐시는 항상 최신 데이터를 보장합니다"라는 주장을 넣고,
  분석의 `answer_quotes`도 그 구절을 인용하도록 맞췄다. 입력에 없는 주장을 비판하는 fixture를 제거했다.
- 수정 전 새 회귀 7사례가 모두 실패함을 확인한 뒤 수정했다. 수정 후 직접 관련 33사례,
  AI 전체 235사례, AI Ruff·format 45파일·mypy 11 source 모두 통과했다.
- 실제 게시 원본 backend의 패키지 import·Director·공통 LLM·설정 경계 131사례가 통과했다.
  실제 BE gateway와 모의 HTTP를 연결한 별도 5시나리오에서도 서로 다른 JD 원문 전달 2건과
  필수 참조 누락의 HTTP 무호출 3건을 확인했다. 원문 전달 응답의 모델·prompt metadata도 보존됐다.
- 기존 `backend/.venv`의 Python을 사용하고 각 worktree의 AI·BE 소스를 명시했다. 외부 API·실제 모델,
  PostgreSQL 저장·면접 전체 흐름·분류 의미 품질은 이번 검증 범위가 아니다. 이전 실행 결과와 구분한다.
- 기존 전용 계약 검사 환경에서 schema 2개·부분 OpenAPI·정상/오류 fixture 7개와 `git diff --check`도
  통과했다. 부분 형식 검사를 전체 API 호환성 검증으로 확대하지 않는다.

## 2026-10-26 — PR #103 검토 결과의 검증 범위 설명 보완

- 리뷰 원본 `742e5a2`의 문서 지적을 반영했다. 승인 `QuestionReview`의 문장·Contract 대조와
  `CandidateRecovery` 분류·사유 전달을 구분하고, 후자의 반환값 자체를 후보와 별도 대조하지 않음을 명시했다.
- 제품 코드·계약·테스트는 바꾸지 않았다. 기존 Python 환경에서 이 worktree 소스를 명시해
  AI 전체 204사례, AI Ruff·format 40파일·mypy 11 source, BE import·Director·LLM·설정 경계
  131사례를 재실행해 모두 통과했다. 실제 검토기의 의미 품질·모델 호출·DB 저장은 검증하지 않았다.
- 기존 전용 계약 검사 환경의 schema 2개·부분 OpenAPI·fixture 7개와 `git diff --check`도 통과했다.

## 2026-10-06 — task-09 답변 분석 task 구현

관련 작업: AI task-09([답변 분석](../../ai/docs/task-09-answer-analysis.md)). PR 번호는 생성 후 기록한다.

### 기준과 변경

- 기준은 origin/develop `ef1a48d`다. 기존 `AnswerAnalysis` 열 개 필드, `validate_analysis`, ADR 0014의 값·저장 위치를
  그대로 쓰며 `contracts.py`, 새 enum, WS 이벤트, DB 컬럼, 의존성은 변경하지 않았다.
- `ai/src/devon_ai/llm_tasks/answer_analysis.py`: `analyze_answer`를 추가했다. 모델 호출 전에 코드로
  (1) 확정 질문(`ContractChecked[Question]`)과 `context.current_question_contract` 일치,
  (2) `turn_id`와 `context.current_turn_id` 일치 및 이미 이력에 있는 Turn 거절,
  (3) 빈 답변(초안·전송 오류) 거절 — 정상 제출된 "모르겠습니다"는 거절하지 않는다,
  (4) 조회 허용 위치·Evidence의 repository/ref가 Context 고정 ref와 일치하는지를 검사한다.
  잘못된 입력은 시도 없이 `answer_analysis_input_invalid`로 반환한다. 시도 소진은 `llm_failed`(budget)다.
- 모델 출력은 열 개 최상위 필드만 허용하고(점수 같은 추가 필드는 schema 실패), `validate_analysis`를 통과한
  `ContractChecked[AnswerAnalysis]`만 반환한다. 주입된 `ModelCall`이 validator를 건너뛰어도 같은 질문·답변으로
  다시 검증하며 실패하면 `answer_analysis_invalid`다. 재시도 루프·Tool 실행은 없고 `verification_requests`는 후보다.
- 모델 payload에서 Persona를 제외했다(평가 기준은 Persona별로 다르지 않다). `tool_results`와 `allowed_locations`는
  BE가 권한을 확인해 선택 인자로 전달하며 근거 ID는 주입된 Evidence·ToolResult 항목만 등록한다.
- `ai/prompts/answer-analysis-v1.md`는 검수 전 초안이며 런타임이 읽지 않는다. 운영 prompt 원본·등록은 BE다.
- 테스트: `test_answer_analysis.py`(입력·호출 경계), `test_answer_analysis_cases.py`(대조 사례 1~4),
  `test_answer_analysis_evidence_cases.py`(대조 사례 5~8), 공용 `conftest.py`. 조회·수정 특성 사례는 경계 테스트에 있다. 거절 사례는 의도한 의미 검증 사유로 실패함을 확인했다.

### 실행 결과

Windows, Python 3.12, 격리 worktree의 locked 환경에서 실행했다.

| 작업 디렉터리 | 명령 | 결과 |
| --- | --- | --- |
| 루트 | `uv --directory ai sync --locked --python 3.12` | 통과 |
| 루트 | `uv --directory ai run --locked ruff check .` / `ruff format --check .` | 통과 / 통과(44개 파일) |
| 루트 | `uv --directory ai run --locked mypy` | 통과(소스 11개 파일) |
| 루트 | `uv --directory ai run --locked pytest` | 228 passed(기준선 193 + 신규 35) |
| 루트 | `uv --directory backend run --locked pytest tests/agents/test_ai_package_imports.py` | 1 passed |
| 루트 | `python .claude/scripts/check_contracts.py` | 미실행(공통 계약 변경 없음) |

### 한계와 후속 작업

- 모든 모델 출력은 고정 fixture다. 실제 모델이 세 축을 올바르게 분리하는지, 유사하지만 무관한 코드를 지지
  근거로 채택하지 않는지 같은 의미 품질은 검증하지 않았다(AI-L01). mock 통과는 모델 품질을 뜻하지 않는다.
- 코드가 확인하는 것은 구조·인용 원문·등록 ID·허용 위치다. 필수 대조 사례 7(평가 불가 vs 설명 부족)과
  1(충분·부분·불충분의 실제 판정)은 모델 판단이며 코드는 모순된 조합만 거절한다.
- 대조 사례 8의 "최종 피드백 연결"은 이력 원문·분석 참조를 변경 없이 전달하는 데까지만 검증했다. 정정·후속
  보완의 최종 피드백 입력 구성은 task 3 범위이며, 사용자 입력 복구·재제출·재평가(AI-L09)는 보류다.
- BE 연동은 미실행이다. `backend/app/llm_tasks/answer_analysis.py`는 골격이며 prompt 로드, `answer_analysis`
  PromptSpec 등록, 분석 저장 순서와 transaction, 종료 후 늦은 결과 차단은 BE 책임이다(AI-L12).
  `tool_results`·`allowed_locations` 산출은 Controller가 맡는 제안이다.
- `decode`는 중첩 객체의 계약 밖 필드를 버리는 기존 동작이며 이번에 바꾸지 않았다. 최상위 추가 필드만 거절한다.

## 2026-10-06 — 기여 정정 사례 테스트

관련 작업: AI task-09·10 후속 사례([task-09](../../ai/docs/task-09-answer-analysis.md)). 선행: #102(`feature/ai-answer-analysis-v2`) 위에 쌓은 변경이며 PR 번호는 생성 후 기록한다.

### 기준과 변경

- 기준은 #102 head `28e2663`(origin/develop `ef1a48d` 위)다. 새 구조를 만들지 않는 범위(A안)로 `contracts.py`, 필드, enum, 함수 시그니처,
  의존성은 변경하지 않았다. 기존 `analyze_answer`·`validate_analysis`·`generate_question`의 동작을 사례로 고정한다.
- `ai/tests/llm_tasks/test_answer_correction.py`(8건)를 추가했다. 새 구현이 없어 테스트가 먼저 실패하는 단계는 없다.
  - 역할을 물은 질문에 "팀원이 했습니다"는 역할 정보 확인(`covered`)이며 정정은 `contribution_scope=teammate`로 남는다.
  - 같은 정정 답변도 질문이 요구하지 않은 key로 충분이 될 수 없고, 요구 항목을 설명하지 않았다면 `insufficient`다.
    요구 항목 누락·질문 밖 key로 `sufficient`를 주장하면 semantic 실패다.
  - 직접 구현을 전제로 한 질문에 정정이 오면 `needs_clarification`(충분성 null, 사유 보존)을 받아들이고, 사유 없는 상태 변경은 거절한다.
  - 정정은 새 분석으로만 남고 과거 답변 원문·최초 분석은 그대로이며(frozen) 이력 payload에도 원문으로 전달된다.
  - 정정이 반영된 검증된 분석이 다음 질문의 Director 입력(`answer_analysis`, `history`)에 변경 없이 전달된다.
  - 이력에 이미 있는 Turn의 재제출은 거절한다. 이는 AI-L09 복구·재평가 정책을 구현한 것이 아니라 현재 경계일 뿐이다.

### 실행 결과

Windows, Python 3.12, 격리 worktree의 locked 환경에서 실행했다.

| 작업 디렉터리 | 명령 | 결과 |
| --- | --- | --- |
| 루트 | `uv --directory ai sync --locked --python 3.12` | 통과 |
| 루트 | `uv --directory ai run --locked ruff check .` / `ruff format --check .` | 통과 / 통과 |
| 루트 | `uv --directory ai run --locked mypy` | 통과 |
| 루트 | `uv --directory ai run --locked pytest` | 236 passed(#102 기준 228 + 신규 8) |
| 루트 | `uv --directory backend run --locked pytest tests/agents/test_ai_package_imports.py` | 통과 |
| 루트 | `python .claude/scripts/check_contracts.py` | 미실행(공통 계약 변경 없음) |

### 한계와 후속 작업

- 모델 출력은 고정 fixture다. 정정 여부와 어느 주장에 대한 정정인지의 판단, 질문 전제 오류를 `insufficient`가 아닌
  `needs_clarification`으로 구분하는 것은 모델 판단이며 코드는 구조 모순만 거절한다. 전제 오류를 `evaluated`·`insufficient`로
  낸 결과는 구조상 유효해 코드로 막지 못한다. 실제 판정 품질은 검증하지 않았다(AI-L01, 평가는 task-12).
- 다른 task에서 구현·검증: 정정·후속 보완을 반영한 최종 피드백 입력 구성(task-11, 입력·출력 타입이 아직 미채택).
- 합의가 필요하며 이번 범위에서 구현하지 않음: 정정·보완이 가리키는 이전 Turn의 연결 형식(AI-L02·AI-L18), 이전 분석 내용을 이후
  Director와 피드백 입력에 전달하는 방식(`HistoryTurn`은 `analysis_ref`뿐), 사용자 입력 복구·재제출·재평가의 상태 매핑(AI-L09,
  보류). 이 때문에 정정이 Turn 5 이후 질문의 전제에 지속적으로 반영되는 동작은 아직 구현·검증하지 않았다.

## 2026-10-06 — task-10 Director 후보 복구 분류 경계

관련 작업: AI task-10 잔여([Director 질문 결정](../../ai/docs/task-10-director.md)). PR 번호는 생성 후 기록한다.

### 기준과 변경

- 기준은 origin/develop `ef1a48d`다. `contracts.py`, 기존 `CandidateRecovery` 필드, 공개 enum·WS 이벤트, DB, 의존성은
  변경하지 않았다. 기존 오류 코드(`director_input_invalid`, `director_candidate_invalid`,
  `director_review_failed`, `director_review_timeout`)와 `ModelResult[ContractChecked[Question]]` 형태를 유지했다.
- `ai/src/devon_ai/agents/director/agent.py`: `QuestionReviewer`의 반환 타입을 `QuestionReview | CandidateRecovery`로
  넓혔다. 기존 검토기는 그대로 호환된다. 검토기가 `CandidateRecovery`를 반환하면 후보는 반환하지 않고
  `semantic` 실패로 변환하며 분류는 `error_code`(`director_candidate_rewrite`, `director_candidate_replan`,
  `director_no_valid_candidate`)로만 전달한다. `candidate_recovery(failure)`는 실패에서 `CandidateRecovery`를 복원한다.
- 분류는 실행 권한이 아니다. 생성 모델·검토기를 다시 호출하지 않고 시도 기록은 그대로 보존하며, 상한 소진이나
  분류 결과로 검증 실패 질문·정상 `finish`를 내보내지 않는다. 형식이 맞지 않는 검토기 반환값(dict·문자열)은
  기존대로 `director_review_failed`다.
- 테스트(`test_director.py`에 4개 함수·11 케이스 추가): 세 분류의 실패 변환·무재호출·시도 기록, 목적이 바뀐 문장("수정 특성 확인"
  목적에 "TTL은 몇 분인가요?")은 분류되어 전달되지 않고 정상 문장은 `ContractChecked`가 되는 대조, 비구조 반환,
  다른 실패의 비분류.
- 이번 범위에서 제외했다: 목적 자동 선정, ask/retrieve/finish 결정 생성, 재작성·재계획 실행(AI-L04). 허용 Persona와
  남은 질문 수는 기존처럼 Controller 입력이며 배분 계산·10번째 질문 차단·finish 수용은 BE 책임이다.

### 실행 결과

Windows, Python 3.12, 격리 worktree의 locked 환경에서 실행했다.

| 작업 디렉터리 | 명령 | 결과 |
| --- | --- | --- |
| 루트 | `uv --directory ai run --locked ruff check .` / `ruff format --check .` | 통과 / 통과 |
| 루트 | `uv --directory ai run --locked mypy` | 통과(소스 11개 파일) |
| 루트 | `uv --directory ai run --locked pytest` | 204 passed(기준선 193 + 신규 11) |
| 루트 | `uv --directory backend run --locked pytest tests/agents/test_ai_package_imports.py tests/integrations/test_director_boundary.py` | 16 passed |
| 루트 | `python .claude/scripts/check_contracts.py` | 미실행(공통 계약 변경 없음) |

### 한계와 후속 작업

- 분류 판단은 주입된 독립 검토기의 몫이다. 승인 결과(`QuestionReview`)는 후보의 문장·질문 계약과 일치하는지 검사한다.
  복구 분류(`CandidateRecovery`)는 현재 검토 호출에서 반환된 분류·사유를 실패 결과로 전달하며, 반환값 자체가
  해당 후보에 대한 판단인지 별도로 대조하지 않는다. 테스트의 검토기는 합성 대역이며 목적 일치·전제 타당성의
  실제 판정 품질은 검증하지 않았다(AI-L01).
- 코드로 결정적으로 막는 것은 기존 입력 검사(허용 Persona·참조·Contract 동일성)뿐이다. 이미 확인한 목적의 반복은
  `HistoryTurn`이 목적을 갖지 않아 코드로 판정하지 않고 검토기 분류에 맡긴다.
- BE 연동은 미실행이다. `backend/app/agents/director/agent.py`(#82)는 `QuestionReviewer`를 타입으로만 쓰므로 변경은
  필요 없다. 새 `error_code`를 소비해 재작성·재계획·실패 안내를 결정하는 부분과 호출 상한은 BE·AI-L04·AI-L09
  합의 대상이다. `spec/ai/contracts.md`는 변경하지 않았다.
- Persona 배분 정책 충돌(공통 0004 vs #97·#82)은 이 변경과 무관하며 AI 코드는 배분을 하드코딩하지 않는다.

## 2026-09-27 — PR #67 JD 분류 계약 리뷰 보완

관련 PR: [JD 분류 category 통일 #67](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/67).

### 기준과 변경

- develop `744a5ad`(#50 병합 포함)과 #67 최초 검토 head `4a8fc09`의 이력을 통합했다.
- `JDRequirement.category`는 `required`/`preferred`/`responsibility`를 그대로 사용한다.
  주요 업무를 `unknown`으로 변환하지 않는 이유를 계약 경계에 한국어 주석으로 남겼다.
- Director 테스트에 7개 사례를 추가했다. 세 분류가 Context 디코딩과 실제 Director의 요청 생성,
  JSON 직렬화에서 보존되는지 확인하고, `unknown` 값과 `category` 없이 구형 필드만 있는 입력을 거절한다.
- AI 검증 기준·BE task-09·OpenAPI 설명을 현행 분류와 맞추고, 공통 ADR 0005에
  AI ADR 0006의 Wanted enum만 대체함을 명시했다. 과거 ADR 본문과 나머지 LLM 정책은 보존했다.
- 이번 보완에서 공개 API 필드·enum, DB schema, Wanted 추출 로직과 의존성은 변경하지 않았다.

### 실행 결과

Windows, Python 3.12, 격리 worktree의 locked 환경에서 확인했다.

| 작업 디렉터리 | 명령 / 시나리오 | 결과 |
| --- | --- | --- |
| `ai` | `python -m pytest -q -p no:cacheprovider` | 167 passed; 신규 회귀 7개 포함 |
| `ai` | 메모리에서 옛 필드·enum으로 되돌린 회귀 검사 | 7개 실패; `unknown`만 재허용하면 해당 1개 실패; 실제 코드에서는 7개 통과 |
| `ai` | `ruff check .`, `ruff format --check .`, `mypy src` | 통과; format 37개, mypy 11개 파일 |
| `backend` | `python -m pytest -q -p no:cacheprovider` | 273 passed, 13 skipped; `TEST_POSTGRES_URL` 미설정으로 PostgreSQL 검사 제외 |
| `backend` | `ruff check .`, `ruff format --check .`, `mypy app` | 통과; format 173개, mypy 114개 파일 |
| 루트 | `.claude/scripts/check_contracts.py` | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |
| 루트 | `PYTHONUTF8=1`로 `.claude/scripts/tests` unittest | 11개 통과, Windows에서 symlink 생성 불가로 1개 제외 |
| 루트 | 문서 링크·OpenAPI 파싱 비교 | 상대 링크 40개·anchor 7개 유효; OpenAPI는 `JdCategory.description`만 변경 |
| 루트 | 독립 코드 검토·BE 추출 결과의 AI Context 복원 | 추가 결함 없음; 세 분류·`source_field`·`tech_tags` 보존 확인 |

모델 경계는 mock provider로 검증했다. 실제 모델 품질·외부 Wanted API·전체 서비스 연결을
이번 실행에서 새로 검증한 것은 아니다. 공통 계약 검사는 부분 형식 검사다.

## 2026-10-26 — PR #125 리뷰 보완과 독립·최신 결합 검증

- 기준은 #125 원본 `70c1dbf`, 최신 결합 기준은 develop `d063d8d`다. 원본 head를
  `backup/pr125-before-review-20261026`에 보존하고 후속 커밋만 추가했다.
- 총 2회·생성/독립 검토 각 1회와 실패·거절 후 중단을 유지한다. 검토의 자유 텍스트 사유는
  일반 CallFailure에서 고정 요약으로 바꾸고 보호된 attempt.raw_output에는 그대로 보존한다.
- 새 planner의 question·contract·required point·basis ref 부가 필드는 호출 경계에서 거절한다.
  공통 decode의 기존 동작, 기존 generate_question, 공개 wire·DB·의존성은 바꾸지 않았다.
- 수정 전 신규 회귀에서 실패 사유 복사 1건과 중첩 부가 필드 4건이 실패했다. 보완 후 runtime
  38건이 통과하며 유효한 부분 Tool item·Context 등록 필요·단계 timeout 중단도 함께 검사한다.
- 원 게시본은 AI Ruff·format 43파일 통과, mypy는 기존 #103의 `_RECOVERY_CODES` 부재 1오류,
  전체 pytest는 `candidate_recovery` import 수집 오류 1건이다. 선행을 복사해 숨기지 않는다.
- 별도 최신 develop + 이 코어 3파일 결합본은 AI 전체 347 passed, Ruff·format 55파일·mypy
  13 source가 통과했다. 기존 Python 3.12 환경에 해당 worktree의 ai/src를 명시했다.
- 이번 347건은 새로 실행한 결합 결과이며 게시본 단독의 성공이 아니다. 실제 모델·원격 GitHub,
  DB·WS·worker·면접 완주·자연어 검토 품질·비용은 미실행이다.
- 10월 23일의 분리 게시 원문은 아래에 그대로 보존한다. 파일 끝의 공통 추가 충돌을 피하려
  #50 기록 앞에 재배치했으며 다른 PR의 기록을 복사·삭제하지 않았다.

## 2026-10-23 — Director 신규 변경의 분리 게시 검증

### 기준과 게시 범위

- 최신 원격 develop `bbe01213`에서 코어·연결 기반·BE 공통 보완·명세의 별도 게시 브랜치를 구성했다.
- 미병합 선행 #82/#102/#103/#107/#114/#119/#120을 결합했던 원본 통합 worktree는 보존했다.
  원본 tree는 `c8f2cb5d`, 선행 결합 기준 tree는 `a4d7c1bf`다. 해당 원본의 신규 차이는
  36파일 +6025/-58이며 아래 게시본의 최종 diff와는 다르다.
- 선행 구현·기존 테스트·패키지 의존성은 게시본에 복사하지 않는다. 모든 PR base는 develop이다.
  코어·연결·공통은 필요한 선행 구현이 없어 단독 검증이 제한되며 Draft로 검토한다.
- 코어는 `ai/.../director/runtime.py`·prompt·테스트를 원형으로 보존한다.
  연결 기반은 새 adapter·원문/과거 분석 복원·실제 tree 수집과 소비하는 8개 설정을 게시한다.
  공통은 seed CLI 수명·migration head 연결·검사 subprocess의 worktree 고정만 보완한다.
- 실제 계약/설계는 별도 명세 PR에, 결정은 0023·별도 연결 PR의 0025·BE 공통 ADR에 둔다.
  이 기록은 세 구현 PR의 결과를 모으는 한 곳이며 각 PR에 같은 현황을 복제하지 않는다.

### 게시본 단독 실행

기존 환경의 Python 3.12와 설치된 도구를 사용했다. 각 worktree의 backend 및 ai/src를
PYTHONPATH로 명시했으며 새 패키지 설치나 실제 모델·GitHub 호출은 하지 않았다.

| 작업 디렉터리 | 명령·범위 | 실제 결과 |
| --- | --- | --- |
| 코어 ai | ruff check / ruff format --check | 통과, format 43파일 |
| 코어 ai | mypy | 실패 1건: #103의 `_RECOVERY_CODES` 부재 |
| 코어 ai | pytest | 수집 실패 1건: #103의 `candidate_recovery` import 불가 |
| 연결 backend | pytest tests/test_config.py tests/core/test_director_limits.py | 10 passed |
| 연결 backend | 수집기·어댑터 런타임 pytest | 수집 실패: 미게시 코어·선행 모듈 부재 |
| 연결 backend | ruff check app tests / ruff format --check app tests | 통과 |
| 연결 backend | mypy app | 실패 19건: 코어 및 #82/#102/#114/#119 입력·모델·API 부재 |
| 공통 backend | seed 및 LLM 설정 pytest | 49 passed |
| 공통 backend | ruff check / format / mypy app | 통과, format 254파일·mypy 133파일 |
| 공통 backend | alembic heads | 실패: #82의 `0002_agent_storage` parent 부재 |
| 명세 루트 | .claude/scripts/check_contracts.py | 2 schemas·partial OpenAPI·7 fixtures 통과 |

공통 seed 검증은 주입 세션을 그대로 쓰는 경로와 CLI 자체 연결의 성공·실패 정리를 확인한다.
연결 검증에는 원래 수집기의 구조 상한 1사례·binary/timeout 부분 실패 2사례를 그대로 옮겼고,
실제 provider 경계의 어댑터·호출 예산·저장 질문 복원 3사례를 추가했다.

### 게시 코드와 선행 구현의 별도 로컬 결합 실행

아래 결합은 무시된 검증 디렉터리에서만 수행했으며 PR diff에는 선행 코드가 없다.
준비 실행·worker·Director 서비스·WS 활성화도 이 결합에 추가하지 않았다.

| 결합 범위 | 실제 실행 결과 |
| --- | --- |
| 코어 게시본 + #103 agent.py 한 파일 | 신규 28 passed, AI 전체 221 passed, mypy 12파일 통과 |
| 연결 게시본 + 선행 tree + 코어 3파일 | 관련 36 passed, mypy app 140파일 통과 |
| 네 게시 범주 + 선행 tree | AI 전체 295 passed, BE 관련 6파일 89 passed |
| 위 결합의 모듈 위치 | 9개 실행 모듈이 모두 해당 overlay에서 로드됨을 확인 |
| 공통 게시본 + #82 migration 한 파일 | 실제 PostgreSQL 새 DB에서 upgrade head 통과 |
| 같은 PostgreSQL DB의 seed CLI 2회 | 평가 기준6·도메인 frame21, 중복 없음·비활성 유지 |
| 같은 PostgreSQL DB | downgrade base 통과, 생성 DB만 삭제·전용 PostgreSQL 종료 확인 |

DB 검사는 SQLite로 대체하지 않았다. 기존 DB·schema·table 목록이 전후 일치하며
추가로 사용한 16086 포트도 해제했다. 원문·모델 provider는 mock으로 검증했다.
위 수치는 이번 게시본으로 새로 실행한 결과이며 원본 통합본의 BE 1302건을 재사용하지 않았다.
계약 검사는 부분 형식 검사이며 runtime·TypeScript·전체 API 호환성 검증이 아니다.

### 보존한 후속과 미검증 범위

- `agent_context.py` 현재 질문·한계 전달 보완 및 `repo_deep.py` 예산·한계 전달 보완은
  선행 구현에 붙는 후속이므로 원본 패치로 보존한다. 선행 반영 뒤 연결·재검증해야 한다.
- 이 보완을 요구하는 `load_answer_context`·반환형, 기존 `generate_question`의 base_url 수정,
  L2 한계 전달 및 Context 서비스 통합 검증도 보류한다. 우회 함수·복제 구현은 만들지 않는다.
- 준비 실행·ARQ 등록·WS·턴 저장/상태 제어·앱 활성화와 전용 테스트, WS ADR0024는 원본에 남긴다.
  BE 실행 전용 3개 상한·quota 예제와 이에 해당하는 테스트·통합 문서 구간도 게시 범위에서 뺀다.
- 공개 OpenAPI·FE·WS wire, 패키지/lockfile, DB 모델은 변경하지 않는다.
  운영 prompt 검수·활성화, 실제 모델 의미 품질·지연·비용, 다언어·대형 파일 전반은 미검증이다.
- 원본·게시·보류·게시용 테스트/문서 조정의 대응표와 패치는 원본 저장소의
  `.claude/scratch/director-publish-20261023`에 보존한다. 선행 병합·보류 보완 후 다시 검증한다.

## 2026-09-27 — PR #50 계약 검증 재검토 반영

관련 PR: [AI 내부 계약과 순수 검증 경계 #50](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/50).

### 기준과 변경

- develop `c6e0c3c`, #49 `387ba2a`, #50 최초 head `3fe5d07`을 통합했다. #56에서 먼저 반영한
  공통 계약·Director·Model Gateway·BE 소비 코드를 유지하며 기존 PR 이력을 보존했다.
- `ai/src/devon_ai/contracts.py`: 전체 충분성이 null이어도 관찰한 충족·부족 항목을 보존하고,
  공통 decoder가 계약 밖 부가 필드를 제거하는 현행 동작을 유지했다. 두 경계에 한국어 주석을 추가했다.
- `partial`·`insufficient`의 모든 필수 항목을 covered/missing으로 강제하던 조건을 수정했다.
  사유가 있는 판단 보류 항목은 미분류로 남길 수 있다. `sufficient`는 여전히 전체 필수 항목의
  충족을 요구하고, 이유 없는 생략·충분성 모순·잘못된 key·중복·허위 인용은 거절한다.
- `ai/tests/test_contracts.py`: 중첩 부가 필드 제거와 기존 필드 검증, null/부분 충분성의 관찰 보존,
  저장용 직렬화 및 모순된 결과 거절을 보강했다. 새 필드·enum·의존성·DB schema는 추가하지 않았다.
- #49 설계 상태 안내를 보존하고 #50 최초 채택 기록에는 현행 기준으로 대체됐음을 표시했다.
  새 실행 결과는 설계 문서에 추가하지 않는다.
- 열린 #65·#66의 질문 저장·턴 루프는 충분성·관찰 목록을 직접 해석하지 않는다. typed `BasisRef`와
  중첩 `ContributionScope`를 유지하므로 이번 수정에 따른 해당 PR 코드 변경은 필요하지 않다.

### 실행 결과

Windows, Python 3.12, 격리 worktree의 locked 환경에서 실행했다.

| 작업 디렉터리 | 명령 / 시나리오 | 결과 |
| --- | --- | --- |
| `ai`, `backend` | `uv sync --locked --python <Python 3.12 경로>` | 양쪽 성공, lock 변경 없음 |
| `ai` | 수정 전 보류 항목 회귀 검사 | partial/insufficient 2건이 `point coverage`로 실패함을 확인 |
| `ai` | `python -m pytest -q -p no:cacheprovider` | 160 passed; 기존 138개와 회귀 22개 |
| `ai` | `ruff check .`, `ruff format --check .`, `mypy src` | 통과; format 37개, mypy 11개 파일 |
| `backend` | 전용 PostgreSQL의 `TEST_POSTGRES_URL`로 전체 pytest | 285 passed, skip 0; 실제 PostgreSQL prompt 검사 13개 포함 |
| `backend` | `ruff check .`, `ruff format --check .`, `mypy app` | 통과; format 173개, mypy 114개 파일 |
| 루트 | 별도 검사 환경에서 `.claude/scripts/check_contracts.py` | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |
| 루트 | 독립 코드 검토·문서 로컬 링크·`git diff --check` | 코드 추가 결함 없음, 문서 인코딩 수정 후 확인 |

PostgreSQL은 전용 로컬 테스트 DB의 임시 schema만 사용했다. 테스트 전후 남은 테스트 schema가
없음을 확인했고 직접 시작한 클러스터를 정상 종료했다. 실제 서비스 DB와 `.env`는 변경하지 않았다.
실제 모델의 자연어 평가 품질·답변 분석 생성·WS 전체 서비스 연결은 이번 검증에 포함하지 않았다.
공통 계약 스크립트는 부분 형식 검사이며 전체 공개 API 호환성 검증을 대신하지 않는다.

## 2026-10-26 — PR #97 기록 충돌 해소와 최신 develop 결합 검증

- 기준은 #97 `0734b802c42878e6cd42c18eaec27c5782e9822a`와 develop
  `633e8dee65bb85031730f30512b4d0a1e4003e86`이다. 두 변경을 결합한 별도 worktree에서 새로 실행했다.
- 충돌은 문서 머리말 뒤에 각 작업이 기록을 추가한 위치가 겹쳐 발생했다. #97의 고유 기록을
  기존 공통 절 사이로 재배치해 원문과 제목을 보존했다. 제품 코드·테스트·정책 의미는 바꾸지 않았다.
- [후속 리뷰](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/97#issuecomment-6161811626)의
  병합 요청을 확인했다. 실행 프롬프트·Director 보조 입력 검증·실제 면접 연결은 기존 후속 범위다.

Windows / Python 3.12.14, 기존 준비 환경의 Python과 검증본의 명시적 AI·BE 소스 경로를 사용했다.

| 검증 대상 | 실행 | 결과 |
| --- | --- | --- |
| 결합본 AI | 전체 pytest, cacheprovider 제외 | 254 passed |
| 결합본 AI | Ruff check·format, mypy | 통과; format 46개·mypy 11개 파일 |
| 결합본 루트 | hook·계약 스크립트 unittest | 17 passed, 1 skipped; Windows symlink 생성 불가 |
| 결합본 루트 | hook 두 파일의 Ruff isolated 검사 | 통과 |
| 결합본 BE | AI 패키지 import pytest | 1 passed; 검증본의 AI 소스 사용 |
| 결합본 BE | Ruff check·format, mypy app | 통과; format 264개·mypy 133개 파일 |
| 결합본 계약 | 전용 검사 환경의 check_contracts.py | schema 2개·부분 OpenAPI·fixture 7개 통과 |
| 실제 AI hook | uv offline/no-sync, 오류 Write·정상 Edit | F401·T201 검출, 정상 파일 통과, 원문·AI lock 불변 |
| 변경 문서·이력 | md 20개의 링크·앵커와 양쪽 기록 절 대조 | 상대 링크 287개·앵커 포함 19개 유효, 원본 절 누락 없음 |

이 결과는 이번 결합본의 새 실행이며 이전 193개·별도 #82의 24개 결과를 재사용하지 않았다.
실제 Claude UI 기동·Linux·외부 LLM·DB/WS 면접 전체 흐름은 이번에 실행하지 않았다.
부분 계약·AI 단위 검사로 고정 배분의 서비스 적용 완료나 다른 PR의 병합 가능을 판단하지 않는다.

## 2026-10-13 — PR #97 리뷰 대응과 면접 배분 구현 현황 재확인

### 문서 번호와 최신 구현

- 최신 `develop` `bbe01213d0bb791b64504f13fbe73ed4bb88d98b`에는 공통 ADR 0007인
  `0007-voice-interview-contract.md`가 있어, 이번 고정 배분 결정은
  [공통 ADR 0008](../shared/decisions/0008-fixed-persona-allocation.md)로 번호와 참조를 정리했다.
  확인한 열린 PR 14개 중 #81이 0006을 사용하고 있으며, 공통 0008을 새로 사용하는 PR은 없었다.
  아래 10월 6일의 번호 선택·구현 확인 기록은 당시 이력으로 보존한다.
- [PR #82](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/82)의 최신 확인 head는
  `0e973f3377553b13bbea419bfd662f968bf64b97`이다. 기존 `b262f29`와 달리 고정 6/2/1을
  계산하는 `agent_context.allowed_personas`와 설정·이력 검증이 구현돼 있다. 첫 HR 이후에는
  잔여 할당이 있는 기술·도메인만 허용하고, 도메인 할당이 남았는데 활성 프레임이 없으면
  `domain_frames_unavailable`로 거절한다. 미분류 공고는 DB 값을 보존하며 활성 `etc` 프레임을 쓴다.
- #82의 위 코드와 테스트는 이번 PR에 복사하지 않았다. 아래 검증은 #97의 문서·hook 검사와
  #82의 기존 배분 함수 검사를 구분하며, #82 전체의 병합 가능이나 실제 면접 완료를 뜻하지 않는다.

### 리뷰 대응과 남은 실행 연결

- [기존 리뷰](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/97#issuecomment-6107262453)의
  실행 프롬프트·Director 입력 검증 지적은 후속 구현 대상으로 유지한다. #97의 배분 변경 범위는
  문서이며, 현재 AI Director는 허용 목록 밖 출력은 거절하지만 이후 HR·횟수 상한에 맞는
  목록인지까지 검사하지 않는다. 프롬프트 문구 변경만으로 고정 배분이 보장되지는 않는다.
- 후속 구현은 #82의 Controller를 재사용하고, 프롬프트에서 배분 계산과 후보 선택의 책임을
  명확히 한다. Director의 보조 입력 검사에서는 이후 HR·이미 채운 할당과 함께
  `persona_counts` 누락·질문 번호 불일치의 처리 기준을 맞춘다. 별도 배분 계산기를 복제하지 않는다.
- FE mock의 6/1/2 예제, 실제 준비·턴 처리와의 연결, 중복·실패 시 질문 수 불변 및
  9번째 **답변 처리 후** 정상 종료는 후속 통합 검증 범위다. #82의 9문항 저장 테스트는 답변을
  fixture에서 직접 저장하므로 실제 답변 처리·WS 정상 종료를 검증한 것으로 취급하지 않는다.
- #82의 기존 고정 커밋 링크는 당시 ADR 0007에 계속 접근할 수 있다. 이후 현행 정책 참조를
  갱신할 때는 #97의 ADR 0008로 연결하며, 해당 PR의 실행 코드·이력은 이번에 수정하지 않는다.

### 이번 수정의 검증

Windows / Python 3.12, #97 게시 worktree와 최신 develop을 합친 별도 worktree에서 새로 실행했다.
기존 준비 환경의 Python을 사용했고, AI·BE 연결 검사에는 검증할 worktree의 `PYTHONPATH`를 지정했다.

| 검증 대상 | 명령 / 시나리오 | 결과 |
| --- | --- | --- |
| #97 루트 | `PYTHONUTF8=1`, `python -m unittest discover -s .claude/scripts/tests -v` | 17 passed, 1 skipped; Windows symlink 생성 불가 |
| #97 루트 | hook 두 파일의 `ruff check --isolated` | 통과 |
| #97 AI hook | 실제 uv·AI venv로 정상 Edit·오류 Write 실행 | F401·T201 검출, 정상 파일 통과, 소스·lock 불변 |
| #97 `ai` | `python -m pytest -q -p no:cacheprovider`, Ruff·format·mypy | 193 passed; format 40개·mypy 11개 파일 통과 |
| #97 `backend` | `python -m pytest tests/agents/test_ai_package_imports.py -q -p no:cacheprovider` | 1 passed |
| #97·develop 통합본 | `.claude/scripts/check_contracts.py` | 각각 schema 2개·부분 OpenAPI·fixture 7개 통과 |
| develop 통합본 | hook·계약 스크립트 unittest, 문서 링크·ADR 번호·본문 보존 | 17 passed, 1 skipped; 로컬 링크 284개, 번호 중복 없음, 기존 음성 ADR 보존 |
| #97 문서 | 로컬 링크·다른 AI ADR 보존·`git diff --check` | 링크 279개 대상 존재, AI ADR 0007·0008 및 배분 정책 본문 보존, 공백 검사 통과 |
| 별도 #82 `0e973f3` | `python -m pytest tests/agents/test_agent_context.py -q -p no:cacheprovider` | 24 passed; 정상 순서 28가지와 잘못된 횟수 검사 포함 |

실제 Claude UI 기동·Linux·외부 LLM·DB/WS 면접 전체 흐름은 이번에 실행하지 않았다.
#82의 DB 저장 회귀는 코드만 대조했으며 이번 24개 실행 결과에 포함하지 않았다.
독립 검토에서도 추가 결함이 없었고, 이번 수정은 문서 번호·참조·현황 기록에 한정한다.

## 2026-10-06 — 고정 질문 배분 문서와 AI 변경 파일 lint

### 기준과 변경

- `develop`의 `ef1a48d1531b43f382b69dee163419afb5709c6b`에서
  `refactor/interview-policy-ai-lint` 브랜치를 분리했다. 미병합 PR의 코드는 가져오지 않았다.
- [고정 배분 결정](../shared/decisions/0008-fixed-persona-allocation.md)(당시 공통 ADR 0007, 현재 0008)에 따라 정상 완료 면접을
  기술 6회·도메인 2회·HR 1회로 정리했다. 첫 HR을 포함한 총 9문항이며, 이후 기술·도메인 순서는
  허용 후보 안에서 선택한다. 마지막 답변 처리 후 종료한다.
- **면접 배분 변경은 문서에만 반영했다.** 현행 기능·계약·과제·검증 기준과 결정 색인을 맞추고,
  과거 ADR·초기 설계 본문은 보존하면서 현행 정책으로 연결했다.
- 게시 전 열린 PR 13개를 대조해 #81이 공통 ADR 0006을 사용 중임을 확인했다.
  번호 중복을 피하려고 이번 정책은 0007로 지정하고, 관련 문서의 참조를 함께 맞췄다.
- [PR #28의 AI lint 보완 요청](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/28#discussion_r4053030543)에
  맞춰 `.claude/scripts/lint_changed.py`의 AI 무조건 건너뛰기를 제거했다.
  Claude `Edit`·`Write`의 AI Python 변경 파일을 `ai/`에서 로컬 Ruff로 검사하며,
  `--offline`·`--no-sync`를 사용한다. 설치·자동 수정 없이 미준비 환경과 lint 실패를 안내한다.
- `.claude/scripts/tests/test_hooks.py`에 AI 실행·오류 전달·정상 통과·시간 초과·환경 부재·경로 제외
  회귀 검증을 추가했다. 사용 조건과 검사 범위는 [AI 테스트 안내](../../ai/docs/testing.md)에 기록했다.

### 실행 결과

Windows, Python 3.12의 별도 worktree에서 실행했다. 아래 결과는 이번 변경에서 새로 확인한 값이다.

| 작업 디렉터리 | 명령 / 시나리오 | 결과 |
| --- | --- | --- |
| 루트 | 구현 전 AI hook 회귀 검증 | 기존 무조건 skip으로 4개 실패 확인 |
| 루트 | `PYTHONUTF8=1`, BE Python으로 `-m unittest discover -s .claude/scripts/tests -v` | 17 passed, 1 skipped; Windows symlink 생성 불가 |
| 루트 | `ruff check --isolated .claude/scripts/lint_changed.py .claude/scripts/tests/test_hooks.py` | 통과 |
| 루트 | 실제 AI venv·uv로 hook에 `Edit`·`Write` JSON 전달 | 정상 파일 통과, 오류 파일의 F401·T201 검출; 소스·AI lock 불변 |
| `ai` | `uv --offline run --locked ruff check .`, `ruff format --check .`, `mypy` | 통과; format 40개·mypy 11개 파일 |
| `ai` | `uv --offline run --locked pytest -q -p no:cacheprovider` | 193 passed; 기존 구현 검증이며 새 고정 배분 구현 검증은 아님 |
| `backend` | `uv --offline run --locked pytest -q -p no:cacheprovider tests/agents/test_ai_package_imports.py` | 1 passed; 현재 worktree의 AI 패키지 연결 확인 |
| 루트 | 별도 검증 환경의 `.claude/scripts/check_contracts.py` | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |
| 루트 | 독립 코드·문서 검토, 변경 문서의 로컬 링크 278개와 `git diff --check` | 추가 결함 없음, 링크 대상 존재·공백 검사 통과; 면접 코드·프롬프트·fixture·설정·lock 변경 없음 |

BE 환경 준비는 캐시에 `lxml-stubs`가 없어 offline sync가 실패한 뒤, 일반 `uv sync --locked`로
완료했다. 이는 수동 검증 준비이며 hook은 의존성을 설치하지 않는다. hook 실검증에서는 실행할 Python을
지정하고 자식 프로세스의 PATH에 uv를 추가했다. 실제 Claude UI에서 hook이 시작되는 단계와 Linux 실행은
미실행이다. 공통 계약 검사는 부분 형식 검사이며 전체 API·DB·WS·모델 품질 검증을 뜻하지 않는다.

### 면접 구현의 후속 반영

- 확인한 [PR #82](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/82)의 head는
  `b262f29e335c1115600fe6dc7b306d0ed231263b`이며 미병합 상태다. 기술 최소 5회·도메인/HR 합산 최소 3회,
  첫 질문 이후 HR 허용이라는 유동 정책을 새 고정 배분과 맞춰야 한다. 도메인 프레임 부재 시 도메인을
  제외하는 경로도 도메인 2회 보장과 함께 검토해야 한다.
- `frontend/src/mocks/fixtures/interview.ts`의 기술 6회·도메인 1회·HR 2회 예제와 설명은 아직 유지된다.
  `ai/prompts/director-question-v1.md`의 배분 문구도 후속 구현에서 Controller의 책임과 함께 정합성을 확인한다.
- 면접 제어 코드·프롬프트·FE fixture·설정 예시는 이번에 수정하지 않았다. 후속 구현에서는 허용 후보 계산,
  질문 확정·중복 처리, 9번째 답변 후 종료 및 도메인 준비 조건을 검증해야 한다.
  이번 문서 정리만으로 #82 병합 가능이나 실제 고정 배분 적용 완료를 선언하지 않는다.

## PR #56의 현재 범위

관련 PR: [AI task-01~03 기반 및 Director 기본 질문 생성 구현](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/56)

| 영역 | 구현 위치와 범위 | 후속 범위 |
| --- | --- | --- |
| task-01 | `ai/pyproject.toml`, `ai/uv.lock`, `backend/pyproject.toml`: 독립 AI 패키지와 BE editable 설치 | 기능별 서비스 연결 |
| task-02 | `ai/src/devon_ai/contracts.py`: 내부 값 계약, 순수 검증, 저장 값 변환 | DB 존재·소유권·transaction 검증은 BE |
| task-03 | `backend/app/core/config.py`, `backend/app/integrations/llm/client.py`: 단일 환경 진입점, 지연 LLM 설정 검증, HTTP 호출·실패 분류·공유 호출 상한·metadata | 실제 계정 접근, 운영 상한·품질·비용 검증, metadata 영구 저장 |
| prompt | `backend/app/llm_tasks/prompt_loader.py`, `backend/scripts/seed_prompt_versions.py`: 활성 prompt 조회, 7종 seed의 멱등성·불변성·동시성 | 검수된 운영 prompt 등록 |
| Director | `ai/src/devon_ai/agents/director/agent.py`: 준비된 질문 계약을 받아 질문 생성·독립 검토·검증 | 목적 자동 선정, 도구 실행, 실제 검토기, DB·worker·API·WS 연결 |

레포 분석과 JD 분석의 본체를 이 PR에서 완성한 것은 아니다. 위 기반을 소비하는 각 기능 구현과
실제 서비스 연결은 해당 담당 작업에서 이어간다. Director도 준비된 목적의 질문 생성 경로까지다.

## 2026-10-26 — PR #119 최신 develop 결합과 병합 준비 검증

- 원본 #119 `93177862fd6bf4f2bcc1191f800b3ba341a115c8`와 develop
  `fca606a979d3b1214e6a5cfd9244d2fa5e10f08e`를 결합한 별도 worktree에서 새로 실행했다.
- #99의 `DomainPostingInput`과 #119의 L2 계약이 같은 위치에 추가돼 충돌했다. L2 정의의 위치만
  조정하고 양쪽 클래스·함수의 AST를 원본과 대조해 보존했다. 검증 로직·공개 계약은 바꾸지 않았다.
- 구현 기록도 #119의 고유 절만 재배치하고 기존 develop 기록은 보존했다. task-05와 저장소 분석
  문서의 과거 미구현 안내는 현재 기록 참조로 바꿨다. #109의 기록 정책 변경은 포함하지 않는다.
- #114는 이미 develop에 반영돼 이번 검증에서 별도 결합하지 않았다. 아래의 단독 실패·Draft
  기록은 당시 결과다. #133의 미적용 patch·호출 기록 hook은 이번에 가져오거나 활성화하지 않았다.

Windows / Python 3.12.14, 기존 준비 환경의 Python과 검증본의 명시적 AI·BE 소스 경로를 사용했다.

| 검증 대상 | 실행 | 결과 |
| --- | --- | --- |
| 결합본 AI | 전체 pytest, cacheprovider 제외 | 309 passed |
| 결합본 AI | Ruff check·format, mypy | 통과; format 52개·mypy 12개 파일 |
| 결합본 BE | L2 실제 adapter→AI→gateway HTTP 대역·패키지 import | 19 passed; L2 18·import 1 |
| 결합본 BE | Ruff check·format, mypy app | 통과; format 266개·mypy 133개 파일 |
| 결합본 계약 | 전용 검사 환경의 check_contracts.py | schema 2개·부분 OpenAPI·fixture 7개 통과 |
| 결합본 루트 | hook·계약 스크립트 unittest | 17 passed, 1 skipped; Windows symlink 생성 불가 |

기존 세 리뷰의 모든 area가 schema인 경우의 복구·ref 우선 semantic 거절·직접/프록시 주소와 토큰 전달을 다시 검사했다.
유효 area와 거절 목록 보존, 혼합/semantic 무재시도, timeout/provider/parse/schema를 합산한 총
HTTP 2회 상한이 통과했다. 과거의 AI 224·별도 결합 309/163을 이번 실행 결과로 재사용하지 않았다.
실제 모델·외부 GitHub·원문 수집·DB 저장·prepare·전체 면접 E2E는 이번에 실행하지 않았다.
구조·참조 검증을 자유 서술의 사실성이나 실제 분석 의미 품질 검증으로 확대하지 않는다.

## 2026-10-26 — PR #119 L2 검증·재시도와 호출 주소 리뷰 반영

- 기준은 원본 `3f945d3`이며 원본 브랜치와 `backup/pr119-before-review-fix-20261026`을 보존했다.
- `parse_deep_analysis`는 repository ID·SHA의 형식을 먼저 검사하고 입력 ref와 대조한다.
  형식이 유효한 다른 ref는 빈 요약·잘못된 area 목록·추가 필드와 함께 와도 semantic 실패다.
  ref 자체의 형식 오류는 schema 실패이며 다른 저장소의 결과를 복구 대상으로 사용하지 않는다.
- 검증된 area가 하나라도 있으면 기존 부분 성공과 거절 목록을 보존한다. 검증된 area가 없고
  거절이 전부 schema일 때 gateway에 schema 오류를 전달해 남은 재시도만 사용한다. semantic
  거절이 섞이면 재호출하지 않는다. task 내부 재시도 loop나 새 gateway·기본 관찰을 만들지 않았다.
- BE adapter는 `base_url=settings.llm_base_url`을 실제 호출에 전달한다. 직접/프록시 주소와 토큰
  조합을 실제 adapter→AI→gateway와 HTTP 대역으로 검사한다. #114의 설정·gateway 본체는 복사하지 않았다.
- #133의 미적용 `03-repo_deep.patch`에도 같은 주소 전달 행이 있으므로 이번 head를 반영해 해당
  중복을 제거하고 exact base/result·manifest를 다시 검증해야 한다. 다른 후속 보완은 보존 대상이다.

### 실행 결과와 범위

아래 표는 최초 리뷰 반영본의 결과이며, 혼합 거절 추가 검토 후의 최종 결과는 다음 절에 구분한다.

| 환경 | 실행 | 실제 결과 |
| --- | --- | --- |
| 원본 코드 + 새 회귀 | L2 AI / BE 테스트 | 5 failed·20 passed / 7 failed·7 passed로 두 검증 문제 재현 |
| #114 결합 + 새 주소 검사, 수정 전 | 직접/프록시 2사례 | 둘 다 필수 `base_url` 누락으로 실패, 외부 요청 없음 |
| 수정 게시본 AI | 전체 pytest·Ruff·format·mypy | 223 passed, format 41파일·type 11 source 모두 통과 |
| 수정 게시본 BE | AI package import·Ruff·format | 1 passed, format 250파일·Ruff 통과 |
| 수정 게시본 BE | L2 pytest·mypy app | 실패: L2 17사례 모두 #114의 `llm_base_url` 필드 부재. mypy 1파일 2오류·133 source로 선행 의존 확인 |
| 최신 develop `2ff1acf` + #119 수정 + #114 `6135275` | AI 전체·BE L2/gateway/proxy 설정/import | 223 passed / 124 passed. L2 17사례 포함, raw·오류 기록·총 HTTP 2회·semantic 무재호출·직접/프록시 전달 확인 |
| 같은 통합본 | AI·BE Ruff·format·mypy | 모두 통과. format 41/261파일, type 11/133 source |
| 수정 게시본 루트 | 기존 전용 venv로 계약 검사 | schema 2개·부분 OpenAPI·fixture 7개 통과. 전체 API 호환성 검증은 아님 |

검증 전후 AI·BE 실행 소스 해시는 동일하다. 실제 모델·GitHub·DB 저장·전체 서비스 E2E는 실행하지
않았다. 테스트 통과를 언어·규모별 분석 의미 품질로 해석하지 않는다. 단독 실행은 #114 미병합으로
제한되므로 Draft로 검토하고 필요한 선행을 반영한 최신 base에서 재검증해야 한다. 실행 로그는
원본 저장소 `.claude/scratch/ai-pr-reviews-20261026/pr119-validation/`에 보존한다.

### 추가 검토: 혼합 거절과 #133 후속 패치 동기화

- 채택 area가 없고 schema·semantic 거절이 함께 있으면 전체 재시도가 semantic area도 다시
  평가하는 것을 확인했다. AI 단위 1건·실제 gateway 대역 1건을 실패시킨 뒤, 거절이 전부 schema인
  경우에만 재시도하도록 좁혔다. 빈 목록은 재시도하지 않으며 혼합 거절의 원문·거절 목록은 보존한다.
- 최종 수정본은 AI 전체 224 passed, BE import 1 passed, AI/BE Ruff·format 통과(41/250파일),
  AI mypy 11 source 통과다. BE L2 18사례와 mypy 1파일 2오류는 여전히 선행 #114 부재로 실패한다.
- #114 통합본에서 AI 전체 224 passed, BE 관련 125 passed와 AI/BE Ruff·format·mypy를 재확인했다.
  이 통합 경로에는 별도 #99 검증 자료도 추가돼 format 42/262파일·type 12/133 source다. L2의
  호출 주소·gateway·기존 입력은 그대로이며, 실행 전후 소스 해시도 같다. 최초 결과와 로그를 덮어쓰지
  않고 `pr119-validation-mixed/`에 별도 보존했다.
- #133의 patch 3은 새 #119 adapter blob `6948791b`를 base로 재생성했다. 최종 result blob
  `8ce0d810`은 그대로이며, 이미 반영한 `base_url`은 문맥 행으로 유지해 추가/삭제가 0행이다.
  남은 후속은 공유 budget·즉시 시도 기록·수집 한계 전달이다. manifest의 patch 3 base·해시·선행
  #119 head와 적용 안내만 갱신하고 원본 source/integration tree ID와 다른 3패치는 보존한다.
- 4패치 모두 정확한 base hash·SHA-256·`git apply --check`·적용 후 기존 result blob 일치를
  확인했다. 기존 patch 4의 합성 base는 객체 DB에 없으므로 보존 result에서 역적용해 복원하고
  원래 base hash부터 대조했다. 기존 패치를 수정하거나 base 검사를 생략하지 않았다.
- 별도 보존 실행 통합본에 새 L2 검증과 patch 3을 결합해 AI L2 31 passed, BE 23 passed를
  확인했다. BE는 L2 18·기존 bridge 3·공유 예산/원문 한계/취소 시 기록 보존 probe 2사례다.
  BE Ruff·format 293파일·mypy 141 source도 통과했다. 원본 gateway를 바꾸지 않았다.
- 이 보존 실행 통합본의 gateway에는 아직 #114 단독에 없는 `attempt_sink` 보완이 있다.
  따라서 위 실행 성공은 #133 자료만으로 일반 코드가 활성화되거나 #119+#114만으로 후속 patch 3의
  실행 선행이 모두 충족됐다는 뜻이 아니다. 해당 gateway 보완의 실제 반영·통합 재검증은 후속이며
  이번에 새 gateway 기능을 만들지 않았다. 정확한 적용 증거와 실행 로그는
  `.claude/scratch/ai-pr-reviews-20261026/pr133-sync/`에 원본 백업과 함께 보존한다.

## 2026-09-27 — 최신 develop 통합

### 기준과 변경

- 작업 브랜치: `feature/ai-director-define`.
- 통합 전 feature: `b5f8a8ece3a34d807098a803c3557ad186751caf`.
- 통합한 develop: `ec38943722b5fb87132a14b29368a799813f28e9`.
- 기존 공통 조상 `b444c64` 이후의 DB 모델·초기 migration, 공통 오류 처리, API schema·검사,
  CORS 제거 및 develop의 면접 화면 변경을 병합했다.
- 유일한 Git 충돌인 `backend/uv.lock`은 양쪽 `pyproject.toml` 선언을 유지하고 `uv lock`으로
  재생성했다. 기존 패키지 버전은 모두 보존했고 `types-pyyaml`만 새로 추가했다.
  `pyyaml`의 명시적 개발 의존성과 `devon-ai` editable 설치도 유지한다.
- `backend/tests/llm_tasks/test_prompt_postgres.py`는 과거 migration에서 복사한 DDL 대신
  현재 `PromptVersion.__table__.create`로 테이블·제약·인덱스를 생성한다. 테스트별 임시
  schema와 정리 방식은 유지한다. 이 테스트와 전체 migration 검증은 별개다.
- 새 DB session/migration의 `get_settings().database_url` 소비, 일반 앱 기동과 LLM 지연
  설정 검증, CORS 설정·소비자의 동시 제거를 확인했다. AI의 호출 정책·Director 출력 계약은 유지한다.

### 실행 결과

환경: Windows, Python 3.12, uv 0.12.13, 로컬 PostgreSQL 15.19.
아래 결과는 통합한 코드에서 실제 실행한 결과다. 프롬프트 테스트 변경 후 BE 검사를 다시 수행했다.

| 작업 디렉터리 | 명령 / 시나리오 | 결과 |
| --- | --- | --- |
| `ai`, `backend` | `uv sync --locked --python 3.12` | 양쪽 성공 |
| `ai` | `ruff check .`, `ruff format --check .`, `mypy src` | 통과; format 37개, mypy 11개 파일 |
| `ai` | `python -m pytest -q` | 138 passed |
| `backend` | `ruff check .`, `ruff format --check .`, `mypy app` | 통과; format 173개, mypy 114개 파일 |
| `backend` | 명시적 `TEST_POSTGRES_URL`로 `python -m pytest -q` | 285 passed; 실제 PostgreSQL prompt 검사 13개 포함 |
| 저장소 루트 | 검사 의존성을 별도 uv 환경에 주입해 `python .claude/scripts/check_contracts.py` | schema 2개, 부분 OpenAPI, 정상·오류 fixture 7개 통과 |
| `backend` | 격리 DB에 `python -m alembic upgrade head`, `current`, `check` | revision `0001_initial`, 26개 업무 테이블, ORM 대비 추가 변경 없음 |
| `backend` | 실제 migration 테이블에서 테스트 prompt 7종 seed → load → 같은 seed 재실행 | 7종 일치; UUID·시간·본문·활성 상태 보존 |
| `backend` | 격리 DB에서 `downgrade base` → `upgrade head` → `check` → seed/load 재검사 | 업무 테이블 제거·재생성, ORM 일치, 7종 재검사 통과 |

전체 migration 검증은 전용 로컬 클러스터의 새 임시 DB에서만 실행했다. `DATABASE_URL`은 검증
자식 프로세스에만 지정했고 `.env`를 수정하지 않았다. 테스트 prompt는 합성 본문과 `test-model`을
사용했다. 검증 후 임시 DB와 테스트 schema가 남지 않은 것을 확인하고 전용 PostgreSQL을 종료했다.
실제 서비스 DB 적용이나 운영 prompt 등록 결과는 아니다.

### 검증 한계와 후속 작업

- 외부 모델 호출은 mock으로 검증했다. 실제 OpenAI 호출·자연어 품질·비용은 미검증이다.
- 이번 실행에서 FE lint/build는 미실행이다. 현재 실행 셸에서 Node/npm을 찾을 수 없었다.
  develop의 FE 변경을 그대로 수용했으며 별도 FE 구현은 추가하지 않았다.
- 공통 계약 스크립트는 부분 형식 검사다. 전체 API·TypeScript 대응·실서비스 호환성 검증을 대신하지 않는다.
- 기존 설계와 `testing.md`의 과거 기록을 이번 통합에서 일괄 재작성하지 않는다.
  이후 구현 현황과 실행 결과는 이 파일을 갱신한다.

## 2026-10-25 — #127 seed 범위 제외와 공통 보완 재검증

### 게시 범위와 원본 보존

- 사용자가 seed 오류 수정을 #131에 맡기고 #127에서 제외하도록 요청했다.
  #131을 병합하거나 수정하지 않고, `develop@dbd7f890`에서 남은 신규 변경만 구성했다.
- 기존 #127의 `eaea0e4b`는 `backup/pr127-before-seed-review-20261025`와 원본 worktree에
  보존했다. 제외한 seed 실행 코드·추가 테스트도 이 원본에서 확인할 수 있다.
- `backend/scripts/seed_all.py`, `backend/tests/test_seed_all.py`는 develop과 동일하다.
  #131의 질문 저장 변경 세 파일도 가져오지 않았다. 이 다섯 파일은 기준선과 내용이 같은지 검사했다.
- 남은 구현은 DDL 없는 `0003_director_runtime` merge revision과 검사 subprocess의
  현재 worktree BE·AI 소스 경로 지정이다. 공개 계약·seed 데이터·활성화 정책은 변경하지 않는다.
- seed 제외와 선행 의존은 [BE ADR](../backend/decisions/0008-director-foundation-publication.md)에
  기록한다. 이전 통합본의 seed 실행 결과를 이번 게시본의 검증 결과로 사용하지 않는다.

### 실제 실행 결과

기존 Windows Python 3.12.14 환경을 사용했다. 아래 단독 검사는 실제 게시용 worktree에서 실행했다.

| 범위 | 검사 | 결과 |
| --- | --- | --- |
| 게시본 backend | `pytest tests/core/test_llm_config.py -q` | 46 passed |
| 게시본 backend | `ruff check .`, `ruff format --check .`, `mypy app` | 통과, format 254파일·mypy 133파일 |
| 게시본 backend | 전체 `pytest -q` | 실패, 기존 `tests/test_seed_all.py`의 삭제된 `dispose_engine` import로 수집 중단 |
| 게시본 backend | `alembic heads` | 실패, #82의 `0002_agent_storage` parent 부재 |
| 별도 로컬 결합 | 게시본 + #82 migration 한 파일, PostgreSQL 15.19 | 단일 head `0003_director_runtime` 확인 |
| 같은 결합 환경 | 초기 revision → 기존 사용자 행 추가 → `upgrade head` | 통과, 기존 행·추가 테이블과 컬럼 확인 |
| 같은 결합 환경 | `downgrade base` → `upgrade head` | 통과 |

로컬 결합은 #82 `0e973f33`의 `0002_agent_storage.py` 한 파일만 사용했고 seed·#131 코드는
결합하지 않았다. 새 전용 cluster·테스트 DB를 사용했으며 생성 DB 삭제·DB 목록 보존·서버 종료를
확인했다. 첫 실행 보조 스크립트는 Windows 자식 프로세스의 pipe 대기로 중단됐고, 해당 전용 서버를
종료한 뒤 파일 로그 방식과 새 cluster로 재실행했다. 위 PostgreSQL 결과는 재실행에서 확인했다.

### 미완료와 병합 조건

- seed import 오류는 #131의 별도 범위다. 이번 변경이 seed 실행을 해결했다고 보고하지 않는다.
- #82가 없는 게시본은 migration graph를 해석할 수 없으므로 Draft로 유지한다.
  선행 반영 후 실제 graph에서 merge 필요성을 다시 확인하고 PostgreSQL에서 재검증한다.
- migration 한 파일의 결합 검증은 #82 전체 모델·서비스 통합이나 전체 pytest 통과가 아니다.
  실제 면접 실행·외부 모델 호출·seed 활성화 검증은 이번 범위가 아니다.

## 2026-10-27 — #127 기존 DB 이력 보존과 최종 합류 검증

### 수정과 선행

- `0003_director_runtime`과 #82·#108의 기존 revision ID·부모·DDL을 보존한다.
  #82의 신규 `0003_agent_storage_merge`, 기존 Director merge, #108 분석 실행을
  DDL 없는 `0004_interview_foundation_merge`에서 합친다.
- 신규 graph 검사는 최종 head 하나와 저장·공고·분석·Director의 기존 이력을 확인한다.
  선행 파일을 테스트에 복사하거나 가짜 revision으로 대체하지 않는다.
- BE ADR은 기존 Task 9의 0002와 구분해 [0008](../backend/decisions/0008-director-foundation-publication.md)로
  연결하고 색인에 추가했다. 원래 #127의 고유 실행 기록은 위에 보존하고 위치만 분리했다.
- #131 반영 이후 seed import 수집 오류는 현재 실패 원인이 아니다. 당시 실패 기록과
  최신 상태를 구분하며 seed 구현은 이번 게시본에 추가하지 않았다.
- Director 분리 게시·통합 검증의 원본은 AI 기록에 유지한다. BE ADR은 이 기록을 참조하며
  현황을 중복 작성하지 않는다. 이는 루트 CLAUDE 문서 원칙과 AI ADR 0020을 따른다.

### 이번 실행 결과

Windows Python 3.12, `develop@d063d8d` 기준이다. PostgreSQL은 새 전용 로컬 cluster를 사용했다.

| 범위 | 검사 | 결과 |
| --- | --- | --- |
| 최신 develop + #127 | `pytest tests/core/test_llm_config.py -q` | 50 passed |
| 같은 게시 범위 | Ruff·format·mypy app | 통과, format 279파일·mypy 136 source |
| 같은 게시 범위 | `alembic heads`·신규 graph 검사 | 선행 #82 부재로 실패, `0002_agent_storage` 없음 |
| 로컬 #81·#82·#108·#127 결합 | 설정 + 신규 graph pytest | 51 passed |
| 같은 결합의 실제 PostgreSQL | 초기·공고·Agent·Agent merge·기존 Director merge·분석 실행의 6개 출발점 → head | 모두 단일 `0004_interview_foundation_merge`, 기존 사용자 행 보존 |
| 같은 6개 DB | 명시한 출발 revision으로 downgrade → upgrade head | 모두 통과, 기존 사용자 행·호출 기록 테이블·분석 지표 컬럼 확인 |
| 초기 출발 DB | `downgrade base` → `upgrade head` | 통과 |
| 검증 자원 | 경로별 전용 DB 생성·삭제 | 6개 모두 정리 |

DB 경로 검사의 코드 tree는 `afd5adf1ceb4f27e237e0836d6ffe233fa1ecd71`이다.
이 로컬 결합에서 #108 main의 충돌은 문서 router와 분석 router 등록을 모두 보존해 해소했다.
이는 #108의 원격 코드 수정이나 해당 PR 전체 검증 결과가 아니다.

처음 사용한 상대 `downgrade -1`은 합류 경로가 모호해 실패했다. 대상 revision을 명시하여
다시 검사한 위 결과와 구분한다. 과거 리뷰어의 전체 pytest 수치를 이번 결과로 사용하지 않았다.

### 최종 PR 조합의 추가 확인

#81·#82·#108·#124·#125·#126·#127·#132를 최신 develop에 로컬 결합했다.
검증 tree `742d924a39480a118607487c589f8901ecca10d7`에서 AI 전체 347 passed,
BE의 저장·예산·gateway·설정·graph·분석 API/worker 집중 검사 423 passed·1 skipped였다.
AI Ruff·format 57파일·mypy 13 source와 BE Ruff·format 331파일·mypy 158 source,
부분 계약 2개·fixture 7개 및 단일 Alembic head를 확인했다. 검사 전후 Python 원문 hash는 같고
실제 import 경로도 해당 결합 worktree의 AI·BE 소스였다. BE 전체 pytest 수치는 아니다.

제외된 #108 migration 검사는 이름이 고정된 별도 DB를 요구했다. 전용 DB로 실행하니
`alembic_version` 첫 행만 비교하는 기존 단일 가지 가정이 드러났다. #108에서 실패 전후
revision 전체 집합·기존 자료·위험 downgrade 차단을 보존하도록 고친 뒤 같은 누적 코드의
전용 PostgreSQL 검사 1 passed와 health 5 passed를 확인했다. analysis·documents·me·health
등록도 함께 확인했고 전용 DB는 삭제했다. #108 자체 source는 #81이 없으면 import할 수 없으므로
이 결과를 단독 완료로 보고하지 않는다. 최종 보완은 migration DDL을 바꾸지 않는다.

#126 결합에서는 기존 `generate_question`과 새 `execute_director`를 모두 보존했다.
두 함수는 각 게시본과 AST가 같음을 독립 대조했고, 공통 gateway의 주소·timeout·시도 기록도
유지했다. 이 해소본은 로컬 검증에만 사용하며 선행 구현을 다른 게시본에 복사하지 않았다.

### 병합 조건

#82·#108이 없는 게시본은 graph를 실행할 수 없으므로 develop base의 Draft로 검토한다.
두 선행 반영 후 그 시점의 실제 graph·기존 자료·전체 BE 회귀와 CI를 다시 확인해야 한다.
이 검증은 외부 모델 품질·면접 완주·운영 DB 배포 확인을 포함하지 않는다.

## 2026-10-27 — #127 순차 게시 graph의 누락 보완과 자료 보존 재검사

### 실제 결함과 수정

앞선 6개 출발점과 최종 PR 조합 검증은 #127까지 결합한 graph의 결과였다.
develop → #82 → #108만 반영한 중간 snapshot에 두 head가 남는 문제를 놓쳤다.
이전 실행 기록을 보존하고 순차 게시 단계 자체를 새 회귀 범위로 추가한다.

- #108 `ef237c56`의 신규 `0004_analysis_storage_merge`가 저장·분석 이력을 먼저 합친다.
  최종 #108 `d0704b97`에서도 해당 migration 원문은 같다.
- #127 `78d39238`은 그 신규 합류와 기존 `0004_interview_foundation_merge`를 부모로 하는
  DDL 없는 `0005_director_foundation_merge`를 추가한다. 기존 migration ID·부모·DDL은 보존한다.
- 최종 head 검사와 기존 이력 검사를 유지하고, 실제 Script의 ID·부모 metadata로
  develop·#82·#108·#127 네 snapshot의 head를 각각 확인한다. 선행 코드는 게시본에 복사하지 않는다.
- [BE ADR 0008](../backend/decisions/0008-director-foundation-publication.md)의 새 절에
  현재 목표 0005와 이전 최종 0004의 관계를 기록한다. Proposed 상태는 유지한다.

### 이번 실행 결과

Windows Python 3.12, `develop@d063d8d` 기준이다. 결합 migration source tree는
`00996aa3ae9f572ff7c67275930c291e3bb36ee7`이며, 새 전용 PostgreSQL DB에서 합성 자료를 사용했다.
아래 수치는 앞선 통합 검증 수치를 재사용한 것이 아니다.

| 범위 | 검사 | 결과 |
| --- | --- | --- |
| 새 #108 + 기존 #127 결합, 신규 회귀 | 수정 전 graph 검사 | 2 failed·3 passed, 실제 두 head와 0005 부재 확인 |
| 새 #108 + 보완 #127 결합 | `pytest tests/core/test_director_migration_graph.py -q` | 5 passed, 기존 Alembic 설정 경고 5개 |
| 같은 결합의 최신 설정 검사 포함 | 설정 + graph pytest | 55 passed, 5 warnings |
| 변경한 Python 두 파일 | Ruff·format | 통과, 2 files already formatted |
| 최신 develop + #127 게시 범위 | 설정 pytest | 50 passed |
| 같은 게시 범위 + 신규 graph 회귀 | graph pytest | 5 failed, 모두 선행 `0002_agent_storage` 부재 |
| 실제 PostgreSQL 순차 게시 | 공고 → #82 merge → #108 merge → head | 각 게시 단계 단일 head, 최종 0005, 기존 모든 fixture 행 보존 |
| 기존 branch의 두 적용 순서 | Agent → Director → Analysis, Analysis → Director → Agent → 신규 merge들 | 두 경로 모두 최종 0005, 모든 fixture 행 보존 |
| 위 세 경로 각각 | 활성 분석 작업 3개 상태에서 `downgrade 0002_posting_versions` | 기존 분석 downgrade 차단, version 전체 집합과 모든 fixture 행 보존 |
| 위 세 경로 각각 | 명시한 #108 merge로 downgrade → head 재적용 | 통과, sibling 기존 #127 merge 이력과 모든 fixture 행 보존 |
| 검사 자원·원문 | 세 경로 후 base 정리, migration SHA-256 전후 대조 | 전용 DB public 테이블 0개로 복원, 원문 hash 동일 |

fixture는 사용자·공고 원문 JSON·작업 steps·질문 Contract·호출 raw·후보 페이지 지표를 포함한다.
전진·실패 rollback·merge-only 왕복에서 해당 테이블의 전체 행 JSON을 대조했다.
위험 downgrade의 첫 probe는 저장 merge를 대상으로 삼아 분석 branch를 내리지 않았다.
공통 조상으로 대상을 교정해 실제 분석 차단을 호출한 뒤 위 세 경로를 새로 실행했다.

이 결과는 #82·새 #108을 로컬 결합한 검증이며, 미병합 선행을 포함하지 않는 단독 CI 통과가 아니다.
#127은 develop base의 Draft를 유지한다. 선행 반영 후 실제 게시 순서와 최종 BE 회귀·CI를 다시
확인해야 한다. 외부 모델·면접 완주·운영 DB 적용과 전체 BE pytest는 이번 검사에 포함하지 않았다.

## 2026-10-28 — #127 선행 병합 후 이력 보존과 검증 기록 정리

- 기준 develop은 `4e511a992d7954fa310146bcba2f2d4c6358fb69`다. #82와 #108은 모두 반영됐고,
  현재 develop+#127의 실제 graph는 `0005_director_foundation_merge` 단일 head다.
  10월28일11:20 KST 리뷰의 #108 미병합 조건은 같은 날16:15 병합 이후 해소됐다.
- 원본 #127 `d580863`을 `backup/pr127-before-review-fix-20261028`에 보존했다.
  이번 보완은 설명·검증 기록만 정리하며 기존 migration 파일 전체의 Git blob을 유지한다.
- 같은 부모를 가진 `0003_director_runtime`은 기존 경로의 이력을 보존한다. 실제 개발자·공유·운영 DB의
  전수 적용 이력은 확인하지 못했으므로 적용된 DB가 없다고 단정하지 않는다. 부모에서만 제거하면
  별도 head가 남고 파일까지 없애면 그 revision을 가리키는 DB의 이력 해석을 깨뜨릴 수 있다.
- [BE ADR0008](../backend/decisions/0008-director-foundation-publication.md)은 Proposed·날짜 이력,
  기존 ID·부모·DDL 보존 이유, 현재 합류 관계와 rollback 보호 조건을 유지했다.
  검증 실수의 반복 서술은 줄이고 상세 실행 결과는 이 기록을 원본으로 삼는다.

| 구성 | 이번에 직접 실행한 검사 | 결과 |
| --- | --- | --- |
| 최신 develop+#127 | 설정·실제 Script graph pytest | 55 passed, skip0, 34.67초, 기존 Alembic 경고5개 |
| 같은 구성 | BE Ruff·format·Mypy app | 통과, format330파일·156 source |
| 같은 구성 | 부분 계약 검사 | schema2개·fixture7개 통과. 전체 API 호환성 검증은 아님 |
| 별도 전용 DB와 격리 schema | 기존 위험 downgrade 회귀·두 선행 적용 순서 회귀 | 3 passed, skip0, 53.27초 |
| 전용 PostgreSQL15.19 | 순차 게시·Agent→Director→Analysis·역순의 세 경로 | 모두0005, 기존 fixture 전체 행 보존 |
| 위 세 경로 각각 | 중복 active 분석이 있는 위험 downgrade | 기존 guard로 차단, 자료와 version 전체 집합 보존 |
| 위 세 경로 각각 | 명시0004_analysis_storage_merge로 downgrade→head | 기존 sibling 이력과 fixture 행 보존 |
| 같은 전용 DB | base→head 재적용 후 base 정리 | 통과, 마지막 public 테이블0개·migration 원문 hash 동일 |

DB fixture는 사용자·공고 원문 JSON·분석 steps·질문 Contract·호출 raw·페이지 지표를 포함한다.
수치와 DB 결과는 이번 최신 develop 결합에서 새로 실행했으며 이전 전체1438/347 결과를 재사용하지 않았다.
리뷰에서 보고한 설정 검사 간헐 실패는 이번55개 실행에서 재현되지 않았다. 최초 실패명·traceback이 없어
원인이나 해결 여부를 확정하지 않으며 재실행 통과를 오류 수정으로 보고하지 않는다.
최신 base의 원격 CI는 게시 후 별도로 확인하고 통과 전에는 Draft 해제나 병합 가능 상태로 단정하지 않는다.
전체BE·AI·외부 모델·운영 DB·배포·면접 완주 검증은 이번 집중·합성 자료 검사의 범위 밖이다.
이전 절의 seed 오류·선행 부재·예전 목표 head는 당시 기준의 기록으로 보존한다.

## 2026-09-27 — task-04 L1 호출·재요청과 캐시 판정

### 기준과 변경

- 작업 브랜치: `feature/repo-shallow`, 기준 develop `744a5ad`.
- PR #56 이전에 만든 로컬 커밋(자체 batch 검증 타입)은 `contracts.py`의 L1 계약과 중복돼 폐기했다.
- `ai/src/devon_ai/llm_tasks/repo_shallow.py`
  - `cache_identity`: `(repository_id, "l1", head_sha, prompt_version)`. `analysis_level`은 DB 모델의
    `ANALYSIS_LEVELS = ("l1", "l2")` 값을 쓰며 model은 제외한다. BE `repo_analyze.py` docstring의
    `analysis_level='shallow'`는 DB 제약과 다르므로 BE 연결 때 정정이 필요하다.
  - `analyze_shallow_batch`: 주입된 `model_call`·prompt·limits로 `ModelRequest`를 만들고
    `{"repositories": [...]}` 출력을 `parse_shallow_batch`로 검증한다. 입력에 대응하는 ID가 있는
    schema 실패 항목만 같은 `model_call`로 한 번 재요청하고 semantic 실패는 재호출하지 않는다.
    첫 호출의 시도 수가 2회면 재요청하지 않고, 재요청의 `max_attempts`는 남은 횟수로 제한한다.
    prompt·limits·입력의 타입 오류, prompt 불일치, 빈 입력, 중복 ID는 모델 호출 전에 Director와 같은
    방식(`ModelResult` 실패, attempts 없음)으로 거절한다.
- `ai/src/devon_ai/contracts.py`: `merge_shallow_retry`가 재요청 결과로 식별된 schema 실패만 교체하고
  첫 성공·다른 실패를 보존한다. `parse_shallow_batch`는 L1 계약에 없는 키(L2 관찰·개인 기여 값 등)를
  버리지 않고 해당 항목의 schema 실패로 처리한다. `head_sha` 불일치를 먼저 semantic으로 확정한 뒤 검사해
  다른 ref 결과가 재요청되지 않게 한다. `basis` 내부 키와 `decode` 공통 동작은 바꾸지 않았다.
- `ai/tests/llm_tasks/test_repo_shallow.py`: fake `ModelCall`로 캐시 판정, 순서 무관 대응, provider
  실패(timeout·parse·거부) 전달, 전체 schema 실패, 부분 재요청·결합, semantic 비재호출, 재요청 실패,
  ID 없는 오류 비재요청, L2·개인 기여 키 금지, 호출 전 입력 거절, SHA 불일치 우선 판정, 총 2회
  상한(첫 호출 2회 사용 시 재요청 없음) 검사.

### 실행 결과

환경: WSL2 Linux, uv. `ai`에서 `ruff check .`, `ruff format --check .`, `mypy`(11개 파일) 통과,
`pytest -q` 185 passed. `backend`에서 `tests/agents/test_ai_package_imports.py` 1 passed.

### 해석 기록

- 설계 문서(2026-09-23-ai-foundation.md)의 "첫 배치에서 유효 항목이 있으면 … 실패한 ID만 다시
  요청"을 제한 조건이 아닌 부분 결과 상황의 설명으로 해석했다. 첫 배치에 성공 항목이 없어도 입력에
  대응하는 ID가 있는 schema 실패 항목은 한 번 재요청한다.
- 이유: 출력 전체의 schema 실패는 공통 호출 계층이 한 번 재시도하므로, 모든 항목의 schema 실패도
  재요청해야 두 경우의 처리가 일관된다. 어느 쪽이든 task가 지키는 총 2회 상한은 넘지 않는다.
- 설계 의도가 "성공 항목이 없으면 재요청하지 않음"이라면 `analyze_shallow_batch`에 첫 결과의 성공
  항목 유무 조건만 추가하면 된다. PR 리뷰에서 문서 작성자 확인을 요청한다.

### 검증 한계와 후속 작업

- 실제 provider 호출과 운영 prompt 등록은 미실행이다. AI-L04는 0018로 총 2회·semantic 비재호출이
  채택됐고, 실행 상한 수치는 설정으로 주입해 대표 사례 측정으로 정하는 구현 작업이다. 재요청의 총 2회
  상한은 task가 첫 호출의 시도 수로 직접 지킨다. BE도 한 작업에 같은 `CallBudget`을 묶어 넘기는지는
  BE 연결 작업에서 검증한다.
- AI-L03은 0018로 기존 저장 위치·프로젝트 요약 의미가 채택됐다. BE adapter
  (`backend/app/llm_tasks/repo_shallow.py`)와 `repo_analyze`의 저장 매핑·캐시 조회 구현은 이번 범위
  밖이며 후속 작업이다. L0-b 입력 수집은 BE PR #45 범위다.

<a id="pr156-review-followup-20261031"></a>

## 2026-10-31 — PR #156 리뷰 후속의 cron·답변 Context 경계 보완

- 원본 head `fa217cd`를 `backup/pr156-before-review-fix-20261031`에 보존하고 후속 커밋만 추가했다.
  단독 게시본과 최신 develop `fa13526`을 합친 검증을 구분한다. #135·#136·#137 구현을 복사하지 않았다.
- 부모 `cron_jobs=None`만 빈 sequence로 정규화했다. list·tuple·설정 부재·기존 분석 reaper의 1회 등록을
  보존하고 잘못된 숫자 설정을 조용히 숨기지 않는다. 공개 `answer_turn_no` 키워드와 호출부를 맞추고
  asked/answered·현재 질문의 history 제외·저장 전 None·bool 거절의 의미를 설명했다.
- 두 Context 파일은 키워드명·docstring 정규화 후 원본과 AST가 같다. 잠금·실패 분류·답변 로직을 바꾸지 않았다.
- #136과 수집 한계 key·저장소 ID·문자열 목록 형태를 대조하고 소비 경계 5사례를 추가했다. 실제 writer→DB→
  worker 전체 통합 검사와 단독 소비 검사는 구분한다. 과거 패치 파일·SHA·base/result·적용 이력은 보존하고
  manifest의 현재 blob과 후속 변경만 갱신했다.

| 이번에 직접 실행한 검사 | 결과 |
| --- | --- |
| cron 수정 전 → 후 회귀 | 1 failed / 6 passed → 7 passed |
| 공개 답변 키워드 수정 전 → 후 | 4 failed / 3 passed → 기존 PG 7개와 소비 경계 5개, 12 passed |
| 게시본 전체 BE, 전용 PostgreSQL15·Redis7 | 1507 passed, skip0, 9 warnings |
| 게시본 AI 전체 | 347 passed, skip0 |
| 최신 develop + 수정본 AI 전체 | 372 passed, skip0 |
| 최신 develop 결합본 BE package import·기존 계약 검사 | 55 passed |
| BE / 게시본 AI / 결합본 AI Ruff·format·Mypy | 모두 통과. format348/57/60 files, Mypy159/13/14 source files |
| 공통 계약 부분 검사 | schema2·부분 OpenAPI·fixture7 통과. 전체 API 호환성 검증은 아님 |

BE 전체에는 전용 migration 검사도 포함돼 별도 1개를 더해 합산하지 않는다. 검사 전후 Python source hash가
같고 최신 develop 결합본의 BE 앱·테스트는 게시본과 같다. 두 Context 파일의 호출자는 공개 키워드로 맞췄다.
로컬 전체 검사 도중 전용 DB의 신규 연결은 `synchronous_commit=off`로 조정했다. SQL 가시성·잠금 검증이며
정전 복구 내구성 검증이 아니다. 원격 CI의 별도 기본 PostgreSQL 환경과 구분한다. 관측 경고는 기존 Alembic
설정과 pytest `record_property`/xunit2이며 통과 수에서 숨기지 않았다.

현재 소스로 redirect 11사례, 실제 Gateway의 공유 예산·timeout/schema·선택→L2 3시나리오와 cron 6입력을
확인했다. 동일 budget의 총2회는 저장소 작업 단위이며 준비 run 전체 상한으로 확대하지 않는다. 실제 #136의
소유권/checkpoint 원문 일부를 사용한 제한 PG 대조에서 User 잠금을 포함한 경로는 정상이고, 보호를 인위적으로
제외한 반례만 교착이었다. 이는 현재 경로의 장애나 준비 worker 전체 통과로 보고하지 않는다.

운영 DB의 활성 prompt 본문·실제 GitHub 자격/잔여 quota·실모델 품질·전체 면접 서비스·운영 배포는 미검증이다.
#156 이후 #135→#136→#137 반영과 최신 CI·REST/WS 양쪽 등록의 재검증 조건을 유지한다. 이전 리뷰의 1498개나
과거 네 PR 결합의 1601/347개를 이번 수치로 재사용하지 않았다. 정확한 명령·XML·source hash·환경·미실행 범위는
`.claude/scratch/pr156-review-fix-20261031/`에 보존한다.

<a id="director-review-integration-20261030"></a>

## 2026-10-30 — Director 선행 패치의 실제 코드 적용과 수집 경계 보완

- 기준은 `develop@2fc0103`이다. #126·#133·#155 병합 상태와 패치 1·2·3의 정확한
  base/result blob·원문 SHA-256을 대조했다. 현재 답변 Context·9번째 답변·L2 공유 예산·
  완료 시도 기록·수집 한계 전달을 일반 Python 코드에 수동 반영했다. 패치 4는 이미 구현된
  과거 자료로 보존하며 다시 적용하지 않는다. manifest에 적용 커밋을 기록했다.
- 원문 수집기가 정확히 항목 상한에 도달했을 때 미방문 디렉터리가 남으면 확인하지 못한
  범위를 명시한다. 상한에서 전체 구조를 다 읽은 경우에는 한계를 붙이지 않는다.
- 공개 저장소 수집에는 기존 OAuth App ID/secret의 공개 데이터 전용 Basic 인증을 사용한다.
  사용자 token의 파일 조회 권한을 확대하지 않는다. 명시적인 GitHub 요청만 만들며 client의
  기본 인증·쿠키·redirect를 상속하지 않는다. 인증값 한쪽만 있는 설정은 익명으로 강등하지 않는다.
  근거: [GitHub 공식 OAuth App rate limit 문서](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#primary-rate-limit-for-oauth-apps).
- REST 발급과 WS 검사가 쓰는 realtime 키 함수는 기존 service에서 공개 이름 하나로 공유한다.
  이미 develop에 있는 공통 파일의 변경이며 #137에 선행 REST 구현을 복사하지 않는다.

| 이번 새 집중 검증 | 결과 |
| --- | --- |
| 현재 질문/이력·1/9턴의 저장 전후·잘못된 턴 | RED 7 failed → GREEN 7 passed, 기존 배분 검사와 합계 31 passed |
| L2 예산·sink·source limitations·취소 | RED 2 failed → 기존 adapter와 합계 20 passed |
| 정확한 구조 상한 2/512·미방문/완료/초과 | RED 2 failed/4 passed → 기존 수집 검사와 합계 9 passed |
| 공개 앱 인증·비공개 전환·오류·비밀값 보호 | 신규 reader 11·collector 9사례의 RED 후 기존 도구 포함 78 passed, skip0 |

추가 독립 검토에서 서로 다른 사용자의 준비와 기존 Context가 공유 공고·Frame을 반대로
잠그는 SQLSTATE 40P01을 실제 PostgreSQL로 재현했다. `lock=True`에서 공고를 먼저 잠가
순서를 통일했다. 신규 회귀 RED 1 failed/1 passed 후 기존 Context·storage 포함 91 passed,
skip0을 확인했다. 앞선 공통 후보 241 passed는 이 잠금 보완 전 결과이며 최신 전체 결합·
원격 검사는 별도로 기록한다. read-only 경로와 기존 Context AST는 추가 블록 외에 같다.

위 결과는 전용 PostgreSQL 15와 외부 HTTP mock 기준이다. 실제 모델 품질·운영 GitHub 호출·배포
성공을 뜻하지 않는다. #135~#137의 실행 연결은 각 후속 PR에만 두고 공통 PR에 복사하지 않는다.
배포 worker의 선택적인 부모 cron을 계승하며 기존에 cron 설정이 없으면 ARQ의 빈 기본값을 유지한다.
부모 작업 보존·빈 목록·설정 부재의 3개 회귀와 실제 배포 등록을 검사했다.

### 최종 게시 소스를 결합한 새 전체 검증

공통 게시본과 #135·#136·#137의 실제 게시 소스를 `develop@2fc0103` 위에 결합했다.
검증용 로컬 head는 `7eb6a929cc2a`이며 원격 PR base는 모두 develop이다.
REST·WS의 두 등록을 모두 보존하고, 부모 준비 cron을 실제 analysis worker가 계승하는 구성이다.

| 새 전체 검사 | 결과 |
| --- | --- |
| PostgreSQL15·Redis7의 전체 BE pytest | 1601 passed, skip0, 1038.2초 |
| AI 전체 pytest, 최종 AI source hash 동일 | 347 passed, skip0 |
| 별도 DB의 Alembic upgrade/downgrade | 1 passed; 전체 BE에도 포함되므로 고유 건수에 더하지 않음 |
| 실제 통합 DB의 Alembic upgrade head·check | 통과, No new upgrade operations detected |
| BE / AI Ruff·format·Mypy | 모두 통과, format 367/57파일·type 163/13 source |
| 부분 계약 검사 | schema 2개·부분 OpenAPI·fixture 7개 통과 |
| 소스·게시 분리 | 실행 전후 Python 347파일 hash 동일, 소유 파일40개와 통합 소스 일치 |

중단된 이전 전체 실행과 그 이전 집중 검사 수치는 이번 전체 통과로 재사용하지 않았다.
전체 BE의 경고12개는 라이브러리의 기존 안내와 JUnit record_property 계측 경고이며 실패·skip과 구분한다.
원격 CI는 각 PR 본문의 해당 head별 검사 링크로 확인한다. 선행 미병합으로 생기는 단독 CI
실패를 이 로컬 결합의 통과와 구분한다. 실제 외부 모델·GitHub·Caddy/브라우저·운영 배포와
abandon 후속은 검증하지 않았다. 기존 정책·보류 계약을 임의 확정하지 않는다.


## 2026-10-28 — PR #126 기존 어댑터 보존과 수집 한계 지침

- 원본 `68c088f`를 `backup/pr126-before-review-fix-20261028`에 보존했다. 기존 `agent.py`는
  develop `09a6f77` 원문으로 유지하고 신규 `execute_director`는 `runtime_adapter.py`로
  분리했다. 기존 함수는 전체 파일 blob, 신규 함수는 원문 AST가 같다. 신규 두 테스트의 import와
  패키지 import 검사를 갱신하고 실제 소비자인 #135의 import 경로를 함께 조정한다.
- `repo-deep-runtime-v1.md`는 입력 `source_limitations`의 미확인 범위를 확인한 것처럼
  설명하지 않고 관찰·결과의 한계에 반영하도록 명시한다. 이 지침은 모델 응답을 코드로 강제하는
  보장이 아니다. 수집 메타데이터의 별도 보존과 모델 출력의 한계를 구분한다.
- 최신 develop `09a6f77`, 이번 변경과 미병합 #125 `23873ef` runtime을 별도 로컬 사본에서
  결합했다. 기존·신규 adapter, gateway, 예산, 원문 수집·패키지 집중 검사는 104 passed, skip 0이었다.
  생성·검토 각각에서 실제 task를 취소하는 새 2사례는 취소 전파와 완료된 plan 기록만 보존함을
  확인한다. AI runtime은 38 passed, BE mypy 151 source·Ruff·format 312파일이 통과했다.
- 게시본에는 #125 runtime을 복사하지 않는다. 최신 develop 결합에서 #125를 제외하면
  runtime import와 파생 Any 반환의 mypy 2오류가 남는다. 이전 d063d8d 기준 CI의 11오류와
  이번 결과를 구분한다. #125 반영 후 실제 게시본을 다시 검사하기 전에는 Draft다.
- 최신 develop와 최종 게시 head의 merge-tree는 충돌 없이 병합된다. 대형 develop merge commit을
  게시하지 않고 소규모 후속만 추가했으며 신규 구현·검증·문서 커밋은 각각 추가+삭제 300줄 이하다.
- #133 patch03은 아직 일반 Python에 적용하지 않은 자료다. #136의 수집 한계가 실제 모델 입력에
  전달되는 실행 연결은 해당 일반 코드 반영 후 다시 검증한다. 이번에 실제 모델·외부 GitHub,
  PostgreSQL 전체 검사·면접 완주·운영 배포는 실행하지 않았다.

## 2026-10-27 — PR #126 실제 예산 경계와 선행 결합 검증

- #126 원본 `e29c8f9`를 `backup/pr126-before-budget-review-20261026`에 보존하고 후속만 추가했다.
  게시본에는 미병합 #82의 저장·도구 구현과 #125 코어를 복사하지 않는다.
- CallBudget의 읽기 전용 remaining_attempts·terminal_failure를 통해 BE가 실제 잔여량과
  종료 상태를 확인한다. Context와 실제 예산 중 작은 값을 전달하며 두 시도가 없으면
  plan 요청 전에 중단한다. 조회는 예약이 아니므로 한 예산을 다른 작업·동시 실행과 공유하지 않는다.
- 실제 gateway를 먼저 소모하는 새 회귀에서 수정 전 2 failed·2 passed를 재현했다.
  수정 후 새 예산·gateway 회귀 77건과 게시본 단독의 설정·gateway 회귀 79건이 통과했다.
- 게시본 단독 전체 pytest는 #125 runtime 2건·dispose_engine 1건의 수집 오류이고,
  mypy는 선행 모듈·API 부재 19오류다. Ruff·format 259파일은 통과했다.
- 별도 로컬 환경에 develop `d063d8d`, #82 `c38d655`, 수정 #125 `23873ef`와 #126을 결합했다.
  새 예산·기존/새 adapter·gateway 경계 95 passed, AI 전체 347 passed, AI Ruff·format 57파일·
  mypy 13 source와 BE mypy 143 source가 통과했다. BE 전체는 전용 PostgreSQL·Redis에서
  새로 실행해 1,302 passed, 0 skipped(676.97초)였다. BE Ruff·format 299파일도 통과했다.
- 결합 adapter의 generate_question은 #82, execute_director는 #126 원문과 AST가 같다.
  공통 gateway의 기존 정의는 develop+#82 결합본과 동일하며 예산 조회 속성 두 개만 추가했다.
  base_url·deadline·attempt_sink와 #97 고정 배분을 보존한다. 준비 상한의 env 블록은
  면접 정책 끝의 동시 수정과 분리했다. adapter는 선행 #82와 합쳐 두 함수를 모두 보존해야 한다.
- 이 결과는 결합본의 새 검사이며 게시본 단독 성공이 아니다. 직접 선행 #82·#125와 명세를
  반영하고 최종 호출 경로를 다시 검사하기 전에는 Draft다. 준비·worker·WS 활성화, 면접 완주,
  실제 모델 품질·외부 GitHub는 이번 검증에 포함하지 않았다.

## 2026-09-28 — task-04 L1 BE adapter

### 기준과 변경

- 작업 브랜치: `feature/be-repo-shallow-adapter`, 커밋 `f1ab897`. 기준은 위 task-04 L1 커밋(`75f25c0`).
- `backend/app/llm_tasks/repo_shallow.py`
  - `analyze_repositories`: `call_model`에 `CallBudget` 하나를 묶어 `analyze_shallow_batch`에 넘긴다.
    부분 재요청까지 한 작업의 HTTP 요청은 총 2회다. prompt는 service가 `load_active_prompt`로 읽고
    조회 transaction을 끝낸 뒤 넘긴다. 이 모듈은 DB session을 받지 않는다.
  - `to_repo_analysis_rows`: 입력 저장소마다 `repo_analyses` 행 값을 만든다. `analysis_level='l1'`,
    `status`는 `succeeded`/`failed`만 만들며 `partial` 판정은 service 책임이다.
  - 성공 행은 `tech_stack`과 검증된 결과(`result`)를 채운다. 프로젝트 요약의 저장 필드는 BE 합의
    전이라 `summary`는 비우고, 개인 `role_summary`로 매핑하지 않는다(ADR 0006).
  - 실패 행은 요약·기술 기본값을 채우지 않는다. `error_code`는 `llm_timeout`·`llm_parse_failed`·
    `llm_failed` 중 하나이며, 요청 전 입력 크기 상한으로 거절되면 `input_too_large`다.
  - 호출 기록(model·raw_output·token·latency·attempt)은 그 저장소 결과를 만든 시도의 값을 넣는다.
    배치 호출이라 저장소별로 나눌 수 없어 `batch_position`으로 구분한다(`ponytail:` 주석).
- `backend/tests/llm_tasks/test_repo_shallow.py`: 가짜 HTTP 공급자로 성공 배치 행 매핑, schema 실패
  재요청 후 성공 저장, 한 budget의 HTTP 2회 상한, semantic 실패 비재호출·기본값 없음, 전체 timeout,
  호출 전 입력 거절, 입력 byte 상한의 `input_too_large`, 실패 행의 실제 실패 시도 기록, 출력에서
  누락된 저장소의 첫 호출 기록을 검사한다(9개). DB는 쓰지 않는다.

### 실행 결과

환경: WSL2 Linux, uv. `backend`에서 `ruff check .`, `ruff format --check .`, `mypy app`(114개 파일)
통과, `pytest -q` 281 passed, 13 skipped. skip은 모두 `TEST_POSTGRES_URL`이 없는
`tests/llm_tasks/test_prompt_postgres.py`다. `ai`의 `tests/llm_tasks/test_repo_shallow.py` 25 passed.

### 검증 한계와 후속 작업

- `backend/app/features/analysis/pipeline/steps/repo_analyze.py`는 docstring 골격이다. prompt 조회,
  캐시 조회, adapter 호출, run `partial`/`failed` 집계와 `repo_analyses` 저장 연결은 후속 작업이다.
  같은 파일 docstring의 `analysis_level='shallow'`는 DB 값 `l1`로 정정해야 한다.
- PostgreSQL 기준 저장·캐시 검증과 실제 provider 호출, 운영 prompt 등록은 미실행이다. 행 매핑 테스트
  통과를 durable 저장 완료로 보지 않는다.
- 분석 API(`backend/app/features/analysis/router.py`)가 골격이라 L1 결과 조회는 검증하지 않았다.
- 프로젝트 요약의 `summary` 저장 필드는 AI-L03의 BE 합의 후 연결한다.

## 2026-09-28 — jd_requirements 초안 정리 (불릿·상한 배분)

- 구현: `backend/app/llm_tasks/jd_extract.py`. 원문 줄머리 목록 기호(`•`·`∘`·`-` 등)를 떼고 기호만 있는 줄은 버린다.
  합계가 20개(`MAX_REQUIREMENTS`)를 넘으면 필수 요건을 먼저 담고, 남은 자리는 우대와 주요 업무가 한 줄씩 번갈아 나눈다.
  이전에는 필수→우대→업무 순으로 채워 우대가 긴 공고에서 주요 업무가 잘렸다(341487은 업무 15개가 모두 빠짐).
- 검증: `backend`에서 `uv run python -m pytest tests/llm_tasks` 20 passed(13 skipped), 변경 파일 대상 `ruff check`·`ruff format --check`·`mypy` 통과.
  실제 원티드 공고 5건(359638·281356·229817·341487·380611)에서 필수 요건이 잘리지 않고 주요 업무가 남는 것을 확인했다.
- 범위 밖: 회사가 자격요건 칸에 우대 문장("~이면 좋아요")을 넣은 경우의 재분류는 `jd_extract_v1`의
  "Wanted 필드를 추측으로 변경 금지"(`spec/ai/contracts.md`)에 따라 하지 않는다. "[함께 할 업무예요]" 같은
  섹션 제목 줄도 내용 판단이 필요해 거르지 않았다.

## 2026-10-05 — #77 리뷰 반영 (내용 속 `*`·`-` 보존, 상한 경계)

- 리뷰(동한님): 기호 뒤 `\s*` 때문에 `*nix`·`*.yaml`·`-40°C`의 `*`·`-`까지 지워져 원문 의미가 바뀜.
  `•`·`∘` 같은 전용 기호는 그대로 떼고, `*`·`-`는 뒤에 공백이 오거나 기호만 있는 줄일 때만 떼도록 고쳤다.
- 상한 정책은 유지하고 경계를 명시했다: 카테고리별 최소 개수 보장 없음. (필수 19, 우대 1, 업무 1) → (19, 1, 0),
  필수 20개 이상이면 필수 앞 20개만 남는다. docstring과 `test_cap_boundaries`에 기록.
- 검증: `backend`에서 `python -m pytest tests/llm_tasks/test_jd_extract.py tests/integrations` 155 passed,
  변경 파일 대상 `ruff check`·`ruff format --check`·`mypy` 통과.

## 2026-10-06 — 도메인 category LLM 판정 (0022)

### 기준과 변경

- 작업 브랜치: `feature/domain-category-llm`, 기준 develop `ef1a48d`. #74의 키워드 규칙안은 채택하지 않았다.
- `ai/src/devon_ai/contracts.py`: `DomainPostingInput`(position·intro·main_tasks·requirements·preferred_points).
  회사명·`industry_name` 필드가 없어 구조상 입력할 수 없다.
- `ai/src/devon_ai/llm_tasks/domain_category.py`: `classify_domain`이 주입된 `model_call`로 한 번 호출하고
  `{category, evidence}`를 검증한다. `etc`가 아닌데 공백 정규화한 근거가 원문에 없으면 `etc`, schema·provider
  실패도 `etc`로 돌려준다(재호출 없음). 원문이 비면 호출하지 않는다. prompt·limits·입력 타입 오류는 호출 전에
  거절한다.
- `ai/prompts/domain-category-v1.md`: 검수 전 prompt 초안.
- `ai/tests/llm_tasks/test_domain_category.py`: 입력 계약 필드, 근거 채택·정규화, 근거 불일치·빈 근거의 `etc`,
  schema 위반 4종, provider 실패, 원문 없음 비호출, prompt 불일치 거절.

### 실행 결과

환경: Windows, uv. `ai`에서 `ruff check .`, `ruff format --check .`, `mypy`(12개 파일) 통과, `pytest -q`
205 passed. `backend`에서 `tests/agents/test_ai_package_imports.py` 1 passed.

### 검증 한계와 후속 작업

- 실제 provider 호출과 정확도 평가는 미실행이다(API 키 없음). 평가 도구는 원티드 개발 공고 100건 표본과
  미검토 라벨로 준비돼 있으며, 실행 시 데이터셋·모델 버전·비용·지표를 함께 기록한다.
- BE 연결은 범위 밖이다: `PostingContent.intro` 필드, `jd_extract` 단계 안 호출, `seed_prompt_versions.py`의
  `domain_category` 등록, BE adapter와 `postings.domain_category` 저장.

## 2026-10-26 — 도메인 category v2: 근거 문단 ID와 semantic 실패 기록 (0028, #99 리뷰 반영)

### 기준과 변경

- 작업 브랜치: `feature/domain-category-llm`, develop `2ff1acf`로 rebase. 리뷰 기준 원본은 `be44f00`.
- `ai/src/devon_ai/llm_tasks/domain_category.py`: 입력 필드를 `[{id, text}]` 문단 목록으로 바꿔 보내고
  `{category, evidence_id}`를 받는다. 요청별 문단 표로 만든 validator가 schema·semantic을 검사하고, 선택한
  ID의 원문을 `evidence`로 복원한다. 근거 검증이 공통 호출 계층 안으로 들어가 semantic 실패가 `failure`와
  attempt `error_stage/error_code`로 남는다(리뷰 P2).
- `ai/prompts/domain-category-v2.md`: 문단 ID 선택, 산업 전용 지원 서비스와 `mobility` 범위·경계. v1은 보존.
- `ai/tests/llm_tasks/test_domain_category.py`: 문단 변환(빈 줄 분리, 문단 안 줄바꿈 유지), ID의 원문 복원,
  정상 `etc` 성공, 잘못된 ID 4종(없는 ID, 인용문을 ID로, non-etc `null`, `etc`의 ID)의 semantic 기록·무재시도,
  schema 위반 5종, provider 실패, 원문 없음 비호출, prompt 불일치 거절.

### 실행 결과 (이 브랜치, 2026-10-26)

환경: Windows, uv. `ai`에서 `ruff check .`·`ruff format --check .`·`mypy`(12개 파일) 통과, `pytest -q` 209 passed.
`backend`에서 `tests/agents/test_ai_package_imports.py` 1 passed.

실제 BE `call_model` + `httpx.MockTransport`(외부 호출 없음)로 4개 응답을 확인했다.

| 모델 응답 | category | failure | attempt 오류 | HTTP 호출 |
| --- | --- | --- | --- | --- |
| `medical`, 있는 ID | `medical`(원문 복원) | 없음 | 없음 | 1 |
| `medical`, 없는 ID | `etc` | semantic | (semantic, llm_failed) | 1 |
| `medical`, `null` | `etc` | semantic | (semantic, llm_failed) | 1 |
| `etc`, `null` | `etc` | 없음 | 없음 | 1 |

### 리뷰어 실측 (동한님, 2026-10-12, 로컬 수정 후보 기준 — 이 브랜치 코드로 재실행하지 않음)

모델 `gpt-6-luna`, PR #114 gateway.

- v1, 원티드 공고 500건: 의료 4·금융 3건이 인용 재작성으로 `etc`, 실패 기록 누락 재현.
- v2, 같은 500건: 호출·근거 검증 실패 0건, 위 7건 medical 4 / finance 3 채택. 입력 토큰 916,031 → 1,244,571(+35.9%).
- v2, 회귀 61사례 61/61, 신규 회사 공고 40건 사전 기대 38/40(허용 경계 포함 39/40). 기대값은 확정된 사람
  정답표가 아니다.

### 검증 한계와 후속 작업

- 이 브랜치의 v2 코드·prompt로 실제 모델을 호출하지 않았다(API 키 없음). 리뷰어 수치는 같은 설계의 로컬 후보 결과다.
- ID 검증 성공은 분류 정확도를 보증하지 않는다. 사람 라벨 평가는 0022의 100건 표본 계획을 따른다.
- BE 연결은 0022와 같은 후속 범위이며, 등록할 prompt version은 `domain_category_v2`다.

## 2026-10-26 — #99 동시 갱신 보존 후 원문·version 회귀 보완

- 리뷰 대응 중 팀원 head가 `be44f001`에서 `ce1019a9`로 갱신된 것을 확인했다. 기존 로컬 수정·
  게시 후보는 보존하고 최신 head에서 새 작업 트리를 만들었다. 팀원의 v2 코드·기존 AI 테스트
  16사례·prompt·Accepted ADR0028·계약·실행 기록을 유지하며, 별도 중복 설계·ADR은 추가하지 않는다.
- 원문 ID·semantic 기록·산업 지원 범위의 주요 리뷰는 최신 팀원 변경이 해결했다. 이번 추가는
  원문 복원과 v2/schema 2 일치라는 같은 계약을 끝까지 지키는 보완과 실제 gateway 회귀다.
- `_paragraphs`에서 양 끝 공백을 지우지 않고 빈 문단만 제외한다. CRLF 빈 줄 경계는 정확히
  분리하되 문단 내부 줄바꿈·비가시 문자·오탈자·공백을 그대로 반환한다. v1/v3 prompt는 schema 2와
  혼용하지 않도록 모델 호출 전에 거절한다. 분류 정책·공개 API·DB 구조는 바꾸지 않는다.
- 팀원 테스트 파일은 교체하지 않고 `test_domain_category_review.py`에 8사례를 추가했다.
  source에 존재하는 ID도 현재 요청의 원문에서 복원하는지 검사한다. 산업 의미의 정확도 검사는 아니다.
- 실제 gateway 7사례는 `test_domain_category.py`에 별도로 둔다. raw·오류·실제 모델·token·version,
  semantic 무재시도·정상 etc·schema 오류 후 총 2회 상한을 검사한다. 테스트 helper만 #114의
  주소 인자가 있으면 명시적 fixture 주소를 주입한다. 제품의 기본 주소·호환 gateway는 추가하지 않는다.

| 최신 head 기준 이번 검증 | 실제 결과 |
| --- | --- |
| 보완 전 새 AI 회귀 | 7 failed / 1 passed. 공백·CRLF·버전 혼용을 실제로 재현 |
| 보완 후 팀원 기존 16 + 새 8사례 | 24 passed. 기존 테스트 파일 무변경 |
| AI 전체 pytest | 217 passed. 이전 로컬 후보 230개 결과와 구분 |
| BE import·기존 gateway·새 도메인 회귀 | 77 passed. 새 도메인 7사례 포함 |
| AI / BE Ruff·format·mypy | 모두 통과. format 45/254파일, type 12/133 source |
| 기존 전용 환경의 부분 계약 검사 | schema 2개·부분 OpenAPI·fixture 7개 통과. 전체 API/FE 호환성은 아님 |

검사 전후 Python 소스 해시는 같다. 외부 모델·GitHub 호출·패키지 설치는 0회이며 DB·서비스 완주와
실제 분류 품질은 검증하지 않았다. 로그는 `.claude/scratch/ai-pr-reviews-20261026/pr99-concurrent/`에
보존한다. 이전 v1·로컬 v2 후보·팀원 원본의 검증 수치를 이번 보완본의 새 결과로 합치지 않는다.
다른 PR과 새로 결합한 결과 및 실제 게시 head는 후속 게시·재검증에서 구분해 기록한다.

## 2026-10-26 — 포트폴리오 문서 Claim 추출 (0029)

### 기준과 변경

- 작업 브랜치: `feature/doc-claims`, 기준 develop `fca606a`(#99 머지 후). AI-L22 중 AI 추출 모듈 범위.
- `ai/src/devon_ai/llm_tasks/doc_claims.py`: `extract_claims`가 추출 텍스트의 비어 있지 않은 줄에 `L<순번>` ID를
  붙여 한 번 호출하고 `{claims: [{claim_text, claim_type, tech_tags, line_id}]}`를 받는다. 요청별 줄 표로 만든
  validator가 schema·semantic(없는 줄 ID)을 검사하고 줄 번호(`paragraph_no`)와 원문 줄을 복원한다. 실패하면
  Claim 없이 실패 정보를 돌려준다. 원문이 비면 호출하지 않고, prompt·limits·입력 타입 오류는 호출 전에 거절한다.
- `ai/prompts/doc-claims-v1.md`: 검수 전 prompt 초안. Claim 4종 정의, 뽑지 않는 것, 원문에 없는 기술·수치 추가 금지.
- `ai/tests/llm_tasks/test_doc_claims.py`: 줄 번호 부여(빈 줄 제외·CRLF 분리·양 끝 공백 유지), 줄 번호·원문 복원과 태그
  중복 제거, 빈 결과 성공, 없는 줄 ID 3종의 semantic 기록·무재시도, schema 위반 9종, provider 실패, 빈 문서
  비호출, 입력 거절 3종(다른 task prompt, `doc_claims_v1`이 아닌 version, 문자열이 아닌 입력).

### 실행 결과 (2026-10-26)

환경: Windows, uv. `ai`에서 `ruff check .`·`ruff format --check .`·`mypy`(12개 파일) 통과, `pytest -q` 213 passed.
`backend`에서 `tests/agents/test_ai_package_imports.py` 1 passed.

실제 BE `call_model` + `httpx.MockTransport`(외부 호출 없음)로 확인했다. gateway가 보내는 schema는 `strict: true`이며
모든 object 단계에서 `required`가 전체 속성과 같고 `additionalProperties: false`다.

| 모델 응답 | claims | failure | attempt 오류 | HTTP 호출 |
| --- | --- | --- | --- | --- |
| 정상 Claim 2개 | 2개(줄 번호 1·2) | 없음 | 없음 | 1 |
| 1개가 없는 줄 ID | 없음 | semantic | (semantic, llm_failed) | 1 |
| 없는 `claim_type` | 없음 | schema | (schema, llm_failed) | 2 (gateway schema 재시도) |
| `claims: []` | 없음 | 없음 | 없음 | 1 |

### 검증 한계와 후속 작업

- 실제 provider 호출과 추출 품질 평가는 미실행이다(API 키 없음). 실행 시 포트폴리오 표본·모델 버전·비용과
  누락·과잉 추출·원문에 없는 내용 추가를 함께 기록한다.
- BE 연결과 Director 사용은 범위 밖이다: `doc_extract` 단계 호출, BE adapter와 `document_claims` 저장,
  `seed_prompt_versions.py`의 `doc_claims` 등록, `claim_type` CHECK 여부, `Context`의 Claim 전달과
  `interview_turns.claim_ids` 기록(0029 영향 절).

## 2026-10-30 — PR #146 리뷰 후속: 검증 순서와 연결 범위 정정

### 기준과 변경

- 원본 PR head `099e7f3`를 `backup/pr146-before-review-fix-20261030`에 보존하고 후속 커밋만 추가했다.
  단독 검증과 최신 develop `2fc0103`에 합친 검증을 구분한다. 다른 미병합 구현을 추가하지 않았다.
- `doc_claims.py`는 모든 항목의 schema를 검사한 뒤 줄 ID를 검사한다. 같은 혼합 오류의 항목 순서를
  바꿔도 schema로 분류한다. 기존 정상 결과·4종·20개·태그 5개·원문 복원·전체 거절 정책은 유지한다.
- 회귀 5사례를 추가했다: 혼합 오류의 두 순서·동일 항목, 정상 항목 뒤 schema/semantic 오류의 부분 채택 방지.
  단일 호출 대역의 설명도 Gateway HTTP·재시도를 검증하는 것처럼 읽히지 않게 고쳤다.
- [0030](decisions/0030-document-claims-validation-boundary.md)과 내부 계약에서 독립 AI 모듈과 서비스 활성화,
  문서 Claim과 답변 `claim_checks`, 원문 ID 존재와 추출 충실성의 경계를 정정했다. 0029의 원본과 Accepted
  상태는 보존하고 후속 링크를 추가했다. FE·공개 API·DB·BE 호출·Director 소비 코드는 변경하지 않았다.

### 이번 수정 후 직접 실행한 검증

| 대상·명령 | 실제 결과 |
| --- | --- |
| 수정 전 새 회귀 포함 `pytest tests/llm_tasks/test_doc_claims.py` | 1 failed / 24 passed. 줄 ID 오류가 먼저인 혼합 응답의 분류 차이 재현 |
| 수정 후 동일 파일 | 25 passed |
| 수정 PR 단독 AI `pytest -q` | 303 passed |
| 최신 develop + 수정 PR AI `pytest -q` | 372 passed |
| 두 환경 AI Ruff·format·Mypy | 통과. format 54/60 files, Mypy 13/14 source files |
| 통합 BE 패키지 import·기존 `tests/contract` | 55 passed |
| 실제 Gateway + `httpx.MockTransport`, 단독/통합 각각 같은 13사례 | 통과. 혼합 오류 세 경우 모두 schema 재시도 후 정상 응답 채택(HTTP 2회), schema가 맞는 없는 ID는 semantic 종료(1회), 일부 채택 없음, 빈 입력 비호출·빈 결과 성공·byte 상한·취소 전파 확인 |
| 공통 계약 검사 | schema 2개·부분 OpenAPI·양성/음성 fixture 7개 통과. 전체 API·FE 호환성 검증 아님 |
| 최신 develop 병합 검사 | 충돌 없음. 최신 공통 계약·색인·구현 기록 보존 |

위 결과는 이전 검토의 298/367개나 작성 당시 213개를 재사용한 수치가 아니다. 이번 수정의 테스트를
현재 소스 경로에 고정해 실행했다. 실제 모델 호출·추출 품질 데이터셋·BE 저장/분석·면접 서비스 흐름·
전체 DB/Redis suite·배포 검증은 미실행이다. 실패·시도 정보의 영구 기록, 문서 버전별 실행 상태·중복 방지,
prompt 등록·adapter·Context/질문 근거 연결은 후속이다. 로그·source hash·정확한 명령은
`.claude/scratch/pr146-review-fix-20261030/`에 보존한다.

<a id="issue109-ai-docs-20261103"></a>

## 2026-11-03 — #109 AI 현재 안내의 상태 표현 정리

### 범위와 유지한 기준

- 기준은 #168까지 병합된 develop `460f5fe`다. 기존 결정에 따른 AI 문서의 의미·참조를 정리했으며
  기능·API·DB·모델·재시도 정책을 변경하지 않았다. BE 기능 PR 전체를 선행으로 복사하지 않았다.
- [문서 역할과 상태 표현](../../ai/README.md#ai-document-status)에서 실제 결정 필요, 채택된 방향의
  구현·검증, 현재 범위 밖, 검증 미실행을 구분한다. 사용자 명시 보류·평가 판단 유보·과거 상태는 보존한다.
  이 안내는 새 runtime 상태·승인 절차를 정의하지 않는다.
- 0018의 기존 Sprint 1 채택 범위와 후속 결정의 변경 범위를 따르고, Proposed·Accepted·FIX를
  실제 구현 완료 상태로 바꾸지 않았다. 0020의 단일 AI 구현 기록 원칙과 기존 문서 경로를 유지한다.

### 표현 대응과 근거

| 대상 | 정리한 안내 | 근거와 보존 범위 |
| --- | --- | --- |
| AI README·pipeline | 승인 방향은 결정 기록, 구현·검수 조건은 AI-L 인계표, 실제 현황은 이 기록으로 연결 | 0018·0020. pipeline의 이전 제목 앵커 보존 |
| task-01~13 | 포괄적인 결정 대기와 이미 채택된 범위의 구현·검증 조건을 구분. task-05는 기존 안내 유지 | 0010·0014·0015·0018. 미채택 상세 계약·실제 합의 필요 범위는 유지 |
| README·testing·layer-rules | loader·분석 모듈·테스트가 없다는 고정 현황 대신 책임·검증 조건과 원본 안내 | develop의 `ai/evals/eval_cases.py`·`grader_check.py`와 관련 경계 확인. 도구 존재가 실제 모델 평가 완료를 뜻하지 않음 |
| pipeline의 seed 안내·리포트 입력 조건 | 초안 작성과 채택·검수·실제 연결을 구분 | `seed_score_criteria.py`의 초안·비활성·환산 미확정 제한 유지 |
| architecture·contracts·verification | 승인 상태·구현 조건·검증 단계·당시 확인 이력을 구분 | 0018·0020. 계약 필드·값·운영 상한의 기존 설정·실측 책임 유지 |
| L1/L2·Evidence·analysis-scope | schema 승인 범위, 준비·조회 조건, 실제 읽기 한계를 구분 | 0003·0008·0010·0015·0018. 평가 유보·미발견·거짓의 구분 유지 |

과거 ADR·초기 설계·원본 감사·실행 프롬프트·평가 사실표와 기존 구현 기록은 변경하지 않고,
현재 안내만 필요한 곳에서 참조화했다. task-04와 pipeline의 기존 제목 앵커는 명시 앵커로 남겼다.

### 이번 검증

| 검사 | 결과·범위 |
| --- | --- |
| 수정 전 기준 AI 전체 | 428 passed |
| 수정 후 작업본 AI 전체 | 428 passed |
| AI Ruff·format·mypy | 통과. format 65파일, mypy 16소스 |
| BE AI 패키지 연결 | 1 passed. 서비스 전체·DB·실제 모델 검증을 대체하지 않음 |
| 게시 전 공통 계약 검사 | 부분 검사: schema 2개·부분 OpenAPI·양성/음성 fixture 7개 통과. BE `tests/contract` 54 passed. 전체 API·FE·서비스 호환성 검증은 아님 |
| 문서·코드의 내부 참조 | Markdown 187개와 UTF-8 코드·설정 528개의 참조 1,464개 검사. 경로·앵커 오류와 기존 앵커 손실 0개 |
| 보존 대조·의미 검토 | 역사 문서 37개·날짜별 기록 48구간·기존 구현 기록 1,544줄 보존. 보호 지침·실행 코드·프롬프트·평가자료 변경 없음. 독립 검토의 기본 질문 생성 경로 한정 문구 보완 후 잔여 지적 없음 |

검사 대상 모듈이 이번 작업본에서 import되는지 확인했고 실행 전후 runtime·테스트·설정 소스 해시가 같다.
YAML·실행 코드 변경, 실제 모델 평가·전체 서비스 실행·운영 배포 검증은 이번 문서 정리 범위에 포함하지 않았다.
문장별 근거, 파일 분류, 링크·앵커·보존 검사와 실행 로그는 `.claude/scratch/issue109-ai-fix-20261103/`에 보존한다.

### 후속 범위

AI 정리는 #109 전체의 BE·FE·shared 문서 구조 결정을 완료한 것이 아니다. 해당 범위는 별도로 처리하거나
이월해야 한다. 단일 기록 안의 고유 절과 안정 앵커로 편집 범위를 구분하되 여러 PR의 같은 구간 편집
충돌이 없어졌다고 보장하지 않는다.


<a id="issue109-ai-supplement-20261103"></a>

## 2026-11-03 — #109 AI 문서 후속 보완

기준은 develop ` 58966c4 `과 [#179 후속 리뷰](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/179#issuecomment-6600334400)다. 제목·상한 표현·기존 ID 매핑·결과 설명·현황 참조와 공개 근거를 보완했다. 실행 코드·계약·승인 상태·운영 수치를 바꾸거나 구현 기록의 물리 구조를 분리하지 않았다.

### 이번 안내 문구의 대응표

아래 표는 이번 보완에서 바뀐 안내 문구의 비공백 줄을 파일별로 모두 대응시킨다. L 번호는 각각 기준 원문과 보완 문서의 위치이며, 공백·줄바꿈 정리와 이 새 기록 자체는 문구 대응 대상과 구분한다. 원문 근거는 공개된 고정 SHA, 새 문구는 이 보완본의 해당 문서에서 확인한다.

| 대상·기준 원문 | 이전 문구 | 보완 문구 | 기존 근거 | 유지한 의미·제한 |
| --- | --- | --- | --- | --- |
| [ai/docs/analysis-scope.md](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/58966c46d8861c55493d9368ba0de2b471aa2c0a/ai/docs/analysis-scope.md#L25) | ` L25: > directory path 는 AI-L08 상한 승인 전 자동 재귀·전체 tree·global keyword search 로 확장하지 않는다. ` | ` L25: > directory path를 임의 재귀 탐색·전체 tree·global keyword search로 확장하지 않는다. 기존 허용 범위의 파일 열거·인접 후보 조회도 AI-L08의 [운영 상한을 설정·검증](pipeline.md#ai-runtime-limits)한 뒤 실제 I/O에 연결한다. 상한 설정은 검색 범위를 확대하는 승인이 아니다. ` | [0018](decisions/0018-existing-baseline-bulk-resolution.md)·[0020](decisions/0020-implementation-record-policy.md) | 검색 범위 확대 금지와 설정·검증 전 실제 I/O 차단을 유지. |
| [ai/docs/pipeline.md](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/58966c46d8861c55493d9368ba0de2b471aa2c0a/ai/docs/pipeline.md#L101) | ` L101: AI-L04·08의 실제 상한 설정·실측과 AI-L18의 저장 위치·마스킹·접근·보관·재사용 연결도 구현 작업이다. 사용 범위·운영 조건·자료 정책의 채택 내용은 0018을 따르며 숫자·필드·도구 선택을 하나씩 묻지 않는다. 이 표로 구현·검수·출시를 완료 처리하지 않는다. ` | ` L85: 과거 [0003](../../spec/ai/decisions/0003-evidence-lookup-policy.md)의 운영·계약 대기 범위는 후속 [0010의 재시도 책임](../../spec/ai/decisions/0010-sprint1-interface-runtime-decisions.md#llm-attempt와-worker-retry), [0015의 기존 Evidence·ToolResult 채택](../../spec/ai/decisions/0015-existing-contracts-and-tool-results.md), [0018의 운영 설정·실측 기준](../../spec/ai/decisions/0018-existing-baseline-bulk-resolution.md#운영-범위와-남은-구현검증)과 함께 읽는다. 당시 승인 범위 기록은 보존하며, 후속 결정이 채택하지 않은 새 계약·범위까지 승인된 것으로 넓히지 않는다. `<br>` L92: \| AI-L04 \| 실행 상한·재시도 책임. [0008의 실패 분류](../../spec/ai/decisions/0008-ai-candidate-policy.md#구조화-후보-실패)와 [0010](../../spec/ai/decisions/0010-sprint1-interface-runtime-decisions.md#llm-attempt와-worker-retry)에 따라 공통 LLM 호출 계층의 한 요청은 최초 호출과 허용된 재호출을 합쳐 최대 총 2회이며 semantic 실패는 재호출하지 않음. ARQ max_tries=1 유지. runtime 전체·면접 전체의 호출 횟수로 확대하지 않고, timeout·token·Context·동시성·Tool·재작성/재계획 budget과 소진 처리는 [운영 상한 기준](#ai-runtime-limits)으로 구현·검증 \| AI [task-03](task-03-llm-boundary.md)·[08](task-08-evidence-tools.md)·[13](task-13-backend-integration.md), BE LLM 호출 계층·worker \| `<br>` L93: \| AI-L05 \| 분석 단계와 JD 선행 관계. [0010](../../spec/ai/decisions/0010-sprint1-interface-runtime-decisions.md#jd-신호와-추천-단계)의 외부 7단계와 첫 repo_select의 JD 신호 미사용 유지. JD 기반 추천은 match_score·후속 후보 페이지에서 처리. [0006](../../spec/ai/decisions/0006-task-llm-usage-policy.md)의 Wanted 규칙 변환·LLM 비호출을 단계 삭제·재정렬로 해석하지 않고 입력 가용 시점·유효 L1 저장·추천 응답 연결을 검사 \| AI [task-04](task-04-repo-shallow.md)·[06](task-06-context-preparation.md)·[13](task-13-backend-integration.md), BE 분석 pipeline·추천 \| `<br>` L96: \| AI-L08 \| 제한 근거 조회. [0003의 세 조건](../../spec/ai/decisions/0003-evidence-lookup-policy.md#추가-조회-조건), [0008의 후보 우선순위](../../spec/ai/decisions/0008-ai-candidate-policy.md#evidence-후보-우선순위), [0015의 부분 오류 처리](../../spec/ai/decisions/0015-existing-contracts-and-tool-results.md#toolresult와-일부-조회-오류)를 유지. repo·고정 SHA·허용 path·권한·출처를 재검증하고 열거 방식·주변 범위·깊이/개수·byte/token/time 상한은 [운영 상한 기준](#ai-runtime-limits)으로 구현·검증. 미설정 실제 I/O나 임의 재귀 탐색·전체 tree·global search로 확장하지 않으며 [0002의 vector 미도입](../../spec/ai/decisions/0002-sprint1-vector-search.md) 유지 \| AI [task-05](task-05-repo-deep.md)·[08](task-08-evidence-tools.md)·[13](task-13-backend-integration.md), BE Tool adapter·GitHub I/O \| `<br>` L102: \| AI-L14 \| 면접 식별자·준비·텍스트 WS·재접속 복구. [0010](../../spec/ai/decisions/0010-sprint1-interface-runtime-decisions.md#websocket과-준비-흐름)의 REST interviewId/WS sessionId 구분, answer·answerReceived·question 의미, 준비 단계·REST 재시도·기존 snapshot 복구를 유지. 인증만 후속 [공통 0003의 devon_session](../../spec/shared/decisions/0003-sprint1-session-auth.md)을 적용하고 권한·DB 복구·저장 질문 재전달·실제 송수신을 검사. 새 wire·토큰·상태를 임의 추가하지 않음 \| AI [task-06](task-06-context-preparation.md)·[13](task-13-backend-integration.md), BE [task-13](../../backend/docs/task-13-interview-rest.md)·[15](../../backend/docs/task-15-interview-ws.md), FE 면접 \| `<br>` L104: \| AI-L16 \| Lazy report 생성·실패 처리. [0010](../../spec/ai/decisions/0010-sprint1-interface-runtime-decisions.md#lazy-report와-profile-summary)의 completed·답변 완료 1개 이상 조건과 기존 결과 200·생성/생성 중 202·생성 불가/이전 실패 409 유지. 성공본 재사용·중복 enqueue 방지·실패 이력의 실제 저장/응답을 검사. Sprint 1에 자동 재생성·수동 재시도·이의제기 기반 재평가를 추가하지 않음 \| AI [task-11](task-11-report.md)·[13](task-13-backend-integration.md), BE [task-16](../../backend/docs/task-16-report.md), FE 리포트 조회 \| `<br>` L105: \| AI-L17 \| 프로필 집계·개인 역할 요약. [0015](../../spec/ai/decisions/0015-existing-contracts-and-tool-results.md)의 profile_summary(user_id)·기존 저장/공개 필드와 [0016의 완료 면접 사용 repo 중복 제거·저장소별 동일 비중 언어 평균](../../spec/ai/decisions/0016-profile-language-aggregation.md#집계-기준) 유지. 역할 요약은 0006·0016의 보류를 철회한 [0019의 기존 LLM 요약](../../spec/ai/decisions/0019-sprint1-profile-role-summary-restoration.md)을 적용. 통계는 LLM에 맡기지 않고 자료 누락·근거 없는 개인 기여를 성공으로 꾸미지 않음. report 성공 후 갱신·응답 비차단·실패 독립과 기존 저장/화면 연결을 검증 \| AI [task-11](task-11-report.md)·[13](task-13-backend-integration.md), BE [task-16](../../backend/docs/task-16-report.md), FE 프로필·Home \| `<br>` L109: <a id="ai-runtime-limits"></a> `<br>` L111: ### 운영 상한의 설정과 검증 `<br>` L113: AI-L04·08의 실제 상한 설정·실측은 [0018의 운영 범위와 남은 구현·검증](../../spec/ai/decisions/0018-existing-baseline-bulk-resolution.md#운영-범위와-남은-구현검증)을 따른다. 내부 대표 입력·계정 한도에 맞춰 유한한 실행 설정·비용 범위를 먼저 정하고 측정으로 조정하며, 사용자가 지정한 한도가 있으면 우선한다. 미설정을 무제한 조회로 바꾸거나 설정·검증 전에 실제 I/O를 연결하지 않는다. `<br>` L115: AI는 요청 판단·후보 선택·결과 해석 정책을, BE는 adapter·설정·권한 검사·실제 I/O와 상한 소진 시 차단을 소유한다. [AI task-03](task-03-llm-boundary.md)·[08](task-08-evidence-tools.md)·[13](task-13-backend-integration.md)에서 정책 fixture·상한 측정·실제 연결 검증을 구분한다. AI-L18의 저장 위치·마스킹·접근·보관·재사용 연결도 구현 작업이다. 사용 범위·운영 조건·자료 정책의 채택 내용은 0018을 따르며 숫자·필드·도구 선택을 하나씩 묻지 않는다. 이 표로 구현·검수·출시를 완료 처리하지 않는다. ` | [0018](decisions/0018-existing-baseline-bulk-resolution.md)·[0020](decisions/0020-implementation-record-policy.md) | 기존 13행 보존, 후속 결정의 채택 범위·책임만 연결. 새 수치·wire·기능 완료를 추가하지 않음. |
| [ai/docs/task-02-contracts.md](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/58966c46d8861c55493d9368ba0de2b471aa2c0a/ai/docs/task-02-contracts.md#L73) | ` L73: ## 결정 대기와 재개 조건 ` | ` L14: [PR #50 계약 검증 재검토](../../spec/ai/implementation.md#2026-09-27--pr-50-계약-검증-재검토-반영)와 `<br>` L15: [PR #56 기반 범위](../../spec/ai/implementation.md#pr-56의-현재-범위)는 당시의 순수 검증·저장 값 변환 범위 기록이다. `<br>` L16: 현재 DB·공개 API 전체의 완료 여부는 이 부분 기록만으로 판단하지 않는다. `<br>` L77: <a id="결정-대기와-재개-조건"></a> `<br>` L79: ## 구현·검증 조건과 검토 범위 ` | [0018](decisions/0018-existing-baseline-bulk-resolution.md)·[0020](decisions/0020-implementation-record-policy.md) | 기존 채택/미채택 상세·운영/연결 검수 조건 유지. 과거 부분 기록을 현재 전체 완료로 보지 않음. |
| [ai/docs/task-03-llm-boundary.md](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/58966c46d8861c55493d9368ba0de2b471aa2c0a/ai/docs/task-03-llm-boundary.md#L86) | ` L86: ## 결정 대기와 재개 조건 ` | ` L14: 공통 호출·설정·prompt loader/seed의 당시 범위는 [PR #56 기반 기록](../../spec/ai/implementation.md#pr-56의-현재-범위)에서 확인한다. `<br>` L15: 이 부분 기록을 실제 모델 품질·운영 검수 완료로 확대하지 않으며, 이후 연결·실행 결과는 위 구현 기록에서 확인한다. `<br>` L89: <a id="결정-대기와-재개-조건"></a> `<br>` L91: ## 구현·검증 조건과 검토 범위 ` | [0018](decisions/0018-existing-baseline-bulk-resolution.md)·[0020](decisions/0020-implementation-record-policy.md) | 기존 채택/미채택 상세·운영/연결 검수 조건 유지. 과거 부분 기록을 현재 전체 완료로 보지 않음. |
| [ai/docs/task-06-context-preparation.md](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/58966c46d8861c55493d9368ba0de2b471aa2c0a/ai/docs/task-06-context-preparation.md#L82) | ` L82: ## 결정 대기와 재개 조건 ` | ` L5: [PR #156 후속 기록](../../spec/ai/implementation.md#pr156-review-followup-20261031)은 cron·답변 Context 경계의 당시 검증이다. `<br>` L6: 준비 전체의 현재 완료 여부는 이 부분 기록만으로 판단하지 않는다. `<br>` L85: <a id="결정-대기와-재개-조건"></a> `<br>` L87: ## 구현·검증 조건과 검토 범위 ` | [0018](decisions/0018-existing-baseline-bulk-resolution.md)·[0020](decisions/0020-implementation-record-policy.md) | 기존 채택/미채택 상세·운영/연결 검수 조건 유지. 과거 부분 기록을 현재 전체 완료로 보지 않음. |
| [ai/docs/task-08-evidence-tools.md](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/58966c46d8861c55493d9368ba0de2b471aa2c0a/ai/docs/task-08-evidence-tools.md#L90) | ` L90: ## 결정 대기와 재개 조건 ` | ` L5: 조회 한계 전달의 일부 검증은 [#124 후속 기록](../../spec/ai/implementation.md#2026-10-28--124-후속-검토의-미실행-조회-범위-보존)에서 확인한다. `<br>` L6: 해당 절은 당시 생략 범위·결과 전달 경계의 기록이며, 전체 Tool·운영 GitHub 호출의 현재 완료를 뜻하지 않는다. `<br>` L93: <a id="결정-대기와-재개-조건"></a> `<br>` L95: ## 구현·검증 조건과 검토 범위 ` | [0018](decisions/0018-existing-baseline-bulk-resolution.md)·[0020](decisions/0020-implementation-record-policy.md) | 기존 채택/미채택 상세·운영/연결 검수 조건 유지. 과거 부분 기록을 현재 전체 완료로 보지 않음. |
| [ai/docs/task-09-answer-analysis.md](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/58966c46d8861c55493d9368ba0de2b471aa2c0a/ai/docs/task-09-answer-analysis.md#L83) | ` L83: ## 결정 대기와 재개 조건 ` | ` L5: 단발 분석의 입력·검증·mock 대조 범위는 [task-09 구현 당시 기록](../../spec/ai/implementation.md#2026-10-06--task-09-답변-분석-task-구현)에서 확인한다. `<br>` L6: 이후 service·저장·후속 보완의 연결·실행 여부는 위 구현 기록의 관련 후속 절과 구분해 확인한다. `<br>` L86: <a id="결정-대기와-재개-조건"></a> `<br>` L88: ## 구현·검증 조건과 검토 범위 ` | [0018](decisions/0018-existing-baseline-bulk-resolution.md)·[0020](decisions/0020-implementation-record-policy.md) | 기존 채택/미채택 상세·운영/연결 검수 조건 유지. 과거 부분 기록을 현재 전체 완료로 보지 않음. |
| [ai/docs/task-10-director.md](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/58966c46d8861c55493d9368ba0de2b471aa2c0a/ai/docs/task-10-director.md#L7) | ` L7: 기본 질문 생성과 후속 Director 실행·BE 연결의 실제 구현·검증 범위는 `<br>` L8: [AI 구현·검증 기록](../../spec/ai/implementation.md)에서 확인한다. `<br>` L121: ## 결정 대기와 재개 조건 `<br>` L125: \| 항목 \| 지금 가능한 작업 \| production 연결 재개 조건 \| ` | ` L7: 기본 질문 생성의 후보 복구 분류는 [task-10 분류 경계 기록](../../spec/ai/implementation.md#2026-10-06--task-10-director-후보-복구-분류-경계), `<br>` L8: 후속 실행·BE 연결의 일부 검증은 [Director 연결 기록](../../spec/ai/implementation.md#director-review-integration-20261030)과 `<br>` L9: [PR #156 후속 기록](../../spec/ai/implementation.md#pr156-review-followup-20261031)에서 확인한다. `<br>` L10: 각 절은 해당 시점·범위의 기록이며 현재 전체 구현·검증 현황은 [AI 구현·검증 기록](../../spec/ai/implementation.md)에서 확인한다. `<br>` L123: <a id="결정-대기와-재개-조건"></a> `<br>` L125: ## 구현·검증 조건과 검토 범위 `<br>` L129: \| 항목 \| 지금 가능한 작업 \| production 연결·검증 조건 \| ` | [0018](decisions/0018-existing-baseline-bulk-resolution.md)·[0020](decisions/0020-implementation-record-policy.md) | 기존 채택/미채택 상세·운영/연결 검수 조건 유지. 과거 부분 기록을 현재 전체 완료로 보지 않음. |
| [ai/docs/task-12-evaluation.md](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/58966c46d8861c55493d9368ba0de2b471aa2c0a/ai/docs/task-12-evaluation.md#L73) | `` L73: - [ ] 통과·실패·보류·미실행·범위 밖 상태를 모두 기록한다. `pending`과 무효 사례는 ``<br>` L118: ## 결정 대기와 재개 조건 `<br>` L122: \| 항목 \| 지금 가능한 작업 \| 실제 평가 재개 조건 \| ` | ` L5: 로컬 loader·grader의 확인 범위는 [평가 로컬 도구 현황](../../spec/ai/implementation.md#eval-local-tools-status-20261103)에서 별도로 확인한다. `<br>` L75: - [ ] 실행 결과와 미실행·범위 밖 사유를 [결과 상태](testing.md#결과-상태)에 따라 모두 기록하고, `<br>`` L76:   판단을 유보했다면 대상·이유를 남긴다. 사례 검수 상태 `pending`과 무효 사례는 ``<br>` L121: <a id="결정-대기와-재개-조건"></a> `<br>` L123: ## 구현·검증 조건과 검토 범위 `<br>` L127: \| 항목 \| 지금 가능한 작업 \| 실제 평가 진행 조건 \| ` | [0007](decisions/0007-evaluation-design-policy.md)·[0009](decisions/0009-ai-evaluation-method.md)·[검증 구분](verification.md#검증-단계를-구분한다) | pending 검수 상태·전체 수·품질 분모와 실제 모델 미검증을 유지. |
| [ai/docs/testing.md](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/58966c46d8861c55493d9368ba0de2b471aa2c0a/ai/docs/testing.md#L7) | `` L7: 모든 검사는 `통과`, `실패`, `보류`, `미실행`, `범위 밖`으로 구분한다. 빈 테스트 수집, import 성공, README 명령 예시, 정적 형식 검사만으로 AI 기능·모델 품질·서비스 흐름이 통과했다고 기록하지 않는다. ``<br>`` L147: 각 task의 완료 체크에는 해당 테스트의 생성 여부, 수집 개수, 명령·결과, 합의한 계약 범위와 남은 AI-L ID를 함께 남긴다. `task-13`의 저장·WS·worker 통합 검사나 실제 모델 품질 검사가 보류라면 패키지 단위 검사가 통과해도 서비스 전체 완료를 선언하지 않는다. `` | ` L7: 검사 결과는 [검증 기준](../../spec/ai/verification.md#검증-단계를-구분한다)에 따라 실행 여부와 판단 가능 여부를 구분해 기록한다. `<br>`` L8: 실행한 검사는 `통과`·`실패`를, 실행하지 않은 검사는 `미실행` 사유 또는 `범위 밖` 조건을 남긴다. ``<br>`` L9: 여기서 `보류`는 자료·근거 부족으로 판단을 유보했다는 뜻이며 해당 판단의 범위와 이유를 적는다. ``<br>`` L10: `보류`를 미실행·미구현이나 추가 결정 필요의 대체 표현으로 쓰지 않는다. ``<br>`` L11: 사례 검수 상태 `pending`은 검수자 불일치를 뜻하며 실행 결과와 별도로 기록한다. ``<br>` L12: 빈 테스트 수집, import 성공, README 명령 예시, 정적 형식 검사만으로 AI 기능·모델 품질·서비스 흐름이 통과했다고 기록하지 않는다. `<br>` L152: 각 task의 완료 체크에는 해당 테스트의 생성 여부, 수집 개수, 명령·결과, 합의한 계약 범위와 남은 AI-L ID를 함께 남긴다. `<br>`` L153: `task-13`의 저장·WS·worker 통합 검사나 실제 모델 품질 검사가 미실행이거나 판단 근거 부족으로 유보된 경우에는 ``<br>` L154: 패키지 단위 검사 통과만으로 서비스 전체 완료를 선언하지 않는다. ` | [0007](decisions/0007-evaluation-design-policy.md)·[0009](decisions/0009-ai-evaluation-method.md)·[검증 구분](verification.md#검증-단계를-구분한다) | pending 검수 상태·전체 수·품질 분모와 실제 모델 미검증을 유지. |

### 기존 #179의 민감한 표현 전환 추적

전체 변경은 [고정 SHA 비교](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/compare/460f5fef515ef4ab4bd17bb29b60aab34732dbb0...af53445ccb373ed226eefffe1876b19aaeaaa491)로 확인한다. 두 SHA의 파일과 실제 ADR/계약 근거를 연결했으며, 로컬 scratch를 승인 근거로 삼지 않는다. 표의 발췌와 전체 문맥은 연결한 원문·수정문을 함께 읽는다.

| 대상·원문 위치 | 이전 표현 | #179에서 정리한 표현 | 기존 근거 | 유지한 의미·제한 |
| --- | --- | --- | --- | --- |
| task-04 출력 필드 [전](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/460f5fef515ef4ab4bd17bb29b60aab34732dbb0/ai/docs/task-04-repo-shallow.md#L69)·[후](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/ai/docs/task-04-repo-shallow.md#L69) | `채택되지 않은 출력 필드·저장 매핑·retry budget을 구현하지 않는다.` | `출력 필드·저장 매핑은 채택 범위와 기존 구조에 맞춰 구현·검증하고, 운영 budget을 임의의 확정값이나 무제한으로 대체하지 않는다.` | [0018 AI-L02·03·04](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/spec/ai/decisions/0018-existing-baseline-bulk-resolution.md#L22) | 채택한 기존 계약 안의 상세 구현과 계약 밖 새 필드·정책을 구분한다. 새 구조 도입이나 미설정 무제한 실행은 허용하지 않는다. |
| task-08 실제 조회 연결 [전](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/460f5fef515ef4ab4bd17bb29b60aab34732dbb0/ai/docs/task-08-evidence-tools.md#L92)·[후](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/ai/docs/task-08-evidence-tools.md#L94) | `디렉터리 열거·인접 후보 생성, 실제 Tool I/O, 주변 범위·깊이·개수와 byte/token/time 상한이 합의되면 제한 검색을 연결한다.` | `기존 허용 범위에서 디렉터리 열거·인접 후보 생성과 실제 Tool I/O를 구현한다. 주변 범위·깊이·개수와 byte/token/time 상한은 운영 조건·대표 사례 측정으로 설정·검증한 뒤 제한 검색에 연결한다.` | [0018 AI-L04·08·11](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/spec/ai/decisions/0018-existing-baseline-bulk-resolution.md#L23)·[운영 범위](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/spec/ai/decisions/0018-existing-baseline-bulk-resolution.md#L45) | 기존 제한 검색 범위의 설정·측정 조건을 명시한다. 새로운 검색 방식 승인이나 상한 설정 전 실제 I/O 허용으로 바꾸지 않는다. |
| task-06 준비 판정 [전](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/460f5fef515ef4ab4bd17bb29b60aab34732dbb0/ai/docs/task-06-context-preparation.md#L66)·[후](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/ai/docs/task-06-context-preparation.md#L66) | `AI-L06 결정 전에는 부분 결과의 최종 성공/실패 기대값을 임의로 고정하지 않는다.` | `0010의 채택 기준에 따라 primary repo 1~2개 중 검증된 notable area가 1개 이상인 repo가 있으면 준비 성공을 허용하고, 총 0개면 preparing_failed인지 검사한다.` | [0010 L2 partial success](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/spec/ai/decisions/0010-sprint1-interface-runtime-decisions.md#L59)·[0018 AI-L06](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/spec/ai/decisions/0018-existing-baseline-bulk-resolution.md#L24) | 이미 채택된 기준을 다시 결정 대기로 돌리지 않는다. 실제 지원 언어·무효 path 제외·저장·준비 연결은 별도 구현·검증 대상이다. |
| task-10 기본 생성 경로 [전](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/460f5fef515ef4ab4bd17bb29b60aab34732dbb0/ai/docs/task-10-director.md#L7)·[후](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/ai/docs/task-10-director.md#L7) | 발췌: `모델이 계약을 다시 출력하거나 바꾸게 하지 않는다.` | 발췌: `기본 generate_question 경로에서는 모델이 입력 QuestionContract를 다시 출력하거나 바꾸게 하지 않는다.` | [현행 Director 계약](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/spec/ai/contracts.md#L72)·[0020](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/spec/ai/decisions/0020-implementation-record-policy.md#L18) | 기본 생성기의 입력 계약 불변을 후속 run_director 전체에 확대하지 않는다. 기본 CandidateRecovery의 세 실패 전달과 실행·재호출 없음은 유지한다. |
| task-12 구현 상태 안내 [전](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/460f5fef515ef4ab4bd17bb29b60aab34732dbb0/ai/docs/task-12-evaluation.md#L3)·[후](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/ai/docs/task-12-evaluation.md#L3) | `현재 실제 평가자료와 loader·harness·채점기는 미구현이다.` | `평가 도구·자료·실행의 실제 구현·검증 범위는 AI 구현·검증 기록에서 확인한다.` | [0020 문서 역할](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/spec/ai/decisions/0020-implementation-record-policy.md#L18)·[#161](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/161)·[loader](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/ai/evals/eval_cases.py#L121)·[채점기 검사](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/af53445ccb373ed226eefffe1876b19aaeaaa491/ai/evals/grader_check.py#L33) | 도구 코드의 존재·합성 경계 검사와 실제 사례·독립 검수·모델 평가 완료를 구분한다. task에 낡은 현황을 중복 기록하지 않는다. |

위 표는 대표적인 의미 전환 5개를 추적한다. 기존 92개 diff hunk 전체의 문장별 사전 합의를 증명하는 표는 아니다. 과거 변경 전체는 고정 비교 링크로 보존하며 이번 대응표와 혼합하지 않는다.

<a id="eval-local-tools-status-20261103"></a>

### 로컬 합성 평가 도구의 확인 범위

기준 소스는 develop `58966c4`다. [#161](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/161)에서
추가된 두 도구가 현재 소스에 있음을 확인했다. 도구를 읽어 확인한 범위와 실제 모델·사례 평가 완료는 구분한다.

- [`eval_cases.py`](../../ai/evals/eval_cases.py)는 합성 입력·기대 JSON 쌍을 읽는다. 짝·version·파일 이름
  불일치, 중복, 입력 쪽의 계약 밖 필드, 비합성 사례, 같은 source group의 dev/holdout 교차와
  잘못된 검수 메타데이터를 거부한다. `Case.model_input()`은 기대값·검수·제어 정보와 분리된
  `payload` 복사본만 반환한다.
- [`grader_check.py`](../../ai/evals/grader_check.py)는 호출자가 주입한 채점기에 허용·금지 기준과
  control 출력을 전달해 비교한다. control 종류는 채점기에 주지 않으며, 종류별
  `correct`·`false_accept`·`false_reject`·`abstained`·`error`를 기록한다.
  미승인 사례는 전체 수에 남기되 품질 분모에서 제외하고, 승인돼도 control 출력이 없으면
  `no_controls`로 제외한다. 이 모듈 자체가 실제 LLM judge는 아니다.
- 관련 경계 검사는 [`test_eval_data_boundaries.py`](../../ai/tests/test_eval_data_boundaries.py)와
  [`test_eval_grader_check.py`](../../ai/tests/test_eval_grader_check.py)에 있다. 임시 합성 JSON과
  대역 채점기로 입력 분리·검수·집계 경계를 확인하며, 실제 모델 판정 품질 검사가 아니다.
- 현재 추적된 `ai/evals/inputs/`에는 `.gitkeep`, `expectations/`에는 `.gitkeep`과
  `fact-table.md`가 있고 JSON 사례는 없다. 실제 사례 작성·독립 검수·모델 실행·품질 수용 기준 충족을
  완료로 표시하지 않는다. 도구는 `src/devon_ai` 런타임 패키지 밖에 있다.
- control 종류별 기대 판정과 사례 검수 담당·완료 방식에는 작성자 제안이 남아 있다.
  `review.status`의 `unreviewed`·`approved`·`pending`·`invalid` 값과
  [평가 안내](../../ai/evals/README.md)의 검수 경계를 이 보완에서 변경하지 않았다.

### 열린 PR의 참조 영향

[#184](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/184)의 task-08 문구는 유지되며, 기존 61행의 근거 두 용도 항목은 64행, 기존 52행의 디렉터리 제한 항목은 55행으로 이동한다. task-05와 Evidence 계약 앵커는 보존했다. 줄 번호 이동과 문서 링크 파손을 구분하며 기존 PR 본문은 수정하지 않았다.

### 이번 실행·보존 확인

실행 시 작업본의 ai/src와 backend를 PYTHONPATH로 고정하고 기존 격리 Python 환경을 재사용했다. 기준본과 보완본은 따로 실행했으며 수를 합산하지 않는다.

| 검사 | 이번 결과·한계 |
| --- | --- |
| AI 전체 pytest | 기준본 428 passed, 보완본 428 passed |
| 로컬 평가 도구 경계 | 두 테스트 파일 43개 통과. 위 전체 검사에 포함되며 합성 JSON·대역 grader 검사임 |
| AI Ruff·format·mypy | 통과. format 65파일, mypy 16소스 |
| BE AI 패키지 연결 | 1 passed. 서비스·DB·실제 모델 연결 완료를 뜻하지 않음 |
| 부분 계약 검사 | schema 2개·부분 OpenAPI·fixture 7개 통과. 전체 호환성 검증 아님 |
| 내부 참조 | Markdown 187개·UTF-8 비Markdown 532개에서 1,547개 검사. 오류·기존 앵커 손실 0개 |
| 원본 보존 | 기존 구현 기록 1,594줄·날짜별 49구간, ADR·설계·보호 지침·코드·설정·프롬프트·평가 자료 보존 |
| 실행하지 않은 범위 | 실제 모델·전체 DB/Redis·서비스 E2E·배포. 정적 문서 검사나 대역 검사로 완료를 주장하지 않음 |

외부 URL 응답·동적 경로는 정적 링크 검사 범위 밖이다. 고정 SHA의 원문 링크는 저장소 객체와 줄 위치로 대조한다. 상세 로컬 검사기·로그는 Git 제외 .claude/scratch/issue109-ai-supplement-20261103/에 보존한다.

### 남은 범위

관련 task의 세부 링크는 당시 기록의 부분 범위를 안내하며 현재 전체 기능 완료를 선언하지 않는다. #109의 공유 편집 구조와 BE·FE·shared 문서 정리는 후속으로 남는다. 실제 구현·모델 평가·자료 검수 완료 여부와 문서 보완 완료를 구분한다.

<a id="pr186-review-followup-20261105"></a>

## 2026-11-05 — #186 리뷰 후속: 초기 상한 검사와 실제 측정의 구분

[#186의 인라인 의견](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/186#discussion_r4464374197)을 검토해, 초기 안전장치 검사와 실측 완료를 같은 조건으로 읽지 않도록 안내 문구를 보완했다.
기준은 `45ecc4a`이며 [0018의 운영 기준](decisions/0018-existing-baseline-bulk-resolution.md#운영-범위와-남은-구현검증)에 따른다. 새로운 운영 정책이나 수치를 채택한 변경이 아니다.

| 수정 위치 | 정리한 의미 |
| --- | --- |
| [pipeline의 운영 상한](../../ai/docs/pipeline.md#ai-runtime-limits) | 유한한 초기 설정·비용 범위와 사용자 한도를 먼저 적용하고, 실제 I/O 전에 허용 범위·권한·상한 유효성·소진 시 차단을 확인한다. 그 제한 안에서 대표 사례를 실제 호출해 측정한 뒤 production 실행·조회 상한을 조정·검증한다. |
| [analysis-scope의 읽기 범위](../../ai/docs/analysis-scope.md#2-분석-수준별-읽기-범위) | 허용된 파일 열거·인접 후보 조회의 제한 실측과 production 상한 검증을 구분한다. 임의 재귀·전체 tree·global search 금지와 검색 범위 확대 금지는 유지한다. |
| [task-08의 작업](../../ai/docs/task-08-evidence-tools.md#작업)·[구현·검증 조건](../../ai/docs/task-08-evidence-tools.md#구현검증-조건과-검토-범위) | 체크리스트와 AI-L08 안내를 같은 순서로 맞췄다. 리뷰에서 말한 63행은 기준본의 상단 3줄 추가로 66행이며, 같은 문서의 99행도 함께 명료화했다. |

BE의 [설정](../../backend/app/core/config.py)과 [GitHub 조회 연결](../../backend/app/features/interview/repository_sources.py)·[요청 및 바이트 예산 차단](../../backend/app/integrations/github/evidence.py)은 코드로 대조했다. 유한한 기본 상한이 실제 HTTP 조회 경로에 연결돼 있다는 확인이며, 기본값의 운영 적정성을 실측했거나 전체 LLM·Tool·job 검증을 끝냈다는 뜻은 아니다.
실행 코드·설정·프롬프트·평가 자료·ADR·보호 지침은 변경하지 않았다.

위 [2026-11-03 보완 기록](#issue109-ai-supplement-20261103)의 원문·대응표·당시 검증 결과는 보존했다. 해당 표의 문구는 당시 스냅샷이며, 초기 설정과 실측 순서에 관한 이번 보완은 이 절과 연결한 현행 안내를 따른다.

### 이번 검증과 미실행 범위

- 문서 내부 참조·기존 앵커 보존·명시 id 중복·변경 범위와 `git diff --check`를 확인했다.
- 기존 구현 기록 전체와 날짜별 기록, pipeline의 AI-L01~19 인계표 및 코드·설정·ADR 등 보존 대상의 해시를 대조했다. 문구의 의미는 별도 독립 검토로 확인했다.
- AI 전체 pytest·Ruff·format·mypy, BE AI import 및 부분 계약 검사는 이번에 재실행하지 않았다. 변경은 안내 문서 3개와 이 후속 기록뿐이며 과거 428 passed 등을 이번 결과로 사용하지 않는다.
- 실제 GitHub·LLM 호출, 운영 상한 실측, DB/Redis·서비스 E2E·배포는 이번 범위에서 실행하지 않았다.

#109의 `implementation.md` 공유 편집 구조와 BE·FE·shared 문서 정리는 여전히 후속 범위다. 이번 표현 보완을 실제 서비스 검증이나 #109 전체 완료로 확대하지 않는다.

<a id="live-ai-validation-20261107"></a>

## 2026-11-07 — 실제 공급자·원문을 사용한 AI 기능 검증과 발견 사항

사용자 요청에 따라 STT·TTS를 제외하고 실제 GitHub·Elice MLAPI·Vision·Tavily를 사용했다.
브라우저 로그인·마이크를 사용자에게 요구하는 검사가 아니라 내부 서비스와 실제 모델의 자동 기능 검사다.
원본 `.env`와 업무 DB는 수정하지 않았다. `feature/ai-final-service-20261107`의 로컬 통합 작업이며 미게시다.
동일 작업의 선행 코드·새 구현·전체 서비스 완료 여부는 이 기록의 이전 범위와 구분한다.

### 실행 환경과 판정 경계

- DB는 로컬 PostgreSQL의 새 `task10_test_ai_actual_20261107_test`로 분리하고 0007까지 마이그레이션했다.
  사용자는 합성 사용자이며, 공고·지원자 답변·별도 리포트 문답도 합성 입력임을 기록했다.
- 레포는 실제 Public `kakaotechcampus-4/ktc4-chonnam-3`의 `13bd98e4af74c977c2db6e367c232fe6209b979b`다.
  전체 언어·레포 규모·파일 배치에 대한 품질 검증으로 확대하지 않는다.
- 실제 LLM 호출의 검증 override는 timeout 60초, 출력 8192, 입력 262144바이트, 응답 1048576바이트,
  `stream=True`, `reasoning_effort=low`다. 원본 환경의 기본값이나 확정된 작업별 품질 정책이 아니다.
- 키·공급자 전체 주소를 결과에 출력하지 않았다. 상세 입력·출력·실패 이력은 Git 제외
  `.claude/scratch/live-ai-check-20261107/`에 보존한다. MLAPI 원시 probe는 원본 저장소의 같은 scratch 경로다.

### 실제 결과

| 기능 | 확인한 결과와 제한 |
| --- | --- |
| L1 기본 분석 | 실제 GitHub 메타데이터·고정 SHA·구조 97항목·보조 파일 4개와 실제 모델로 분석. 구조 깊이·요청 상한 이후의 미확인 범위를 보존했다. |
| L2 정밀 분석 | 실제 AI가 고른 8파일을 같은 SHA의 로컬 Git에서 읽고 실제 모델로 관찰 5개 생성. GitHub tree blob·로컬 Git object·원문 blob 해시를 모두 대조했다. GitHub 익명 quota로 수정 후 전체 수집 재실행은 못 했으며, 이 우회를 원격 수집 성공으로 표시하지 않았다. |
| GitHub 수정 후 원문 조회 | 제품 `EvidenceReader.file_text`로 고정 SHA의 `ai/pyproject.toml` 663바이트·30줄을 실제 HTTP 200으로 확인했다. 전체 수집기의 재검증과는 구분한다. |
| Vision | 합성 PNG 1건, 제출 1회·조회 3회 모두 HTTP 200. 9.672초에 OCR 751자·원문 블록 5개·도식 설명 1개. 미전사 영역을 `partial`로 유지하고 전사·생성 설명을 분리했다. |
| 문서 Claim | 실제 Vision snapshot을 재사용해 제품 Claim 추출·저장을 실제 LLM으로 실행했다. 주장 1개와 원문 위치를 저장했으며 주장의 진위를 확정하지 않는다. |
| 공고 도메인 | 합성 공고의 실제 분류 응답은 `etc`, 호출 실패 없음. 이 단독 검사에서 분류 결과를 새 공고에 저장해 frame을 고르는 전체 자동 연결까지 검증하지는 않았다. |
| 외부 자료 | 명시적 Tool 점검으로 Tavily 검색·원문 수집 및 자료 3개 DB 저장 성공. AI가 스스로 검색을 요청한 분기의 통과로 계산하지 않는다. |
| 연속 Director·T3 | 첫 HR와 다음 기술 질문, 답변 분석 2개를 저장했다. 1턴은 sufficient, 2턴은 partial이며 코드와 충돌한 주장은 conflicting·근거 충돌 2행으로 남았다. 다음 질문 후보는 rewrite 1회·replan 2회 거절. 마지막 1회는 별도 진단 작업에서도 재현됐다. 원 면접은 2턴에서 in_progress이며 9턴 완주 실패다. |
| 별도 리포트·프로필 | Director와 분리한 합성 9문답을 DB에 넣고 실제 서비스로 리포트 점수 6개·Persona 피드백 3개·프로필 1개를 저장했다. 모델 호출은 리포트 2회+프로필 1회. 재호출은 각각 exists·role_kept이며 추가 모델 호출 0회다. |

별도 리포트 입력에는 T3 분석·코드 Evidence·Tool 결과·보완 자료가 없다. 따라서 위 성공은
문답→리포트·프로필→DB·동일 입력 재사용 범위다. 실제 면접의 T3·코드·Claim·외부 근거가 최종 리포트에
전파되는 연결, 새 답변·새 면접·새 prompt의 캐시 무효화까지 검증했다고 주장하지 않는다.
저장된 서술과 프로필은 합성 사례·실제 기여 미확인·성과 수치 미측정을 유지했다.

### 원본 설정과 #196 비교

원본 `.env`의 유효 LLM 연결은 `CHAT_PROXY_URL`·`PROXY_TOKEN`, 실제 모델은 `gpt-6-luna`다.
기본 호출 설정은 출력 1024, timeout 30초, 입력 32768바이트, 응답 131072바이트,
비스트리밍, 추론 강도 미지정이다. 같은 합성 9문답의 리포트를 이 설정으로 호출한 비교는 실패했다.
4번의 provider 시도 모두 출력 1024를 사용했고 `llm_failed`로 완료형 결과를 얻지 못했다.
위 스트리밍 override로 저장에 성공한 검사와 구분하며, 원본 `.env`를 변경하지 않았다.

현재 endpoint에 짧은 `OK` 응답을 요청한 원시 HTTP 비교도 별도로 수행했다.

| 요청 | 실제 응답 |
| --- | --- |
| 비스트리밍·출력 2000·low | HTTP 200·completed |
| 비스트리밍·출력 8192·low | HTTP 400, 비스트리밍 2000 이하 또는 streaming 사용 안내 |
| 비스트리밍·출력 8192·추론 미지정 | 같은 HTTP 400 |
| 스트리밍·출력 8192·low | HTTP 200·response.completed |

이는 [#196](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/196)의 **해당 서버 비스트리밍 제한**을 재확인한다.
MLAPI 전체나 모델의 보편적 출력 한도가 2000이라는 뜻은 아니다. `OK` probe가 실제 8192토큰 생성이나
그 이상의 최대 한도·판정 품질을 검증한 것도 아니다. 작업별 추론·출력 설정과 품질 비교는 후속 범위다.

### 실제 실패에서 수정한 코드

- GitHub 일반·직접 요청의 공통 `User-Agent`: `integrations/github/base.py`, `client.py`, `evidence.py`.
- 구조 목록의 디렉터리 끝 `/`와 파일 경로 규칙을 구분: `ai/src/devon_ai/contracts.py`.
- 구조 조회가 파일 수집 요청·바이트를 모두 소진하지 않도록 예약: `features/interview/repository_sources.py`, reader 예산 경계.
- 기존 Vision 설정명과 `/v1` 접미사 호환, 명시 endpoint의 자격증명 우선순위: `core/config.py`, 문서 router, Vision 어댑터.
- 실제 `bounding_box`의 좌표 보존: Vision 어댑터. 최초 결과는 보존하고 같은 실제 응답만 재정규화해
  원문·텍스트 해시·파일 해시 불변과 원문 5개·도식 1개의 좌표를 확인했다. 추가 Vision 추론 호출은 없다.

결정·이유·영향은 [0032](decisions/0032-provider-compatibility-and-source-budgets.md)에 분리했다.
STT 설정은 기존 `Whisper_Large_v3_PROXY_URL`이 있으나 현행 `STT_BASE_URL`·`STT_API_KEY`와 자동 연결되지 않는다.
이번 요청에서 STT·TTS는 제외했으므로 연결 변경이나 실제 음성 요청은 하지 않았다.

### 회귀 검사와 남은 범위

- 이번 최종 AI 전체 검사: **687 passed**, `ai/report/live-verification-ai.xml`.
- GitHub·원문 관련 BE 122개, 관련 AI 65개, PostgreSQL 준비·캐시 52개 통과·1개 환경 skip.
  마지막 핵심 PG 4개 재검사는 52개와 중복이다. skip은 TEST_REDIS_URL 미설정의 REST retry 검사다.
- Vision 설정·정규화·preview·snapshot 관련 42개 통과. 변경 파일 Ruff·format·mypy 통과.
  위 수치는 중복 범위가 있으므로 합산하지 않는다. 대역 회귀는 실제 외부 호출과 별도로 기록한다.
- 실제 남은 작업은 후보 거절 사유를 반영하는 생성·복구의 제한된 실행 정책과 품질 보완,
  운영 작업별 호출 설정, 인증된 GitHub에서 전체 수집기 재검증, 실제 전체 면접의 최종 리포트 근거 전파다.
  이번 검증 도구의 별도 질문 작업을 제품의 자동 복구로 간주하지 않는다.
- 핵심 산출물: `repository/report.json`, `repository/validation.json`, `vision/live-summary.json`,
  `vision/source-snapshot.v2.json`, `interview/result.json`과 보존된 attempt-01·02,
  `interview/report-profile-components/result.json`, `interview/env-report-comparison/result.json`,
  `database-audit.json`. 실제 출력·저장·미실행을 구분하며 서비스 전체 완료를 선언하지 않는다.

<a id="stt-live-validation-20261107"></a>

## 2026-11-07 — STT 설정 호환과 실제 한국어 전사 확인

사용자의 후속 요청으로 STT를 실제 호출했다. 기존 기록의 STT 미확인은 그 시점의 결과이며,
이번 기록에서 확인한 범위로 갱신한다. TTS 서비스 연결과 전체 음성 면접 완주는 별도 범위다.

### 연결 보완

- `backend/app/core/config.py`가 기존 `Whisper_Large_v3_PROXY_URL`을 읽게 했다.
  전용 STT 주소·키를 우선하며, 기존 프록시 경로에서만 공통 `PROXY_TOKEN`을 재사용한다.
- 전사 클라이언트가 붙이는 경로와 중복하지 않도록 끝의 `/v1`을 정규화한다.
  모델·언어·공급자·HTTPS·키 검증과 명시 endpoint의 자격증명 경계는 유지한다.
- 현재 작업본에서 원본 `backend/.env`를 그대로 읽은 `require_stt()`가 성공했고,
  실제 전사도 같은 설정으로 실행했다. 요청 설정 override와 원본 환경 파일 변경은 없다.
- [0033](decisions/0033-stt-proxy-configuration-compatibility.md)에 이유와 영향을 기록했다.
  STT 공급자 프로토콜과 기존 `MlapiSttClient` 사이의 불일치는 없어 전사 클라이언트는 수정하지 않았다.

### 실제 API 확인

구성된 공급자의 `/openapi.json`에서 전사 경로와 multipart 입력을 확인했다.
`/docs.json`은 404였으며 이 문서 경로의 부재를 STT 장애로 해석하지 않았다.
알려진 한국어 문장을 로컬 Windows 음성 합성으로 준비하고 ffmpeg로 WebM/Opus를 만들었다.
사용자 마이크 녹음·개인정보 입력·외부 TTS 호출·DB 쓰기는 없다.

| 입력 | 실제 결과 |
| --- | --- |
| 한국어 WAV, 16kHz·mono·PCM16, 16.91초 | HTTP 200, 클라이언트 완료까지 2.297초. 공백·문장부호 제외 원문 일치 |
| 같은 음성의 WebM/Opus, FE와 같은 `audio/webm;codecs=opus` | HTTP 200, 1.016초. 공백·문장부호 제외 원문 일치 |
| 무음 WAV 3초 | 공급자 HTTP 200과 `감사합니다.`·usage.seconds=3. 기존 클라이언트가 `empty_transcript`로 거절 |

기존 제품 `MlapiSttClient`를 사용한 실제 POST는 3회이며, 합계 3.843초다.
두 형식은 같은 합성 음성 한 건의 변환본이다. 원문 일치를 일반 사용자 인식 정확도 100%로 표현하지 않는다.
실제 마이크·배경 소음·억양·장시간 답변의 품질이나 브라우저부터 실제 DB·Director까지의 완주를 검증한 것은 아니다.
무음 검사도 이번 3초 샘플과 알려진 환각 문구에 대한 확인이다.

### 회귀·보존과 남은 작업

- 신규 설정 검사 21개 통과. 수정 전 7개가 실패하는 것을 확인했다.
- STT·Vision·LLM·설정 관련 회귀 271개 통과. 변경 파일 Ruff·format·mypy 통과.
- 별도 음성 WS·오디오 버퍼·공통 음성 계약 검사 56개 통과.
  이 56개는 외부 전사·일부 처리 경계를 대역으로 둔 회귀이며 실제 API 3회와 구분한다.
- 원본 `.env`와 이전 실제 검증 결과를 보존했다. 오디오·공급자 응답·비민감 확인 정보는
  Git 제외 `.claude/scratch/stt-live-check-20261107/`에 보존했다.
  실제 결과는 `run-20261107T040703583086Z/result.json`, 입력은 `fixtures/manifest.json`,
  회귀는 `backend/report/stt-config-compatibility.xml`과 `stt-live-service-regression.xml`이다.
- 토큰 문제의 해결 방향은 앞서 실제 확인한 스트리밍·충분한 출력 예산·응답 바이트·시간 설정의 조합이다.
  이번에는 원본 LLM 설정을 변경하지 않았으며 아직 비스트리밍·출력 1024다.
- 외부 연결 기준으로 LLM·Vision·Tavily·STT의 실제 호출을 확인했다. TTS는 미검증이다.
  Director의 후보 거절 후 진행 보완, 실제 연속 9턴과 최종 리포트 근거 전파는 계속 별도 남은 범위다.

<a id="llm-xhigh-limit-20261107"></a>

## 2026-11-07 — 사용자 지정 xhigh·최대 출력 설정과 실제 재검증

사용자가 원본 `.env`의 추론 강도를 `xhigh`, 출력 예산을 최대 상한으로 변경하도록 명시 요청했다.
공식 `gpt-6-luna` 사양의 출력 한도 128,000토큰을 확인하고 같은 Elice endpoint의 작은 요청으로
`stream=true`·`xhigh`·`max_output_tokens=128000` 수락 및 정상 완료를 확인했다.
큰 정수도 수락되므로 프록시의 요청 파라미터 validation을 모델의 실제 출력 한도라고 해석하지 않았다.
확인 근거는 [공식 모델 사양](https://developers.openai.com/api/docs/models/gpt-6-luna)과
Git 제외 `.claude/scratch/llm-max-settings-20261107/run-20261107T041656505540Z/result.json`이다.
최대 분량 생성을 요구한 검사는 없으며 작은 경계 probe의 실제 출력은 요청당 15토큰이다.

### 실제 적용

원본 `ktc4-chonnam-3/backend/.env`에서 아래 6개 필드만 수정했다.

| 필드 | 변경 전 | 변경 후 |
| --- | --- | --- |
| LLM_REASONING_EFFORT | 미지정 | xhigh |
| LLM_STREAM | false | true |
| LLM_MAX_OUTPUT_TOKENS | 1024 | 128000 |
| LLM_TIMEOUT_SECONDS | 30 | 50 |
| LLM_MAX_INPUT_BYTES | 32768 | 262144 |
| LLM_MAX_RESPONSE_BYTES | 131072 | 67108864 |

자격증명·다른 공급자 설정·주석을 포함한 비대상 행을 바이트 단위로 보존했다.
저장 직전 동시 수정 여부를 검사하고 임시 파일로 교체했으며, 저장 후 Settings로 다시 읽어 적용값을 대조했다.
환경 파일 자체는 버전 관리에 추가하지 않았다. 실행 중인 API·worker에는 설정 재읽기가 필요하다.
설정의 이유와 유한한 실행 가드는 [0034](decisions/0034-local-llm-xhigh-output-limit.md)에 기록했다.

### 최신 원본 설정 그대로의 실제 리포트 재검증

이전에 원본 설정에서 잘렸던 같은 합성 9문답으로 점수 판정과 서술 생성을 실행했다.
설정 override 없이 최신 원본 `.env`를 사용했고, 테스트 DB는 `transaction_read_only=on`으로 확인했다.

| task | 실제 결과 |
| --- | --- |
| report_score | HTTP 200·response.completed·제품 validator 통과. 입력 5837, 출력 4049 중 추론 3809토큰. 43.625초, SSE 246000바이트 |
| report | HTTP 200·response.completed·제품 validator 통과. 입력 4821, 출력 5371 중 추론 3624토큰. 40.969초, SSE 702405바이트 |

병렬 실제 HTTP 호출은 2회, 전체 44.015초이며 점수 6개·Persona 피드백 3개를 검증했다.
기존 실패 결과를 보존했고, 이번에는 제품 코드·DB 쓰기·STT·TTS 호출을 하지 않았다.
설정 변경 후 실제 호출 중 환경 파일 해시도 동일했다.
상세 결과는 `.claude/scratch/llm-max-settings-20261107/report-20261107T041920204799Z/`에 보존했다.
변경 전후의 비민감 설정과 보존 확인은 같은 상위 디렉터리의 `environment-change.json`에 있다.

### 완료 판단의 범위

외부 공급자 LLM·Vision·Tavily·STT의 실제 호출과 대표 기능 실행은 확인했다.
그러나 이를 **TTS를 제외한 서비스 전체 검증 완료**로 확대하지 않는다.

- 기존 실제 Director 흐름은 2턴 답변 분석 뒤 다음 질문 후보 검수에서 중단됐다. 정상 연속 9턴 완주가 아니다.
- 이번 성공 리포트는 별도 합성 9문답이며 T3 분석·코드·Claim·검색 근거가 비어 있는 입력이다.
  실제 면접의 전체 근거가 최종 리포트로 전달되는 통합 검증을 대신하지 않는다.
- 이전 프로필·레포·문서·T3의 성공 측정을 새 전역 `xhigh` 설정의 재검증으로 옮기지 않는다.
  이번 새 설정에서는 출력 경계 probe와 합성 리포트 두 task만 실제 실행했다.
- 128,000은 공식 모델 출력 예산이다. 50초·64MiB 등 실행 가드는 계속 적용되며,
  모든 입력에서 그 분량 전체를 생성하거나 완료할 수 있음을 증명한 검사가 아니다.

<a id="issue196-followup-20261107"></a>

## 2026-11-07 — #196 실측 공유와 실행 제한의 근거 정리

사용자 요청에 따라 [#196 댓글](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/196#issuecomment-6702412478)에
비스트리밍 제약 재현, 스트리밍·명시적 추론 강도 지원, 실제 리포트 결과와 미실행 범위를 게시했다.
본문은 UTF-8 파일로 준비하고 독립 대조 후 게시했으며 원격 댓글 원문과 파일의 정확한 일치를 확인했다.
연결된 GitHub 앱은 이슈 쓰기가 403으로 거절돼, 기존 로컬 Git Credential Manager의 같은 사용자
`gdh0730` 인증을 확인한 뒤 GitHub API로 한 번 게시했다. 토큰은 메모리에서만 사용했다.
이슈 상태는 변경하지 않았으며 로컬 미게시 구현을 공유 브랜치·운영 반영 완료로 설명하지 않았다.

### 50초와 64MiB의 의미

- 50초는 모델 HTTP 시도 1회의 전체 수신 제한이다. 재시도·대기·큐·면접 전체 제한과 다르다.
  실제 최신 호출 43.625초·40.969초는 이 안에서 성공했지만, 두 측정으로 p95/p99나 최적값을 판단하지 않는다.
- 기존 준비 worker 600초, 리포트 잠금 300초 등 실행 경계도 함께 고려했다.
  문서 Claim·primary 수집·L2·Director를 포함한 590초 계산은 호출 예산 추정이다.
  DB·큐·JSON 처리·취소 정리까지 엄밀히 제한한 전체 완료 보장식으로 해석하지 않는다.
- 응답 바이트에는 최종 JSON뿐 아니라 SSE 이벤트·delta·완료 응답이 포함된다.
  실측 246000·702405바이트는 이전 128KiB 상한도 초과하므로 상향 근거가 있다.
- 64MiB 자체는 통계적으로 도출된 최적값이 아니라, 출력 예산 확대에 맞춰 둔 넉넉하고 유한한 보호선이다.
  실측 최대의 약 95.5배이며 그 크기를 미리 할당하지는 않는다. 수신·문자열 변환·파싱 중 복사로
  피크 메모리는 실제 수신량보다 커질 수 있어 동시 호출을 포함해 별도 측정해야 한다.
- 후속 조정은 task·모델·추론 강도·입력 규모별 지연과 응답 크기 분포, timeout·재시도율,
  동시 실행 메모리를 측정하고 사용자 대기·worker·잠금 예산에 맞춰 수행한다.

### 환경 예제와 모델 우선순위

작업본 `backend/.env.example`의 LLM 관련 값만 현재 원본 `.env`에 맞췄다.
`OPENAI_MODEL=gpt-6-luna`, 추론 `xhigh`, 스트리밍, 출력 128000, 시간 50초,
입력 262144바이트, 응답 67108864바이트의 실제 적용값 일치를 확인했다.
실제 키·토큰·비공개 공급자 주소는 복사하지 않았다. 원본 저장소의 develop 작업 파일과 원본 `.env`는 변경하지 않았다.

비교는 `Settings`의 기본 필드가 아니라 실제 소비 경로 `require_llm()`을 기준으로 했다.
기본 `LLM_DEFAULT_MODEL=gpt-5.6-luna`보다 명시한 `OPENAI_MODEL`이 우선하므로,
현재 실제 모델은 계속 `gpt-6-luna`이며 환경 파일 전체 해시도 이전 설정 변경 직후와 동일했다.
현재 모델 목록 조회와 작은 실제 Responses 요청으로도 요청·응답 모델 `gpt-6-luna`를 확인했다.
명세의 다른 모델을 검증했다고 확대하지 않는다.

공급자 LLM·Vision·Tavily·STT의 실제 연결·대표 호출 확인과 전체 Director 연속 9턴·최종 근거 리포트 검증은 계속 구분한다.
댓글 원본·게시 결과·예제 대조·작은 모델 확인은 Git 제외 `.claude/scratch/issue196-followup-20261107/`에 보존했다.

## 2026-11-07 — 최종 AI 실행 연결의 후속 구현과 sol 검증

### 작업 원본과 범위

기존 `feature/ai-final-service-20261107`의 미게시 변경을 patch·index·untracked 묶음으로 보존했다.
최신 로컬 develop `99635268fe86b3ef3762a6a2b5dcd9ba67b6b9ce`에서
`feature/ai-final-service-complete-20261107` worktree를 만들고 이전 구현과 #201·#204의 잠금·WS 복구를 결합했다.
이 기록은 로컬 통합 구현이며 커밋·push·PR·병합·운영 배포 결과가 아니다.
초기 설계·task·testing 문서는 구현 완료 표기로 변경하지 않았다.
정책은 [0035](decisions/0035-final-runtime-budgets-and-report-revisions.md)에 남긴다.

사용자의 `sol` 지정은 서비스 모델이다. 기존 세 번째 모델·주소 설정을 `LLM_CONNECTION_SLOT=3`으로
함께 선택하도록 연결했다. 원본 로컬 `.env`에는 해당 선택값과 작업별 시간 상한만 추가했고,
키·공통 토큰·공급자 주소를 출력하거나 예제에 복사하지 않았다.
본 절 이후의 실제 모델 검증은 새 worktree의 `require_llm()`과 `gpt-6.1-sol`을 기준으로 한다.
이전 절의 luna 검증과 혼합하지 않는다.

### 이번에 연결·보완한 기능

| 범위 | 실제 변경과 코드 위치 |
| --- | --- |
| Director | `ai/src/devon_ai/agents/director/runtime.py`와 v4 프롬프트에서 현재 답변·질문 계약·평가 기회를 분리하고 명시적 과거 v1/v2 호환을 유지한다. 마지막 답변의 새 검색 요청은 `director_service.py`에 미실행 상태로 저장한다. |
| 레포 수집·분석 | `repository_sources.py`, `source_segments.py`에서 SHA·본문·범위를 확인해 구간 캐시를 재사용한다. L1 v3 프롬프트는 공고와 비교할 기술명을 설명문과 분리한다. 다른 언어는 지원한 정적 해석 또는 원문 구간과 한계를 사용한다. |
| 이미지 공고 | Wanted의 허용 본문 이미지 수집 → 기존 Vision → `jd_extract_image` → 전사 인용·위치 검증 → `source_blocks`·`JdRequirement.source_refs` 저장을 연결했다. 본문과 이미지의 충돌은 기록한다. |
| 문서 주장 대조 | `documents/claim_comparison.py`와 AI `claim_code`를 연결했다. 선택 문서의 Claim과 실제 코드 Evidence만 비교하며 역할·성과·미열람 코드는 미확인으로 남긴다. 실행별 결과와 과거 참조를 보존한다. |
| 답변 분석 | 실제 실행에서 발견한 근거 ID·충분성의 모순을 v6의 생성 전용 구조와 원문 구간 ID로 제한한다. 저장용 `AnswerAnalysis`는 그대로이며, 기존 의미 검증·실패 비재시도와 감사 raw 보존을 유지한다. |
| 면접 중단·재도전 | 기존 계약의 `POST /interviews/{id}/abandon`을 구현했다. DB 상태·중단 턴·WS 소유권을 확정하고 늦은 T3·Director 결과를 폐기한다. 시작 전 중단은 재도전 대상에서 제외한다. |
| 리포트 | 영구 생성 요청·명시적 실패 재시도·이의 제기 revision·운영자 검토·별도 재평가·이전 결과 보존을 구현했다. `report/generation.py`, `reviews.py`, `revisions.py`, `service.py`, `scripts/review_report.py`를 사용한다. |
| 프로필 | 답변·프롬프트 등 실제 요약 입력의 지문과 실행 당시 상한을 보존한다. 입력이 바뀐 동안 생성한 결과가 새 결과를 덮어쓰지 못하게 한다. |
| FE | 문서 종류·선택 입력을 유지하고 리포트 이의 제기·실패 생성 재시도·revision 변경 안내를 실제 API 계약에 맞춰 연결했다. |
| 평가 | 서비스 실행과 Judge의 별도 예산·감사 기록을 연결했다. 승인된 기존 control 교정은 서비스 입력이 없어도 가능하지만 서비스 실행 결과와 구분한다. 미검수 사례·미확정 release gate를 그대로 유지한다. |

추가 영구 모델은 `0008_document_claim_comparison` → `0009_jd_image_sources` →
`0010_report_review_runtime` → `0011_profile_generation_limits`로 이어진다.
공유 계약에는 리포트 revision·명시 재생성 요청 등이 추가되어 FE·BE 팀 검토가 필요하다.
실행용 DB 모델과 공유 명세의 변경을 게시 시 같은 범위로 취급하지 않는다.

### 실행 예산과 실패 보존

실제 sol 정밀 분석은 기존 50초 상한에서 실패했다. `repo_deep`, `answer_analysis`, `director`를
각 120초로 두었다. 실제 9턴 리포트의 점수·서술이 공통 50초에서 각각 두 번 타임아웃되어,
`report_score`·`report`는 별도 180초로 조정했다. 그 외 작업과 `profile_summary`는 공통 50초다.
스트리밍·xhigh·출력 128000·입력 262144바이트·
응답 67108864바이트는 유지한다. 이 수치는 제한된 실제 실행을 위한 시작값이며 성능 SLO가 아니다.
준비 worker 1800초와 내부 deadline 1770초, 준비의 최대 계획 검사, WS 작업 잠금 수명도 함께 조정했다.
STT는 전체 업로드·수신 timeout과 최대 응답 1048576바이트를 적용한다.

실제 검증 중 실패한 면접·모델 시도는 삭제하거나 질문·답변을 다시 쓰지 않았다.
제품 중단·재도전 경로로 새 면접을 만들었다. T3 v3의 등록된 인코딩 오류 본문도 덮어쓰지 않고,
정상 UTF-8 본문을 v4로 분리했다. v3 원문은 DB와 Git 제외 `verification/retired-prompts/`에
해시가 같은 상태로 보존하고 제품 프롬프트 목록에서는 제외했다. v2·v4는 보존했다.
v4의 실제 실행은 첫 5개 답변까지 정상 처리됐으나 여섯 번째에서 일반 설계 설명을
`supported`·빈 코드 근거로 분류해 차단됐다. 실패를 통과시키지 않고 새 v5에서 해당 상태를
생성 스키마부터 거절하도록 보완했다. 실제 실패 출력은 v4 생성 스키마가 허용하고 v5가
거절함을 JSON Schema로 재현했다.

v5의 실제 실행에서는 두 번째 답변에서 `partial`과 빈 `missing_points`의 모순을 확인했다.
새 v6는 충분성·필수 항목·누락 항목·판단 상태를 함께 생성하고, 답변 인용은 원문 ID로 선택한다.
서버는 선택한 원문과 명시된 판단을 기존 저장 형식으로 복원한다. 판정값이나 답변을 교정하지 않는다.
미확인 기여의 사유는 모델이 쓴 문장 그대로 한계에 옮기고, 조회 필요 flag는 실제 요청 배열에서 정한다.
이전 버전·실패 원본은 보존했다. 현재 recipe는 v6를 선택한다.

감사 raw도 v6 원본 그대로 남는다. 다음 Director와 리포트는 당시 버전·질문·답변에 맞춰 복원한다.
같은 claim quote ID의 중복 판정은 v6에서 거절하고, 기존 v1~v5 prior 분석의 관용 복원과
기존 report의 strict 복원은 유지했다. 실패했던 동일 질문·답변의 별도 실제 진단은 v6에서
1회 호출로 canonical 검증을 통과했으며, 이전 실패·답변·분석 DB를 수정하지 않았다.

추가 독립 검토에서는 이미지 JD의 읽기 한계가 리포트에서 빠지는 문제를 확인했다.
`report/jd_sources.py`는 실제 질문에서 참조한 요구사항만 저장 전사와 해시로 복원한다.
본문은 블록별 4KiB·전체 16KiB로 제한하고 일부 구간이면 원래 전체 좌표를 그대로 붙이지 않는다.
원문 누락·해시 불일치와 OCR·원문 충돌은 서술·점수 판정 모두에 별도의 `JDSourceNote`와 한계로 전달한다.

### 실제 공급자 확인

Git 제외 원본은 새 worktree의 `.claude/scratch/final-service-execution/`에 보존했다.
키·비공개 주소를 기록하지 않고, 기존 GitHub 자격은 메모리에서만 사용했다.

- sol 모델 조회와 작은 Responses 스트리밍 요청이 HTTP 200으로 완료됐다.
  실제 요청·응답 모델은 `gpt-6.1-sol`이며 출력 128000개를 실제 생성한 검증은 아니다.
- 인증된 실제 GitHub에서 고정 SHA `9963526…`의 원문을 수집했다.
  레포 L1, 실제 구조를 바탕으로 한 파일 선정, 원문 8개를 사용한 L2가 성공했고 분석 영역 5개를 생성했다.
  로컬 Git 원문으로 대체하거나 모의 GitHub 응답으로 성공시킨 검증이 아니다.
- 같은 실제 수집 입력으로 L1 v3를 별도 호출했다. 합성 공고 태그 `Python`·`TypeScript`·`Docker`가
  기존 설명문 목록에서는 0개, 기술명 목록에서는 3개 매칭됐다. 실제 사용자 추천 품질의 평가 결과는 아니다.
- 현재 설정 그대로 STT에 기존 합성 WAV·WebM을 제출했고 둘 다 공백·문장부호 정규화 기준으로 일치했다.
  무음은 `empty_transcript`로 거절됐다. 실제 마이크·잡음·여러 화자의 정확도를 검증한 것은 아니다.
- Vision은 합성 PNG를 실제 전사해 751자·원문 블록 5개와 원본 해시를 반환했다.
  `visual_regions_not_transcribed`, `unread_document_regions`가 있어 상태는 partial이다.
- Tavily는 PostgreSQL 공식 도메인 검색 1건과 본문 수집 1건에 성공했다.
  공식 출처를 찾은 사실이 내용의 영구 최신성·개별 답변의 정답을 보증하지 않는다.
- 별도 Judge 예산 2회로 승인 control의 허용·금지 출력을 실제 sol이 각각 accept·reject했다.
  나머지 control은 예산 부족 상태다. 서비스 입력이 없는 11사례의 서비스 실행은 모두 not_executed이며,
  이 2건으로 Judge 타당성이나 서비스 release gate를 통과시켰다고 판단하지 않는다.

**실제 TTS 호출은 사용자의 요청에 따라 보류했다.** Persona별 목소리 설정과 예산·캐시·실패 처리의
모의 검증은 실제 Google Cloud 인증·음질·결제 검증을 대신하지 않는다.

### 남은 검증과 승인 경계

연속 9턴·리포트·프로필의 실제 모델 실행과 최종 전체 회귀는 아래 최종 검증 기록으로 확정한다.
현재 단계의 개별 API·mock·PG 성공 수치를 그 결과로 대신 사용하지 않는다.
실제 Wanted 이미지 공고 전체 흐름, 다양한 외부 레포의 모든 언어·규모 조합,
사람의 rubric·평가셋 검수와 Judge 교정·운영 임계값 승인, 운영 배포는 별도 경계다.

### 코드·저장·화면 회귀 검증

검증 원본과 지문은 Git 제외 `verification/`에 보존했다. 과거 실행·겹치는 후속 실행을 더해
하나의 최신 전체 테스트 통과 수로 쓰지 않는다.

| 검증 | 실제 결과와 범위 |
| --- | --- |
| AI 최신 v6 | 전체 `pytest` 750개 통과. Ruff·format 111파일·mypy 26소스 통과. |
| BE 전체와 후속 검증 | v5 고정본 전체는 2269 통과·3 실패·1 스킵이었다. 발견한 Git 부재·설정 예시 기대값을 수정하고 최신 영향 195개, 최종 prior 호환 42개, runtime recipe 3개, 별도 migration 1개가 통과했다. 최신 수집 2282개와 XML을 사례 ID로 대조해 미검증·미해결 실패·남은 스킵 0을 확인했다. 최신 단일 실행 2282 통과 결과는 아니다. `backend-linux-final-matrix.json` 참조. |
| 리포트 시간 설정 후속 | 실제 타임아웃에 따라 `report_score`·`report`를 180초로 조정한 뒤 설정·연결 선택·manifest·실행 recipe 관련 103개가 통과했다. 이전 전역 결과에 합산하지 않는다. |
| BE 정적 검사 | 최신 Ruff·format 507파일·mypy app 206소스 통과. 검사 전후 소스 지문이 같다. |
| FE | tsc·build·eslint·프록시 회귀 4개 통과. 전체 Playwright는 143/144였고 자동 종료의 임시 UI 기대 1건을 수정했다. 179999ms의 미제출 상태, 다음 1ms의 자동 종료·영구 답변 저장·질문2·마이크 해제를 확인한 뒤 영향 음성 파일 31개가 모두 통과했다. 수정 후 전체 144개를 다시 실행한 결과는 아니다. |
| 계약 | 기존 검사 환경으로 스키마 2개·부분 OpenAPI·양/음성 fixture 7개 통과. 전체 서비스 API 호환성 승인은 아니다. |
| 마이그레이션 | 새 DB에서 head0011 → 빈 스키마0006 → head0011 왕복과 두 번의 Alembic 모델 대조 통과. 실제 profile 감사가 있으면 downgrade를 거절하고 감사 행이 남는 것을 확인했다. 별도 독립 PG에서는 Task11의 분석 작업·페이지·partial unique 보존 검증도 통과했다. |
| Docker | 기존 runtime 이미지에 최신 소스를 읽기 전용으로 연결하고 network none에서 모듈·worker 6종·cron 3종·runtime prompt 11종을 확인했다. 새 이미지 빌드나 운영 배포 검증은 아니다. |
| 독립 검토 | 수정한 중복 claim 판정·legacy prior 호환을 포함한 원문/버전/감사 재생 경계 probe 28개 통과. 사람의 서비스 품질 승인과 구분한다. |

BE 평가 도구는 Git이 없거나 실행할 수 없을 때 `source_revision=null`, 상태·한계를 남기고
파일별·전체 작업 소스 지문은 계속 기록한다. 원래 OS 예외나 비공개 접속 정보를 출력하지 않는다.
운영 예시 `.env.example`의 sol·xhigh·상한을 설정 클래스의 미설정 fallback과 혼동하지 않도록
허용한 차이와 비공개 입력의 빈값도 검증했다.

### 실제 9턴·작업 큐·리포트·프로필 확인 결과

격리 DB·Redis와 실제 `gpt-6.1-sol`에서 새 면접을 처음부터 끝까지 실행했다.
지원자 답변은 검증용 합성 입력이며 사용자 개인의 실제 경험·기여·성과 자료가 아니다.
LLM 응답을 모의로 바꾸거나 실패한 과거 턴을 수정해 이어가지 않았다.

- 제품 면접 준비가 성공한 뒤 질문 생성·독립 검토·답변 분석을 연속 처리했다.
  **9개 답변·9개 분석, 기술 6·도메인 2·HR 1**을 저장하고 `completed`로 종료했다.
- 완료 면접의 lazy 리포트 요청을 실제 Redis/ARQ 큐에 넣었다.
  최초 작업의 점수·서술은 기본 50초 상한에서 실패했고, 요청 행·시도·실패는 그대로 보존했다.
- 작업별 상한을 180초로 조정하고 제품의 명시적 `generation.enqueue(mode=retry)` 경로로 새 요청을 만들었다.
  실제 worker가 점수·서술과 후속 프로필을 실행해 작업 2개가 완료됐다.
  점수 6개·리포트 revision1·불변 revision 기록1개·프로필 입력 지문·실제 생성 상한이 저장됐다.
  이전 `failed`와 새 `succeeded` 요청 행이 모두 남아 있다.
- 성공한 실호출은 `report_score` 약120.9초·서술 약103.1초였다.
  프로필의 실제 모델도 sol이고 시간 상한은 공통 50초다.
  이는 이번 입력 한 건의 관찰값이며 p95·SLO·동시 실행 성능을 검증한 수치가 아니다.
- 리포트를 두 번 다시 읽어 `ReportResponse`를 받았고, 프로필은 `role_kept`와 추가 모델 호출 0회로 재사용했다.
  프로필은 가상 역할 설정과 실제 기여 미확인, 저장소 언어 비율과 개인 기여 비율을 구분했다.
- 실제 TTS는 호출하지 않았다. 이번 검증은 내부 서비스 함수·실제 공급자·PG·Redis/ARQ의 연결이며,
  사용자 로그인·브라우저 마이크·배포 환경 전체를 거친 실사용 E2E와 구분한다.

원본은 `interview/result.json`, `report-attempt-01-50s/`, `report-queue-result.json`,
`final-report-storage.json`이다. Windows 검증 도우미의 ARQ 종료 중 `SIGUSR1` 정리 오류는
`handle_signals=True`로 수정해 본래 timeout과 구분했다. 제품 코드를 바꾼 장애 수정은 아니다.

기존 작업 worktree의 tracked patch·status 해시가 초기 보존본과 같은 것도 확인했다.
이번 결과는 새 로컬 작업 브랜치에 보존하며 PR·병합·운영 배포를 수행한 결과로 기록하지 않는다.

## 2026-11-08 — Chirp 3 HD 채택과 로컬 서비스 설정

사용자가 직접 청취한 TTS를 채택하고 서비스 설정을 요청했다.
선택과 활성화 경계는 [0036](decisions/0036-chirp3-service-configuration.md)에 기록한다.
이 절은 앞선 실제 9턴 검증의 TTS 보류 기록 이후 상태이며 과거 결과를 덮어쓰지 않는다.

### 설정과 보존

- 공급자는 `google_cloud`, 언어는 `ko-KR`로 선택했다.
- 기술 면접관은 `ko-KR-Chirp3-HD-Charon`, 도메인은 `ko-KR-Chirp3-HD-Kore`,
  HR은 `ko-KR-Chirp3-HD-Aoede`로 배정했다.
- 앱의 월 상한은 100만 문자로 두었다. 이는 확인된 Cloud 잔여량이 아니다.
- 원본 로컬 `backend/.env`에 선택값을 추가하고 새 worktree의 Git 제외 `backend/.env`에도
  같은 설정을 준비했다. 기존 키와 비TTS 설정이 유지되고 두 파일이 같은 것을 확인했다.
  공개 `.env.example`에는 선택값만 반영하며 키·접속 주소·프로젝트는 복사하지 않았다.
- 실제 Cloud 프로젝트와 이번 달 무료 잔여량은 미확인이다. `TTS_BUDGET_PROJECT`는 빈 값으로
  두고 Redis 월 예산을 초기화하지 않았다. 사용자에게 필요한 정보를 요청한 상태다.
  현재 합성 요청은 `budget_unconfigured`로 차단되므로 서비스 활성화 완료로 보고하지 않는다.

### 실제 공급자 확인과 이번 회귀

앞선 단독 검증에서는 실제 Google 키로 한국어 음성 목록 조회와 세 음성의 합성이 성공했다.
한국어 입력의 MP3 세 개를 디코딩했고 STT 재전사도 공백·문장부호 정규화 기준으로 일치했다.
첫 인코딩 오류의 세 요청은 한국어 검증에서 제외해 보존했다. 전체 전송량은 174문자다.
원본은 Git 제외 `tts-verification-20261107/result.json`, `roundtrip-stt.json`과 MP3에 있다.
이는 공급자 단독 진단이며 서비스 월 예산이나 브라우저 전체 면접을 검증한 결과가 아니다.

이번 실행 산출물은 Git 제외 `.claude/scratch/tts-service-20261108/`에 보존했다.

| 검증 | 이번 결과와 범위 |
| --- | --- |
| TTS 회귀 | 신규 격리 PostgreSQL DB와 테스트 Redis DB에서 60개 통과. 어댑터·예산·캐시·질문 API·재생 복구·계약을 확인하며 Google 합성은 모의 응답이다. |
| 설정 | `test_config.py`·`test_final_provider_settings.py` 36개 통과. 선택값을 무설정 fallback과 구분해 정확히 검사한다. |
| 정적 검사 | 수정한 설정 테스트의 Ruff와 format 검사 통과. |
| FE | 기존 브라우저 회귀 중 음성 재생·공급자 실패·자동재생 차단의 3개 통과. 모의 API를 사용하며 실제 Google 연결 E2E는 아니다. |
| 실제 API 차단 | 실제 앱 인증·Redis 세션과 기존 실검증 DB의 저장 질문으로 무인증 401, 본인 질문의 예산 미설정 409/not_ready, 없는 턴 404와 원문 보존을 확인했다. Google은 호출하지 않았다. |

실제 API 차단 검증은 별도 검증 DB·Redis를 명시했다. `.env`의 평상시 DB·Redis가 실행 중이거나
새 API/worker가 기동됐음을 뜻하지 않는다. 설정을 읽은 기존 API는 재시작해야 하며,
배포 환경의 `.env.deploy`나 원격 설정은 이번에 변경하지 않았다.

### 남은 활성화와 검증

1. 실제 Cloud 프로젝트와 다른 앱 사용을 포함한 이번 달 잔여량·진행 중 합성을 확인한다.
2. API가 사용하는 Redis가 준비되면 같은 DB 번호에 확인한 잔여량으로 월 예산을 초기화한다.
   새 달이나 Redis 교체 때도 명시적으로 확인하며 자동으로 새 무료량을 부여하지 않는다.
3. 실제 질문 음성 API에서 세 페르소나 합성과 같은 질문의 캐시 재사용·추가 문자 소비 없음을 확인한다.
4. 브라우저에서 실제 인증·재생·녹음 시작 시 음성 정지·실패 시 텍스트 대체를 확인한다.

추가 조회 판단 외에도 실제 이미지 JD·문서 원문 경로, 다양한 레포·SHA 캐시,
프로세스 중단·중복 요청, Task-12 사람 검수·Judge 교정·품질 gate, 운영 배포·동시성은 남아 있다.
이번 60·36·3개 결과를 과거 전체 테스트나 전체 모델 품질 통과 수치로 합산하지 않는다.
커밋·push·PR 게시·병합·배포는 수행하지 않았다.

### 프로젝트 ID 제공 이후

사용자가 제공한 프로젝트 ID를 원본과 새 worktree의 비공개 `TTS_BUDGET_PROJECT`에 반영했다.
키와 그 외 환경 값의 보존, 두 파일의 일치, 실제 `Settings.require_tts`와 음성 입력 검증을 확인했다.
이는 사용자 제공 프로젝트의 등록이며, 키의 소속·Cloud 무료 잔여량을 별도로 조회한 결과는 아니다.
잔여량과 다른 앱·프로젝트의 사용 이력은 미확인이므로 월 예산은 초기화하지 않았다.
사용자에게 같은 결제계정의 Chirp 3 HD 사용이 기록된 샘플 6건·174자뿐인지 확인을 요청했다.
Google 합성은 추가 호출하지 않았다. 산출물은 `tts-service-20261108/project-configuration.json`이다.

### 전체 이력 확인과 실제 질문 API 활성화

사용자는 같은 결제계정의 다른 앱·프로젝트까지 포함한 이번 달 Chirp 3 HD 사용이
기록된 샘플 6건·174자뿐이라고 명시적으로 확인했다. 이 근거의 범위는
[0037](decisions/0037-tts-complete-history-budget.md)에 기록한다.

- 원본 `.env`의 API Redis 대상은 로컬 56379 포트의 DB 0이며 당시 실행 중인 서버가 없었다.
  기존 데이터를 삭제·이동하지 않고 캐시된 `redis:7` 이미지로 전용 로컬 Redis를 실행했다.
  AOF는 별도 Docker volume에 보존한다. 평상시 DB나 API·worker를 새로 기동한 것은 아니다.
- 최초 예산은 `1,000,000 - 174 = 999,826`으로 산정했다. 기존 `initialize_budget`을 사용했고
  Cloud 조회 확인 플래그는 사용하지 않았다. 근거는 `user_confirmed_complete_history`로 남겼다.
- 초기화 도우미는 이번 기간의 최초 1회만 허용하고 기존 카운터나 초기화 기록이 있으면 중단한다.
  사용자 확인 뒤 실제 API를 통한 신규 소비는 같은 Redis 카운터에 누적한다.

실제 앱·인증·저장 질문·Google 합성·위 Redis를 연결한 유한 검증이 성공했다.
DB는 기존 실제 9턴의 격리 PostgreSQL을 명시했으며 평상시 DB 설정을 바꾸지 않았다.
호출 횟수 계측만 추가하고 Google 응답을 모의로 대체하지 않았다.

| 확인 | 실제 결과 |
| --- | --- |
| 페르소나 합성 | 저장된 HR 1턴·기술 2턴·도메인 6턴의 질문 음성 GET이 모두 200. Aoede·Charon·Kore 배정을 실제 전송에서 확인했다. |
| 원문·형식 | 저장 질문을 그대로 전송하고 질문 원문은 변경되지 않았다. 세 MP3 모두 디코딩 성공, 응답은 `audio/mpeg`·`private, no-store`다. |
| 캐시·동시 요청 | 같은 질문의 반복 GET과 HR 질문의 동시 GET이 같은 음성을 반환했다. 질문마다 Google 합성 1회이며 반복 조회의 문자 소비는 0이다. |
| 인증 | 무인증 401을 확인했다. 검증 DB에 다른 활성 사용자가 없어 이번 실호출의 타인 소유권 검사는 미실행이며 앞선 자동 회귀와 구분한다. |
| 문자 예산 | 신규 사용량은 126+156+184=466자. `used=466`, `pending=0`, `uncertain=0`, 초기 상한 999,826을 확인했다. |
| 누적·잔여 | 앞선 174자를 포함한 기록상 누적 사용량 640자, 남은 앱 예산 999,360자다. 공급자 사용량 직접 조회값은 아니다. |

원본은 Git 제외 `tts-service-20261108/history-budget-initialization.json`, `live-route.json`과
`live-*-turn-*.mp3`다. 이번 검증은 실제 공급자를 사용하는 인증된 ASGI API 경로이며,
사람의 브라우저·마이크로 9턴 전체를 진행하거나 운영 환경에 배포한 결과는 아니다.
평상시 `.env`의 PostgreSQL과 API/worker의 기동, 배포 설정은 별도다.

## 2026-11-08 — 최종 AI 서비스 후속 구현과 통합 검증

앞선 원본 worktree와 실행 기록을 보존하고 `feature/ai-final-service-followups-20261108`에서 진행했다.
기준은 `develop`의 `18f4105b2e7e9885df118d283badbf59692ec5b4`이며, 필요한 기존 미병합 구현을 로컬에서 결합했다.
이 절은 새 후속 변경과 검증 기록이다. 커밋·push·PR 게시·병합·운영 배포를 수행한 기록은 아니다.
결정과 이유는 [0038](decisions/0038-final-service-followups.md)을 참조하고, 초기 설계·task·testing 문서는 유지한다.

### 범위와 협업 근거

- [#206 댓글](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/206#issuecomment-6711527539): 새 환경의 rubric 초기화와 사람 승인 분리.
- [#207](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/207): 문서 계약과 저장된 text/voice 모드의 일치.
- [#208](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/208): 보고서 성공 이후 프로필 전달·실행·복구.
- [#209](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/209): 서비스 실행과 자동 평가 연결, Judge 교정·누출 방지.
- [#210](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/210): 고정 원문 보완 조회와 전체 실행 검증.
- [#211](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/211): 배포 prompt 감사 버전의 저장 용량과 보존.

### 구현한 연결

문서 요청에는 종류·선택 자소서 ID·형식별 지원과 상한을 명시했다.
새 voice 면접의 text WS 입력은 STT·모델·저장 전에 거절하고, 기존 text 면접은 텍스트 화면으로 이어간다.
text 준비에서는 마이크를 요구하지 않으며 초안·원문 줄바꿈·재접속·질문 텍스트를 보존한다.
계약과 화면은 [OpenAPI](../shared/contracts/openapi.yaml), [FE API 계약](../../frontend/docs/api-spec.md),
[WS](../../backend/app/features/interview/ws.py), [진행 화면](../../frontend/src/features/interview/InterviewScreen.tsx)에 연결했다.

보고서와 revision별 프로필 갱신 요청을 같은 transaction에 저장한다.
큐 전달·worker 인수·완료의 회차와 소유 토큰을 검사하고 총 5회·24시간 안에서 복구한다.
정지·탈퇴 사용자는 대기 작업 인수 때 영구 종료하고, 직접 호출·기존 job도 모델 실행 전에 차단한다.
캐시 재사용도 짧은 User 행 잠금으로 활성 상태를 재검사하며 이전 성공 요약은 보존한다.
근거는 [outbox](../../backend/app/features/profile/refresh_outbox.py),
[프로필 서비스](../../backend/app/features/profile/service.py), [worker](../../backend/app/workers/tasks/profile_summary.py)다.

준비 복구 두 경로는 한 번에 최대 10페이지×100건을 조회하고 다음 cron에서 이어간다.
동일 timestamp도 UUID로 순서를 정하며, ARQ의 job별 ctx 복사 사이에서 cursor·cutoff를 공유한다.
겹친 cron·취소·새 owner·lease 갱신을 재검사하고 DB 잠금을 잡은 채 큐 응답을 기다리지 않는다.
연결은 [공통 순회](../../backend/app/workers/preparation_candidates.py)와 기존 준비 reaper 두 개를 재사용했다.
준비 전체 상한 1770초, worker 1800초, lease 90초·heartbeat 20초와 프로필 등록을 유지했다.

고정 commit의 root tree와 실제 파일 경로를 열거하고 선정 경로·주변 후보를 별도로 보존한다.
재귀 목록도 요청·응답/누적 바이트·항목·깊이 상한 안에서 처리하며, 완전한 부모 목록만 캐시한다.
경로별 fallback이 항목 상한에서 잘린 부모 목록을 전체 캐시로 쓰던 문제도 보완했다.
원문을 읽지 않은 후보는 Evidence가 아니며, 저장 전에 사용자·선택 public 레포·SHA·경로를 다시 검사한다.
근거는 [구조 수집](../../backend/app/features/interview/repository_sources.py),
[재귀 목록](../../backend/app/features/interview/repository_structure.py),
[후보](../../backend/app/features/interview/repository_candidates.py), [조회·저장](../../backend/app/features/interview/agent_queries.py)다.

### 새 개발 환경 초기화의 실제 실행

격리 개발 DB에서 다음 8단계를 실제 실행했고 모두 exit 0이었다.

| 단계 | 확인 |
| --- | --- |
| 1 | 새 검증 DB 생성 |
| 2 | Alembic head까지 적용 |
| 3 | sol 배포 버전으로 runtime prompt 등록 |
| 4 | 지식 초기화 dry-run |
| 5 | 미검수 개발 초안 사용을 명시해 적용 |
| 6 | 같은 지식 초기화 재실행 |
| 7 | 같은 runtime 등록 재실행 |
| 8 | Alembic 모델 정합성 확인 |

평가 key 6개와 질문 프레임 21개로 변경 예정 27건·적용 27건·재실행 변경 0건을 확인했다.
활성 runtime prompt는 11개이며 긴 배포 버전도 100자 저장 용량 안에서 보존했다.
반복 실행 전후 기준·prompt 본문과 지문이 같았고 rubric 승인 상태는 `unreviewed`다.
사용 도구는 [지식 초기화](../../backend/scripts/configure_ai_knowledge.py)와
[runtime 등록](../../backend/scripts/configure_ai_runtime.py)이며 운영 rubric 승인 도구로 해석하지 않는다.
산출물: `followup-live-20261108/bootstrap-operator/result.json`과 단계별 감사 JSON.

### 실제 레포·면접·보완 조회

공개 `golang/example`과 `spring-guides/gs-rest-service`를 고정 SHA에서 실제 GitHub·sol로 분석했다.
모델 전송 시도는 세 실행 합계 10회이며 원문 지문·줄 위치·고정 SHA와 분석 입력을 대조했다.
초기 Go 결과는 구현·설정·테스트를 포함했으나 초기 Java/Kotlin 결과는 설정·문서에 치우쳤다.
재귀 목록 개선 후 같은 Java SHA를 다시 실행해 Java/Kotlin 구현·설정·테스트 8개 원문을 확인했다.
Go는 기존 방식의 성공 결과이며 개선한 재귀 방식으로 실제 재실행하지 않았다.
전체 레포 독해, 모든 언어·빌드 도구, 거대 monorepo·큰 파일 조합, 실제 build/test 실행은 검증하지 않았다.
개인 저작·기여·성과와 해석의 정확성에 대한 사람 검수도 이 결과에 포함하지 않는다.
산출물: `followup-live-20261108/repository-diversity/combined-summary.json`과 각 원문·요청 기록.

격리 PG·Redis와 실제 sol로 준비·답변 9개·질문 저장·최종 종료를 실행했다.
면접은 `completed/current_turn=9`이며 `turn_asked=9`, `turn_answered=9`,
`interview_started=1`, `interview_completed=1`을 실제 저장에서 확인했다.
첫 실행의 후보 L1 binding 누락은 검증 fixture 문제로 남기고 제품 가드를 완화하지 않았다.
산출물: `followup-live-20261108/interview/result.json`, `storage-metadata.json`, 준비 재시도 기록.

별도의 가상 질문·답변 사례에서는 실제 T3가 레포 verification 1건과 외부 조회 1건을 요청했다.
Tool 요청을 모델 출력에 강제 주입하지 않았으며 실제 GitHub 원문 조회는 `found`였다.
외부 조회에서 공식 원문 3개를 저장하고 다음 T4 질문의 Director 계획·검수 입력에 반영했다.
레포 원문을 읽은 뒤 T3를 재분석하지만 외부 자료는 당해 T3 재분석에 소급해 넣지 않는다.
실제 sol 호출은 총 4회였고 같은 답변 재전송은 같은 턴·다음 질문을 유지하며 추가 HTTP 0회였다.
이는 기존 9턴에서 보완 요청이 없었던 결과와 구분하는 별도 사례다.
산출물: `followup-live-20261108/actual-tools-02/result.json`, `postexecution-checks.json`, 모델 입력 4개.

### 실제 리포트·프로필과 이미지 JD

실제 worker와 sol로 최초 리포트·프로필을 만들고 이의 제기·운영자 검토 경로로 revision 2를 생성했다.
revision 1·2, 점수 6개, 이전 revision 1의 같은 해시, 바뀐 프로필 입력 지문을 확인했다.
총 공급자 호출 6회이며 반복 조회·프로필 재사용의 추가 호출은 0회였다.
검증용 운영자가 재평가 절차를 행사했으며 `human_quality_or_score_approval=false`다.
따라서 실제 서비스 검토 기능의 실행 검증이며 사람의 점수·내용 품질 승인은 아니다.
산출물: `followup-live-20261108/report-profile-revision-02/combined-verification.json`과 revision 저장 기록.

이미지 JD는 합성 Wanted 응답·이미지 전달과 실제 Vision·sol·PG를 연결한 혼합 검증을 수행했다.
Vision 원문 블록 13개에서 sol 1회로 요구사항 6개를 저장하고 출처·인용·이미지/텍스트 해시를 확인했다.
같은 공고 캐시 재사용의 공급자 추가 호출은 0회였다.
상류 Wanted 응답과 CDN 전달을 합성했으므로 실제 공개 Wanted 이미지 공고를 종단 검증한 결과는 아니다.
첫 시도와 최종 `wanted-image-functional-20261108-02/result.json`을 각각 보존했다.

### 컨테이너·브라우저 연결

새 [서비스 이미지](../../backend/Dockerfile)와 [평가 이미지](../../backend/Dockerfile.evaluation)를 빌드했다.
평가 이미지는 사례·holdout·비밀값을 내장하지 않으며 읽기 전용 입력과 네트워크 차단으로 실행했다.
합성 서비스 사례 32개의 dry-run 입력 계약이 통과했고 실제 모델 실행·품질 합격은 그 검사 범위가 아니다.
실제 이미지 worker의 기능 6개·cron 4개 등록과 `role_kept` 재사용, 기존 프로필 보존을 확인했다.
산출물: `followups-final-validation/images/`, `followup-live-20261108/runtime/worker-result-02.json`.

실제 컨테이너 API·시험 인증 세션·브라우저에서 text 경로 6개 확인이 통과했다.
무인증 401, 인증 조회, 기존 text 면접, 실제 WS 질문·입력, MSW/TTS 미사용, 홈 API·화면을 확인했다.
`runtime/browser-result.json`의 결과이며 GitHub OAuth 교환을 실행한 것은 아니다.

`runtime/voice-browser-result-03.json`에서는 실제 Google 질문 음성을 브라우저로 재생했다.
가상 마이크를 통해 MediaRecorder로 녹음하고 실제 STT→sol 분석·Director→질문 2까지 진행했다.
MSW를 사용하지 않았고 실제 음성 API·바이너리 전송·전사·답변 저장을 확인했다.
이는 사람의 육성·실제 장치 사용성이나 음성으로 9턴 전체 진행을 검증한 결과와 구분한다.
같은 Redis의 기존 TTS 예산을 사용했으며 이번 후속 검증에서 예산을 추가 초기화한 횟수는 0회다.
최신 사용량·잔여 예산은 별도 후속 기록에서 확인한다.

### 전체 자동 회귀와 판정 범위

다음은 JudgeContext 보완 전 동결본의 각 전체 실행 결과이며 이전 부분 검사와 합산하지 않는다.

| 검사 | 결과와 범위 |
| --- | --- |
| AI | 758개 통과, Ruff·format 111파일·mypy 26소스 통과. 실제 공급자 품질 검사는 아니다. |
| FE | Playwright 147개 통과, 실패·skip·flaky 0. MSW 회귀이며 위 실제 브라우저 실행과 구분한다. |
| FE 정적·기반 | 강제 TypeScript 검사·build·ESLint와 proxy 4개 통과. |
| BE | Linux `final02` 한 번의 전체 실행에서 2405개 통과, 실패·오류·skip 0. |
| BE 정적 | 전체 Ruff 통과, format 530파일·mypy app 212소스 통과. |
| 공통 계약 | 스키마 2개·fixture 7개 통과. 부분 OpenAPI 검사이며 전체 런타임·TS 호환성 승인은 아니다. |

BE `final01`의 2403통과·깊이 제한 fixture 불일치 1건과 수정 후 `final02`는 별도 보존했다.
두 번째 snapshot은 승인된 fixture 파일 1개만 달랐고 제품·테스트 guard·timeout은 변경하지 않았다.
`final02`의 snapshot 705파일은 실행 전후 같았다. 결과는 `followups-final-validation/backend/`에 있다.
나머지 전체 결과와 소스 지문은 `followups-final-validation/summary.json` 및 검사별 폴더에 있다.
앞선 준비 fixture 누락·도우미 인자/종료 오류·실패 시도도 각 artifact에 남기며 성공 횟수에 합산하지 않는다.

### 진행 중인 평가와 남은 승인

위 통과 결과는 자동 검증 완료이며 사람의 기준·출력 품질 검수는 별도 보류 상태다.
실제 서비스 사례 32개 실행과 근거를 포함하는 JudgeContext 보완·재교정은 이 절 작성 시 진행 중이다.
기존 서비스 출력·control·라벨·Judge 버전은 보존하며 기존 결과를 새 판정으로 덮어쓰지 않는다.
해당 실행 결과·변경 후 영향 회귀와 새 Judge 교정 수치는 후속 절에서 별도로 추가한다.
운영 환경 배포, 사람의 음성 사용성·내용 품질 검수, 운영 SLO·동시성 검증은 별도 완료 조건이다.

### 실제 화면·예산 및 32개 서비스 실행의 확정 결과

실제 API의 revision 2 리포트는 점수 6개·면접관 피드백 3개·턴 9개를 반환했다.
반복 GET의 응답이 같았고 브라우저의 리포트·마이페이지가 오류 없이 표시됐다.
홈 응답의 프로필 역할 요약도 확인했다. `runtime/report-browser-result.json`에 기록했다.
voice 세션에 text 답변을 보낸 별도 실제 WS 검사는 `answer_rejected`를 반환했고
현재 턴·영구 답변은 그대로였다. 제품 가드를 실제 녹음 성공 경로와 따로 확인한 결과다.

실제 음성 경로에서 답변 1개·분석·다음 질문을 저장했고 LLM 기록 2개에 sol 시도 3개가 남았다.
공식 원문 재검색은 같은 출처 3개를 재사용하며 추가 HTTP 0회였다.
보완 코드 원문은 고정 SHA `99635268fe86b3ef3762a6a2b5dcd9ba67b6b9ce`의
`backend/tests/test_config.py:1~158`과 내용 해시를 저장했다.

TTS 신규 소비는 138자이며 기존 Redis는 `limit=999826`, `used=604`, `pending=0`, `uncertain=0`이다.
초기화 이전 174자를 포함한 기록상 누적은 778자, 남은 앱 예산은 999,222자다.
Cloud 잔여량 직접 조회값이 아니며 기존 예산을 다시 초기화하지 않았다.
원본은 `runtime/final-live-storage.json`이다.

원문 전달 보완 전 실제 서비스 32개 실행은 입력 계약 32개 통과·서비스 성공 31개·후보 거절 1개였다.
리포트 형식 13개가 통과했고 진단 Judge는 성공 출력 31개를 판정했다.
원래 판정은 accept 12·ambiguous 4·reject 15이며 사람 검수·품질 승인 결과가 아니다.
서비스 모델은 128시도 예산 중 57회, Judge는 별도 64시도 중 31회를 사용했다.

`q-0006.v2`는 계획·독립 검토 2회 후 `director_candidate_replan`으로 안전하게 거절됐다.
같은 입력을 별도 단 한 번 진단 실행했을 때는 계획·검토 2회로 성공했다.
32개 원실행을 32통과로 고치거나 두 실행을 합쳐 한 번의 전체 성공으로 계산하지 않는다.
원본은 `eval-service32-live.json`과 `q0006-rejection-diagnostic/`에 각각 보존했다.

### 평가 이미지 실행 방법의 명시

평가 compose는 같은 checkout에서 빌드한 runtime 이미지를 `EVAL_RUNTIME_IMAGE`로 받는다.
deploy compose가 생성하지 않는 `devon-backend:local`을 기본으로 추측하지 않는다.
저장소 루트 PowerShell에서 다음과 같이 입력 검증만 실행할 수 있다.

```powershell
docker build -f backend/Dockerfile -t devon-backend:local .
$env:EVAL_RUNTIME_IMAGE = 'devon-backend:local'
$env:EVAL_CASES_DIR = (Resolve-Path 'ai/evals/service_regression').Path
New-Item -ItemType Directory -Force '.claude/scratch/eval-input-check' | Out-Null
$env:EVAL_OUTPUT_DIR = (Resolve-Path '.claude/scratch/eval-input-check').Path
docker compose -f compose.evaluation.yaml --profile evaluation build
docker compose -f compose.evaluation.yaml --profile evaluation run --rm evaluation
```

이 기본 실행은 검증 전용 manifest와 네트워크 차단을 사용하며 모델을 호출하지 않는다.
실제 평가에는 설정에서 만든 모델 manifest와 명시적 시도 예산을 따로 사용한다.
미검수 자료의 실행 성공은 `자동 검증 완료`, 사람의 기준·해석 검수는 `사람 검수 대기`로 구분한다.

### Judge 원문 전달·저장 출력 재판정의 최종 확인

실제 사례의 원문·위치·질문 계약·면접관 역할·Tool 상태를 64KiB 이내의
`judge-context.v1`로 전달한다. 없는 원문은 채우지 않고 이전 분석·거절 후보는 원문과 구분한다.
정답·다른 control·검수자 메타데이터는 전달하지 않는다.
[context 투영](../../ai/evals/judge_context.py), [Judge](../../backend/scripts/ai_model_judge.py),
[실행기](../../ai/evals/eval_runner.py)와 [CLI](../../backend/scripts/run_ai_evaluation.py)에 연결했다.

기존 성공 출력 31개는 input·expectation·binding·output 해시를 확인한 뒤 v2 Judge로 재판정했다.
서비스 모델 호출은 0회, Judge는 64시도 상한 중 31회였고 실행 실패는 없었다.
판정은 accept 18·reject 12·ambiguous 1이며 원래 실패한 q-0006은 그대로 남았다.
원본 결과와 새 `eval-service32-grounded-rejudge.json`은 별도 파일이다.
재판정 완료를 서비스 재실행이나 생성 내용 전체의 품질 합격으로 세지 않는다.

기존 승인 사례 11개의 제어 출력 34개를 v2 Judge로 다시 교정했다.
실행 34개 성공·재시도 0개·기존 라벨 일치 33/34였다.
허용 11개와 거절 대상 22개는 일치했고, 기대값 ambiguous인 `e-0002.v1/control2`를 reject했다.
앞선 v1의 31/34와 새 v2의 33/34는 각각 보존했다.
고정 순서의 각 1회 측정이며 일반 정확도, 순열·반복 안정성, 사람 품질 승인을 뜻하지 않는다.
산출물은 `approved-controls-grounded-20261108-01/`에 있다.

판정 12개 거절의 원인을 대조하자 기준과 관찰 범위의 문제가 함께 확인됐다.
q2·q5는 기존 검토 이견이 남아 있고, q3는 허용하는 주제 전환 범위를 재검수해야 한다.
q7의 기존 평가는 T4 질문 생성만 실행해 선행 조회 판단을 관찰하지 않았다.
r1~r8의 v2 입력에는 원래 전역 자료 m1/m2가 빠져 있었고,
리포트 평탄화 후에는 원래 검증된 내부 참조도 Judge에 보이지 않았다.
이 결과만으로 운영이 조회를 생략하거나 보고서 내부 참조가 없다고 결론내리지 않는다.

### 보고서 자료 연결과 내부 관찰의 추가 보완

기존 v1·v2 자료와 실제 실행·판정은 보존하고 별도
[보고서 v3 코호트](../../ai/evals/report_source_binding_cohort/binding-manifest.json)를 구성했다.
원래 m1/m2 원문과 명시 경로·줄 표기를 그대로 사용한다.
새 연결은 가상 평가의 사용 가능 자료라는 전제이며 원래 질문 당시 사용 이력의 복원이 아니다.
필요한 ref는 기존 합성 snapshot에 연결하고 실제 코드 버전을 증명한 것으로 취급하지 않는다.
질문·답변·질문 계약·허용/금지 기준·control은 바꾸지 않고 검수는 `unreviewed`로 유지한다.

평가 bridge는 실제 모델의 검증된 `ReportNarrative`를 같은 입력으로 다시 검증한 뒤
`validated-report-claims.v1` artifact를 만든다. 문구·section·persona·claim_index·turn_refs·
evidence_refs를 함께 보존하고 공개 `output_hash`와 별도의 `artifacts_hash`를 기록한다.
공개 보고서·DB·서비스 런타임을 변경하거나 공개 문자열에서 참조를 만들어 붙이지 않는다.
[artifact 검증](../../ai/evals/eval_artifacts.py)과 재판정은 형식·버전·해시 쌍·변조를 검사하고,
원래 artifact가 없는 결과에는 숨은 근거를 만들어 채우지 않는다.

이 관찰을 읽는 v3 Judge는 기존 기본 v2와 분리했다.
`--judge-prompt ai/prompts/evaluation-judge-v3.md --judge-prompt-version evaluation-judge-v3`를 명시한다.
내부에만 있는 항목이 공개 응답에 표시됐다고 간주하거나 공개 누락을 대신 충족할 수는 없다.

[q7 v3 코호트](../../ai/evals/component_regression/binding-manifest.json)는
`director_verification` 단계의 실제 `verification_decision`만 실행한다.
요청·경로·SHA는 입력과 일치했고 model factory·HTTP·다음 Director는 모두 0회였다.
이는 조회 판단 함수의 자동 검증이며 실제 원문 조회는 앞선 별도 실검증 결과를 참조한다.
새 manifest의 출처 지문은 `utf8_lf`로 정규화하고 원본 raw 지문은 별도로 보존했다.
Windows CRLF·Linux LF에서 같은 의미의 자료가 해시 차이만으로 실패하지 않는 회귀도 확인했다.

추가 보완 후 AI 전체 782개, BE 평가 관련 42개가 통과했다.
기존 전체 BE 2409개 이후의 평가 연결 변경에 대한 별도 영향 검사이며 두 수치를 합산하지 않는다.
Ruff 전체·format 530파일·mypy app+scripts 228소스도 통과했고 검사 대상 713파일은 전후 같았다.
원본 58개 자료, v2 코호트 66개 JSON과 BE app 212파일도 이전 동결본과 같았다.
산출물은 `report-source-observation-verification-01/`과
`followups-final-validation/backend-static-post-artifacts/`에 있다.

### 최종 이미지와 임시 검증 프로세스

추가 평가 코드와 v3 prompt를 포함한 runtime·평가 이미지를 새로 빌드했다.
평가 이미지의 실제 실행 파일 7개 해시가 작업본과 같았고 키·사례·holdout 내장 파일은 없었다.
네트워크 없이 기존 32개·새 보고서 8개·조회 결정 1개의 입력 계약이 모두 통과했다.
그 실행에서는 서비스·Judge 예산을 생성하지 않았다. 실제 모델 실행과는 별도 결과다.
산출물은 `followups-final-validation/images-artifacts-final/`에 있다.

시험 로그인 세션을 폐기하고 임시 API 컨테이너·Vite를 종료했다.
DB·Redis의 검증 이력과 TTS 예산은 보존했으며 5173·8000 포트는 해제됐다.
이는 평상시 `.env`의 DB 적용이나 운영 배포를 완료한 상태가 아니다.
정리 도우미의 인코딩·부분 정리 후 재실행 오류도 기록하고 마지막 정리 결과와 구분했다.
산출물은 `runtime/cleanup/attempt-03/result.json`이다.

### 자료·관찰 보완 후 실제 9개 검증의 확정 결과

`source-binding-observation-live-01/`에서 기존 실행과 분리해 실제 sol로 검증했다.
새 보고서 v3 8개와 조회 결정 q7 v3 1개이며 기존 공개 출력·기준을 고쳐 통과시키지 않았다.

| 항목 | 실제 결과 |
| --- | --- |
| 입력·실행 | 9/9 통과. 조회 결정 1개는 실제 함수만 실행했고 model factory·HTTP·다음 Director는 0회였다. |
| 보고서 형식 | 8/8 통과. 점수·서술 모델은 각각 8회, 총 16/20시도를 사용했다. |
| 내부 근거 | 실제 검증된 모델 Narrative와 최종 artifact의 문구·구분·담당·순번·턴/Evidence 참조가 8/8 일치했다. 별도 artifact 해시·참조 그래프 대조도 통과했다. |
| Judge 실행 | 명시한 v3 Judge 9/9 실행 성공, 9/16시도 사용. 재시도·실행 실패 0회다. |
| 진단 판정 | accept 8·reject 1. 사람의 정답 승인이나 전체 서비스 품질 합격으로 승격하지 않는다. |
| 보존 | 기존 자료·v2 결과·31개 재판정·제어 출력 교정과 새 실행 전후 소스 지문이 같다. |

남은 reject는 `r-0008.v3`이다. m1/m2가 실제 모델 입력에 모두 있고,
최종 Claim 24개도 검증된 모델 결과와 같지만 구조화된 evidence_refs에는 m2만 사용했다.
Redis 보완 관찰은 실제 턴 2·6으로 연결했고 `build.gradle:38~43`은 한계 문장에만 언급했다.
Judge는 해당 a3의 m1 근거 연결을 충족하지 못했다고 판정했다.
이제 자료 누락·관찰 손실과 구분되는 특정 인용 품질 진단이며, 기준은 여전히 미검수다.
사람 기여·성과를 확정하거나 환각이라고 단정하지 않았고 재실행·기준 완화로 결과를 바꾸지 않았다.

이번 후속 구현과 기능·형식·참조·실행의 상태는 **자동 검증 완료**다.
내용의 모든 품질 판정이 통과한 것은 아니며 사람의 rubric·평가셋 검수는 **사람 검수 대기**로 유지한다.
운영 적용·게시·배포, 실제 공개 Wanted 이미지 공고, 물리 마이크의 전체 9턴,
모든 언어·규모와 운영 동시성·SLO는 이번 완료 범위에서 확인하지 않았다.

원본 모델 입력·결과·판정과 독립 대조는 `source-binding-observation-live-01/`의
`result.json`, `summary.json`, `preservation.json`에 있다.
겹치는 검사 수를 합산하지 않은 최종 색인은 `followups-final-validation/final-summary.json`이다.
원본 worktree 371파일·patch·status는 그대로이며 공개 대상 1104파일에서 실제 키 값은 검출되지 않았다.


## 2026-11-08 — 게시 PR #212~#219의 의존 관계 정리

사용자 요청에 따라 게시 당시 신규 403경로만 대상으로 정리한다.
게시 후 별도로 변경한 45경로는 원본 그대로 보존하고 이번 게시에서 제외한다.
기존 PR 번호와 develop 기준은 유지하며 원본 8개 HEAD 뒤에 후속 커밋을 추가한다.

- 공통 모델·마이그레이션·런타임 프롬프트·검색·준비 lease·이벤트 기반은
  #213에서 제공하고 문서·JD → Director·레포 → 리포트·프로필 순으로 소비한다.
- 평가 실행은 #214, 데이터 의존 검사와 CI 연결은 #215, REST·WebSocket과
  음성·FE 최종 통합 검사는 #219에 둔다. 파일별 신규 변경의 소유자는 한 곳이다.
- 준비 실패 후 실제 REST·큐·worker 재시도를 확인하는 테스트 한 개만
  `test_director_prepare.py`에서 `test_director_ws.py`로 옮긴다.
  기존 검사 본문·fixture·도우미와 전체 테스트 정의를 보존한다.
- 선행 PR과 겹치는 19개 패치는 미적용 후속 변경이다. 선행 반영 이후
  적용·재기준화·통합 재검증이 필요하며, 단독 CI 통과나 즉시 병합 가능으로
  보고하지 않는다. 이번 변경으로 선행 PR을 병합하지 않는다.

원동결 1104파일에서 새로 실행한 자동 검증은 AI 782건 통과, BE 2413건 수집,
AI·BE Ruff/format/mypy, 공통 계약 검사와 앱 import 검사 통과다.
Windows 표준 asyncio socketpair를 차단했던 검증 도구 오류는 제품 변경 없이
검증 도구만 고쳐 해당 검사를 재실행했다. 초기 실패 기록도 보존한다.
테스트 이동 후 통합 전수 검증과 각 게시본 단독 검증은 별도로 실행·기록하며,
기존 실제 공급자 실행 결과를 이번 변경의 새 결과로 재사용하지 않는다.
외부 모델·STT·TTS·Vision·검색 유료 호출과 사람 평가는 이번에 실행하지 않는다.
지속되는 결정은 [0041](decisions/0041-published-pr-dependency-order.md)에 남긴다.


## 2026-11-08 — 기존 작업의 신규 변경 게시와 실제 자료 후속 보완

사용자 요청에 따라 기존 작업을 먼저 게시하고, 별도 `feature/ai-real-source-hardening-20261108`에서 후속 구현을 시작했다.
기존 통합본·index·원본 1104파일과 선행 PR은 보존했다. 초기 설계·task·testing 문서는 변경하지 않는다.
후속 결정은 [0039](decisions/0039-real-source-coverage-and-official-snapshots.md)다.

### 신규 부분만 게시한 PR

모든 base는 `develop@18f4105b2e7e9885df118d283badbf59692ec5b4`다.
선행 기준본과 동결 원본을 대조한 신규 변경은 403경로이며 추가 263·수정 140·삭제 0이다.
직접 변경 384개·후속 patch 19개와 적용 안내 12개로 총 415경로를 게시했고 그룹 간 중복은 0개다.
선행 tip·상속 커밋은 제외했으며 341커밋 모두 추가+삭제가 300줄 이하이고 최대 270줄이다.
독립 재생에서 403개를 모두 적용한 전체 1104파일이 동결본과 UTF-8 LF 지문까지 일치했다.

| PR | 범위 | 파일 | 커밋 | 추가/삭제 |
| --- | --- | ---: | ---: | ---: |
| [#212](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/212) | 공개 API와 AI 내부 계약 정의 | 5 | 3 | +337/-23 |
| [#213](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/213) | 공급자·실행 설정 및 개발 초기화 | 44 | 80 | +4749/-28 |
| [#214](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/214) | 평가 실행·근거 기반 Judge·CLI·CI | 26 | 23 | +3786/-18 |
| [#215](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/215) | 서비스 평가 사례·원문 연결·회귀 자료 | 98 | 83 | +15742/-0 |
| [#216](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/216) | Director·답변 분석·레포 원문·근거 Tool | 104 | 41 | +7549/-218 |
| [#217](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/217) | 문서 Claim·공고 이미지·도메인 연결 | 52 | 26 | +4762/-161 |
| [#218](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/218) | 리포트 재시도·검토·버전과 프로필 갱신 | 47 | 71 | +5045/-170 |
| [#219](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/219) | 질문 음성·예산과 FE 계약 실행 연결 | 39 | 14 | +2451/-235 |

8개 모두 Draft다. **patch는 PR 병합만으로 실행되지 않는다.** 선행 반영, 기준 지문 확인, 신규 patch 적용과 최종 통합 검증이 필요하다.
원격 HEAD·base·Draft·전체 파일 목록·커밋 목록·규모·UTF-8 본문을 게시 후 실제 다시 읽어 대조했다.
직접 게시 Python·JSON·YAML 329개, 그룹별 diff 검사와 현재 materialized 공통 형식 검사는 통과했다.
후속 patch 계약까지 검증한 결과는 아니며 구현 그룹의 단독 수집 실패도 그대로 PR에 기록했다.
원격 #212의 BE CI는 1736통과·1skip, migration CI도 통과했다.
#213~219의 CI 실패 13 job은 제외한 선행·다른 그룹·비활성 patch 누락으로 설명됐으며 실패 상태를 통과로 바꾸지 않았다.
완전한 게시 조합의 CI 통과나 잔존 결함 0을 증명한 것은 아니다.
공개 415파일을 실제 민감 설정 10개와 메모리에서 대조해 값 일치 0건을 확인했고 private 환경 파일은 게시하지 않았다.
근거는 보존한 `ai-final-publication-20261108/`의 `publication-verification.json`, `branch-verification.json`, `validation-summary.json`, `remote-prs.json`, `remote-ci-audit.json`이다.

### 게시 전 실제 자료 검증에서 확인한 범위

- Memos는 실제 8원문·58659bytes·1698줄을 읽었다. Umami도 실제 8원문을 분석했다. 전체 레포 실행·개인 기여 검증은 아니다.
- Healthchecks의 기본 L1 50초 timeout과 개행 전용 겹침 구간 오류는 보존했다. 별도 timeout 진단 성공을 원래 실행 성공으로 바꾸지 않았다.
- Halo의 옛 L2는 설정 8개에 편중됐으며 Java·테스트 원문은 0개였다. 이를 전체 Java 프로젝트 분석 성공으로 세지 않는다.
- 실제 Wanted 개발자 공고 361487은 API→제품→격리 DB에서 요구사항 20건의 원문 인용을 확인했다. 구조화 본문이므로 모델·Vision 0회가 정상이며 기존 9턴의 합성 JD와 다른 검증이다.
- 자소설의 2015년 실제 이미지 공고는 Vision 31블록·sol 후보 6개를 얻었지만 기존 분류 제목 검사에서 최종 0개를 채택했다. 후보의 인용·참조 6/6은 맞았다. Wanted 이미지나 새 사이트 adapter 완료 증거가 아니다.

### 별도 개발본의 후속 보완

이미지 제목의 명시 별칭·bullet을 인식하도록 보완했다. 저장된 실제 출력 재생에서 업무 2·우대 4·필수 0이며 인용·참조·기술명은 그대로다.
문장 속 단어, 우대의 필수 승격, 모호한 절과 불일치 인용은 계속 거절한다. 회귀 18 RED 뒤 관련 35 GREEN, 이 변경 후 AI 전체 809·Ruff·format·mypy가 통과했다. 외부 모델 재호출은 0회다.
별도 Halo 구조 진단은 같은 SHA의 공개 GET 1회로 1111590bytes·4209항목·일반 파일 3323·Java 1386·test Java 383을 확인했다.
이 진단은 구조 크기·범위 계측이며 실제 collector의 canonical tree chain이나 선정·L2 성공으로 세지 않는다.
L1 180초·기타 작업 시간 예시를 정렬했고 설정/준비 deadline 31개 회귀가 통과했다. sol·xhigh·stream·출력 128000과 worker 1800초는 보존했다.
FE API 문서의 revision·이의제기·명시 리포트 재시도 설명을 실제 동작에 맞추고 GET report의 기존 404 누락을 OpenAPI에 추가했다. 공개 동작을 새로 만들지 않았다.
이후 구조 inventory/window 분리와 공유 공식 snapshot 경로를 구현했다. 구체적인 검증 범위는 아래와 같다.
이 후속 변경은 #212~219에 추가 게시하지 않았다. 사람 검수는 계속 `사람 검수 대기`이며 자동 통과만 `자동 검증 완료`로 기록한다.

### 실제 구조·원문과 공식 자료의 후속 검증

준비 collector의 구조 응답·전체 수집·원문·모델 입력 예산을 분리했다.
`repository_sources.py`와 `repository_source_selection.py`는 전체 inventory와 실제 모델 선정 window를 따로 보존한다.
`prepare._save_analysis`는 경로·SHA·전달 범위·미확인 범위를 저장하며 기존 면접 중 조회 권한을 확장하지 않는다.
저장된 Halo 실제 tree의 오프라인 계측에서는 4209항목 중 후보 3328개를 1437개 window로 제한한 요청이 262127/262144bytes였다.
별도 live matrix의 실제 선정 요청은 후보 1435개·262141/262144bytes·HTTP 200이었다. 사전 계측과 실제 모델 전송 수치를 같은 회차로 합치지 않는다.
Java 1386개·test Java 383개를 전체 목록에서 확인했고, 실제 선정된 8원문에는 Java·테스트·설정·frontend가 포함됐다.
개행 전용 겹침 구간은 빈 SourceDocument로 만들지 않으며 원래 줄 위치와 생략 한계를 보존한다.

새 실제 레포 matrix에서 Healthchecks·Umami·Memos는 L1→실제 파일 선정→L2 각각 5개 관찰의 저장용 결과까지 성공했다.
Halo는 L1·선정 성공 후 L2 120초 timeout으로 실패했다. 이 원본 실패는 그대로 보존했다.
같은 저장 입력·schema·전송 body의 별도 180초 진단은 약 113초에 5개 관찰로 완료됐다.
입력 토큰 대부분이 cache hit였으므로 180초가 필수이거나 timeout 확대만이 성공 원인이라고 해석하지 않는다.
matrix 12회와 별도 진단 1회로 총 실제 모델 13/16회를 사용했고 진단의 GitHub·DB 호출은 0회다.
독립 대조는 32파일·34구간에서 SHA·경로·줄 위치·모델 입력·저장용 UUID/참조를 확인했다.
30파일은 전체 Git blob을 대조했고 Healthchecks와 Memos의 큰 파일 각 1개는 prefix 범위만 확인했다.
Python AST·JSON reader와 나머지 원문 구간 처리는 검증했지만 모든 언어의 전용 해석기나 TOML 실자료 검증을 주장하지 않는다.

공식 자료는 `official_catalog.json`의 8개 항목과 명시 CLI→Tavily 추출→공유 불변 snapshot→면접별 소유 원문 경로를 추가했다.
JS shell인 TourAPI 항목은 부적합으로 남기고, URL 접근 확인을 실제 본문·요청 절 추출 성공과 구분했다.
`OfficialSourceSnapshot`은 사용자·면접 FK 없이 원문·추출 Markdown 줄·hash·시각·한계를 저장한다.
기존 `InterviewExternalSource`에는 snapshot FK를 남기며 소유권·인용·검색 상태·부족 시 Tavily fallback을 유지한다.
실제 MDN·Python URL의 Tavily 추출 1회는 HTTP 200이었다. MDN 원문 4306자를 격리 PostgreSQL에 저장했고
첫 수집 시 사용자·면접 행이 없는 상태와 이후 면접별 원문 복사·재사용을 추가 외부 HTTP 0회로 확인했다.
Python의 실제 캡처는 링크가 포함된 Markdown 제목 때문에 최초 절 추출에 실패했다.
제목 인식 수정 후 같은 캡처 재생에서 Task Groups 절 165~201줄을 확인했다. 추가 API·DB 쓰기는 0회다.
모든 catalog 항목의 provider 실추출 성공이나 다국어 의미 매칭의 완전성을 증명한 결과는 아니다.
legacy 캐시 키 순서, 유데이터 downgrade 거절, CLI URL query 우회 거절·실제 DB 확인도 회귀로 보완했다.
관련 70개 테스트·정적 검사·migration 정합성 검증이 통과했으며 기존 원문과 최초 실패 기록을 덮어쓰지 않았다.

### 긴 실제 면접에서 확인한 입력 중복과 재검증

실제 Wanted 361487의 요구사항 20건과 고정 SHA의 Umami 원문·분석을 재사용했다.
사용자·소유 관계와 지원자 답변은 검증용 합성 입력이다. 실제 개인의 기여·성과 검증은 아니다.
`actual-01`은 3턴 뒤 지원자 답변 생성용 검증 입력의 50초 timeout으로 중단됐다.
별도 명시한 `actual-02`는 미답변 4번 질문부터 정상 답변을 제출했지만 6턴 분석 뒤 질문 7의 입력 상한에서 중단됐다.
당시 Director 요청 264553bytes가 262144 상한을 초과해 provider 시도 0회로 거절됐고, 6개 답변·분석과 호출 기록은 남았다.
이 두 회차의 실패를 완료로 변경하지 않았으며 누적 실제 모델 호출은 26회였다.

[0040](decisions/0040-director-single-copy-source-input.md)에 따라 `agent._model_reference_texts`와 `runtime._input_payload`에서
Context의 같은 원문을 `reference_texts`에 중복 전달하는 부분만 제거했다.
서버의 전체 참조 검증 map, 모든 Context·원문 위치·SHA·문답 이력·기여 정정과 현재·과거 분석은 그대로다.
Context 밖에서 허용한 `job_posting` 원문은 별도로 전달하며 출력 계약·프롬프트·독립 Plan/Review 두 시도는 바꾸지 않았다.
실제 실패 입력의 무모델 재구성은 264553→174853bytes였으며 상한 확대나 과거 이력 삭제는 하지 않았다.
9번째 질문·8이력·큰 원문·최신 기여 정정·위조 근거 ID의 실제 gateway 회귀는 2 RED→2 GREEN이었다.
수정 뒤 AI 전체 809개와 Ruff·format 119파일·mypy 28소스, root의 동일 gateway 회귀 2개가 통과했다.

수정 전 전체 BE 검사에서는 격리 DB 이름의 fixture 조건 불일치와 의미가 부족한 원문 mock을 먼저 발견했다.
실패 회차를 보존하고 DB 접두사·실제 의미 원문 fixture·MYPYPATH를 올바르게 지정한 별도 실행에서
2472통과·1skip, 전체 Ruff·format·mypy 235소스·공통 형식 검사를 확인했다. 외부 provider 호출은 0회다.
이는 Director 중복 제거 전 결과다. 수정 후 별도 BE 전수 회차는 2474통과·1skip·12warning이었다.
전체 Ruff·format·mypy 235소스·공통 계약 부분 형식 검사도 통과했고, 검사 전후 537개 Python 소스 지문이 일치했다.
격리 PostgreSQL/Redis와 외부 네트워크 차단으로 실행했으며 provider 호출 0회다.
실제 모델의 새 9턴 검증과 단독 게시본의 CI 성공으로 이 결과를 확대하지 않는다.

수정 후 runtime/evaluation 이미지를 새 `20261108-director-budget` 태그로 빌드했다.
외부 네트워크 없이 실제 설치된 AI와 각각 305·313파일의 지문·catalog 8개·민감 환경 파일 미포함을 확인했다.
컨테이너의 평가 입력 계약 검사는 `--split all`로 32+8+1=41건 `validated_only`이며 모델·DB 호출 0회다.
최초 기본 dev split 29건만 검사한 명령의 단언 실패는 보존하고 전체 split 검사와 구분했다.
이 검사는 Judge 내용 평가·사람 승인·운영 release gate 통과를 뜻하지 않는다.

### 수정 후 새 정상 면접의 최종 실행

`actual-03`은 이전 실패 세션의 Director를 강제로 다시 실행하지 않았다.
제품 `abandon_interview`→`retry_interview`로 새 세션을 만들고, 전용 Redis의 실제 queue에서
`interview_prep` ARQ 작업 1건을 소비했다. 준비 작업은 complete 1·failed 0이었다.
새 세션의 기본 `answer_mode=voice`는 보존했으며, 이후 문답은 STT 뒤의 텍스트 입력에 해당하는
`process_answer` 서비스 함수로 검증했다. 실제 STT/TTS·브라우저·OAuth의 전체 경로 검증은 아니다.
리포트·프로필도 실제 서비스 함수를 호출했으며 해당 후처리 ARQ worker 전체 실행으로 세지 않는다.

실제 Wanted 요구사항과 Umami 고정 SHA의 유효한 분석을 재사용했다.
이번 준비에서 새 L1/L2 모델을 재실행한 것으로 세지 않으며, 새 9턴의 모델 호출은 실제 연결이다.
지원자 답변·사용자·소유 관계는 검증용 합성 입력이다.

| 저장·실행 항목 | 실제 결과 |
| --- | --- |
| 면접 | `completed`, 문답 9개·답변 분석 9개 |
| 페르소나 | HR 1·기술 6·도메인 2 |
| 리포트 | `created`, 점수 6개와 본문 저장 |
| 프로필 | `updated`, 저장 행 존재 |
| 모델 호출 | 신규 39회, 이전 실패 회차 26회를 계승해 누적 65/90회 |
| 입력 상한 | 신규 39개 실제 wire의 최대 189194/262144bytes |
| 원본 보존 | 이전 6답변·13호출 기록과 모든 `actual-01/02` 산출물 불변 |
| 실행본 보존 | 305개 제품 파일·private 환경 파일 지문 불변, cleanup/export 오류 0 |

7~9번 질문의 실제 Plan/Review 요청은 각각 174184/174916, 178024/179179, 187656/189194bytes였다.
독립 감사에서 39개 전송 body의 실제 byte/hash와, 72회 문답 이력·페르소나·과거 분석 대조가 일치했다.
Evidence 5개도 원래 L2 원문·줄 범위·고정 SHA와 일치했다. 새 조회 허용 범위나 개인 기여를 추정하지 않았다.
이번 9턴의 추가 레포 조회 요청·외부 검색 요청·Tool trace·외부 원문 행은 모두 0건이었다.
따라서 이 체인이 검색·보완 분석 분기의 실재발생까지 검증했다고 표현하지 않는다.
해당 분기의 이전 별도 검증과 이번 공식 snapshot 수집·재사용 검증은 서로 구분한다.

이 결과는 해당 입력·모델·설정에서의 기능 실행 **자동 검증 완료**다.
미검수 rubric에 따른 점수·질문 내용의 품질 승인과 사람 검수는 대체하지 않는다.
기존 `r-0008.v3`의 reject나 사람 검수 대기 상태도 새 기능 성공으로 변경하지 않았다.
원본 실행·DB export·보존 기록은 `hardening/real-service-chain/actual-03/`,
전수 검사는 `backend-verification-director/`, 새 이미지 검사는 `image-checks-director/`에 보존했다.
게시한 PR 8개는 앞선 동결본의 신규 부분이며, 여기의 후속 보완은 별도 로컬 개발본에만 있다.
선행 반영·후속 patch 적용·게시 조합 재검증과 운영 배포를 이번 로컬 실행 완료로 대신하지 않는다.

## 2026-11-09 — 두 모델의 새 전체 연쇄 검증과 Director 입력 보완

### 범위와 설계 결정

기존 로컬 hardening 원본을 보존하고 별도 `ai-full-model-validation-20261108` 작업본에서 진행한다.
사용자 요청의 기본 방향은 개발에 Luna를 사용하면서 Sol과 같은 조건으로 실제 기능 연쇄를 확인하는 것이다.
설계 결정은 [0043](decisions/0043-director-turn-state-and-reference-constraints.md)에 기록했다.
이 절은 공개 PR 게시·병합이나 운영 DB·환경 적용 완료를 뜻하지 않는다.

Director의 [runtime](../../ai/src/devon_ai/agents/director/runtime.py)은 확정된 이력으로
`next_question_no`, `answered_turn_count`, 직전 답변의 번호·ID와 남은 질문 수를 계산한다.
8개 답변 이후의 9번 질문과 9개 답변을 모두 받은 종료 시점을 구분하며, 종료 권한은 Controller에 둔다.
v6 Plan schema `director-plan.v3`는 실제 등록된 근거 종류별 ID·Evidence·JD·과거 parent·허용 페르소나를
선택하도록 제한한다. 기존 semantic 검증과 Plan/Review 총 2시도는 유지하며 UUID 자동 보정은 하지 않는다.
`director-runtime-v4.md`·v5 본문은 보존하고 새 v6 본문과 runtime recipe를 사용한다.
공개 API와 기존 `Context` dataclass는 변경하지 않았다.

[개발 환경 예시](../../backend/.env.example)는 Luna slot 1과 `OPENAI_MODEL=gpt-6-luna`를 기본 방향으로 두고
Sol slot 3을 보존한다. 실제 task 모델은 DB 프롬프트에서 읽으므로 각 검증 DB에 모델별 새 deployment를 등록한다.
각 실제 모델 실행 동안 private 환경 파일과 제품 소스를 고정했다.
완료 뒤 수행한 로컬 기본 모델 전환은 아래의 실제 활성화 결과와 구분해 기록한다.

### 완료된 자동 검사와 독립 task 실호출

v6 반영 후 AI 전체 **840개**, BE 영향 검사 **56개**와 관련 정적 검사가 통과했다.
이 수치는 해당 코드의 **자동 검증 완료**이며 새 전체 면접 연쇄의 완료 결과와 합산하지 않는다.
원문 인용·참조 ID·마지막 질문·구버전 호환의 검증을 유지했고, 기존 의미 검증을 완화하지 않았다.

고정 입력 재생에서 별도로 남았던 아래 네 task는 Sol/Luna 각각 실제 공급자로 실행했다.
각 모델에서 task당 1회, 총 4회 호출로 모두 제품 검증을 통과했다.

| 독립 task | 확인한 범위 |
| --- | --- |
| `domain_category` | 원문 기반 분류와 실패 없는 계약 반환 |
| `doc_claims` | 합성 문서의 Claim 추출과 원문 줄 연결 |
| `claim_code` | 기술 주장과 공개 코드 대조, 개인 역할·성과의 미확인 보존 |
| `jd_extract_image` | 제공한 이미지 추출 블록에서 JD 요구사항과 참조 구성 |

검증 입력은 공개 자료와 합성 문서·주장 fixture가 포함된 독립 사례다.
새 사이트 URL adapter 지원이나 실제 개인 기여 검증, 모든 이미지 레이아웃의 성공으로 확대하지 않는다.
산출물은 private `full-validation/tasks-{luna,sol}-01/tasks/summary.json`에 보존했다.

### 모델이 요청한 보완 조회 분기의 실제 연결

별도 자연 발생 조회 사례에서 각 모델은 실제 T3→레포 원문 조회→T3 재분석→다음 Plan/Review의 4회 모델 호출을 수행했다.
모델이 요청한 Umami 고정 SHA의 구현·테스트 원문 2개를 실제 GitHub 응답과 blob hash로 대조했다.
같은 원문·ID가 재분석 T3와 다음 Plan/Review 입력에 전달됐고, 다음 질문은 새 코드 근거 2개를 참조했다.
이는 합성 질문·지원자 답변·소유 관계 fixture에서 제품 `process_answer`를 실행한 결과다.

외부 자료 검색은 그 T3 재분석 이후에 실행되고 결과·한계가 다음 Director 입력으로 전달됐다.
Luna의 해당 질의는 `insufficient_analysis`, `query_terms_missing`, 채택 원문 0건이었다.
Sol은 MDN 원문 1건을 `found`로 전달했다. Sol의 다음 질문이 그 외부 원문을 별도로 인용한 것은 아니다.
부족한 검색 결과를 `found`로 승격하거나 외부 자료가 당해 T3에 이미 반영됐다고 기록하지 않는다.
두 모델의 코드 원문 전달·외부 상태·wire/참조 무결성에 대한 저장 산출물 감사는 통과했다.
근거는 `full-validation/tool-natural-{luna,sol}-01/`과 `tool-natural-binding-audit-02.json`이다.
이 독립 분기의 성공은 새 전체 9턴에서 같은 분기가 반드시 발생한다는 보장이 아니다.

### 첫 전체 실행의 실패 보존과 같은 조건의 재검증

첫 회차는 새 DB·Redis·DB 프롬프트에서 L1을 새로 생성하고, 그 모델이 선정한 원문으로 L2와 면접을 이어 갔다.
Wanted 361487의 실제 요구사항 20건과 Umami SHA `559e3c607c23d2c72d9bd4f6481bda428255323c`를 사용했다.
두 실행의 Wanted 원문·요구사항 hash가 일치했다. 과거 L1/L2 분석 결과는 서비스에 주입하지 않았다.
지원자 답변은 두 실행 모두 별도 Luna 모델·같은 공개 원문 사실은행·합성 팀 역할을 사용했다.
실제 개인의 경력·운영 경험·성과는 확인한 것으로 처리하지 않는다.

- `luna-full-01`: 실제 모델 17회 후 3번 답변의 다음 Plan에서 Evidence UUID 오타가 semantic 검증에 걸려 중단됐다.
  올바른 basis ID가 함께 있더라도 잘못된 `evidence_refs`를 자동 보정하거나 저장하지 않았다.
- `sol-full-01`: 실제 모델 4회 후 L2가 원본 설정의 120초 한도에서 timeout되어 준비가 중단됐다.
  L1·파일 선정 성공과 L2 실패를 구분하며, 200 stream 응답의 미완료 상태를 분석 성공으로 세지 않았다.

두 회차의 DB·모델 입출력·호출 비용·원문·실패 상태는 그대로 보존했다.
새 v6와 L1 180초/L2 160초를 양 모델에 공통 적용한 `luna-full-02`·`sol-full-02`를 별도로 실행했다.
검증 중에는 프로세스 설정만 바꾸고 원본 환경 파일과 첫 회차의 설정·실패 기록은 보존했다.
재검증은 첫 회차와 조건이 다르므로 최초 비교의 실패를 없애거나 같은 조건의 승리로 바꾸지 않는다.

재검증의 목표는 새 L1→자체 파일 선정·실원문→새 L2→9턴 T3/Director→실제 report ARQ→profile outbox worker다.
모델별 새 DB·Redis·deployment, 총 60회 호출·2400초 상한과 동일한 후보 응답 정책을 적용한다.

### 실제 전체 연쇄 결과와 복구 경로

| 실행 | 실제 결과 | 분리해서 해석할 사항 |
| --- | --- | --- |
| `luna-full-02` | 자체 새 L1/L2와 7답변·7분석 저장 후 다음 질문의 독립 Review가 `replan`으로 반려 | 질문이 `identify`의 조건부 identity 갱신을 무조건으로 표현했다. 원문 기반 안전 반려이며 schema 오류와 다르다. |
| `sol-full-02` | 자체 새 L1/L2→9답변·9분석→6점수·리포트 저장 | burst 검증기가 report 완료 중 추가된 profile job을 다시 poll하지 않아 중단했다. 제품 report 생성 실패로 분류하지 않는다. |
| `sol-profile-continue-01` | 실제 만료 delivery 소비→공식 reaper 재전달→profile worker 성공 | 기존 9문답·리포트·점수·원 호출 행 전체 불변, outbox `succeeded`, 캐시 GET 추가 모델 0회. 새 모델 1회. |
| `luna-public-retry-01` | 공개 abandon→retry로 새 면접을 시작해 9답변·9분석 완료 | 원래 7문답은 보존하고 자기 유효 L1/L2를 재사용한 warm 복구다. 리포트 입력 복원 오류로 당시 report/profile은 생성되지 않았다. |
| `luna-report-retry-01` | 아래 제품 수정 후 같은 9문답에서 공개 report retry→report worker→profile worker 완료 | 원 실패 요청 불변·새 retry 요청 1개 성공·6점수·report/profile/outbox 저장·캐시 GET 2회의 추가 모델 0회. 새 모델 3회. |

두 최종 면접 모두 HR 1·기술 6·도메인 2의 9문답이며 마지막 답변까지 저장·분석한 뒤 종료됐다.
Luna의 단일 cold 실행 완주나 Sol의 최초 burst 실행 완주로 기록하지 않는다.
위 복구는 현재 공개 정책과 공식 큐 재전달 경로를 사용했고, 내부 질문 재생성 우회나 DB 상태 강제 변경은 없다.
각 실패의 `campaign-result.json`은 실패 상태 그대로 보존했다.

기본 연쇄 안에서도 실제 보완 조회가 발생했다.
Luna cold 2회차의 첫 답변은 `route.test.ts:1–925` 1개 원문을 조회했고, public retry의 8번 답변은
`getEventData.ts:1–150`·`getEventDataEvents.ts:1–157` 2개 원문을 조회했다.
GitHub blob·원문·좌표·wire 지문과 후속 T3/Plan/Review 입력의 동일 원문을 대조했다.
두 회차에서 바로 다음 질문이 새 source ID를 직접 인용한 것은 아니므로, 입력 반영과 직접 인용을 구분한다.
앞의 독립 자연 발생 Tool 사례에서는 두 모델 모두 새 코드 근거를 다음 질문에서 직접 참조했다.

### 실제 검증에서 발견한 리포트 복원 오류와 수정

[report history](../../backend/app/features/report/history.py)는 기존 Evidence와 L2 경로만으로
과거 T3의 `verification_requests`를 재검증해, 면접 당시 허용한 주변 후보 경로를 누락했다.
실제 실패 요청의 6경로는 모두 저장한 16개 후보와 고정 SHA에 포함됐지만 `verification scope`에서 거절됐다.
report 모델 호출 전의 제품 입력 구성 오류이며, 모델의 잘못된 출력으로 분류하지 않는다.

공통 `repository_candidates.STATE_KEY`·`snapshot_paths`를 재사용해 소유한 선택 레포의 같은 SHA 후보만 복원했다.
후보는 조회 권한으로만 사용하고 Evidence·Tool item·원문을 만들지 않는다.
프롬프트·ID·schema·semantic 검증과 저장된 분석·원응답은 유지했다.
새 독립 PostgreSQL DB에서 정상 후보 실패를 RED로 재현하고, 같은 SHA 정상·다른 SHA·손상 후보·미선택 레포·
snapshot 누락·다른 소유자의 6개 회귀를 GREEN으로 확인했다.
이어서 report/profile·AI facade·answer wire history 관련 **201개**가 단일 실행에서 통과했다.
Ruff·format 2파일과 mypy 1소스도 통과했다. 앞의 AI 840·BE 56과 겹치는 범위가 있어 수치를 합산하지 않는다.
실제 실패 DB에서는 read-only transaction으로 입력 구성 3단계를 다시 검증했고 모델 호출·DB 쓰기는 0회였다.

### 사용량·참고 비용과 비교의 범위

2026-11-09 KST 최종 감사는 이번 15개 campaign의 실제 HTTP 원응답·SSE usage·요청 지문을 대조했다.
이전 고정 입력 36회 비교는 포함하지 않는다. 같은 입력으로 실제 재호출한 요청은 중복으로 삭제하지 않았다.

| 실제 호출 모델 | 시도 | 확인된 사용량의 참고액 |
| --- | ---: | ---: |
| Luna | 110 | 732.585043원 |
| Sol | 47 | 5,975.973231원 + usage 미상 1건 |
| 합계 | 157 | **6,708.558274원 + 미상 비용** |

156회는 usage를 확인했고 초기 Sol L2 timeout 1회는 확인하지 못했다.
서비스 호출 129회의 참고액은 6,552.035143원, 검증용 합성 지원자 생성 28회는 156.523131원이다.
독립 task·Tool·실패·복구 비용까지 포함한 실험 합계이며 서비스 면접 1회의 평균 비용은 아니다.
2026-11-08 Elice에 표시된 100만 토큰당 원화 단가(Luna 입력141/캐시14/출력708,
Sol 입력2835/캐시141/출력14175)로 계산했다. 추론 토큰은 출력에 이미 포함돼 중복 가산하지 않았다.
실제 청구액·VAT·별도 캐시 쓰기 단가·비LLM API 비용은 이 계산으로 확정하지 않는다.
Luna의 안전 반려와 복구·자기 캐시 재사용, 모델별로 달라진 질문·출력을 고려해야 하므로
이 한 사례로 모델 품질의 동등성이나 운영 평균 지연·완주율을 확정하지 않는다.

### 로컬 Luna 활성화와 새 프로세스 검증

원본 환경 파일을 private 영역에 보존한 뒤 원본·검증 작업본의 `backend/.env`를 같은 설정으로 맞췄다.
`LLM_CONNECTION_SLOT=1`, Luna 연결, L1 180초·L2 160초를 적용하고 Sol slot 3·다른 공급자 설정은 보존했다.
기존 로컬 DB 주소 55432/devon_local과 Redis 56379를 유지했다.
이전에 연결할 DB가 없어 새 전용 PostgreSQL container·volume을 만들고 migration 0014까지 적용했다.
검증 면접을 이 서비스 DB로 복사하지 않았으며 초기 사용자 fixture는 0명이다.
이 개발 DB에 새 deployment `luna-local-v6-20261109`의 **11개 활성 task 프롬프트**를 등록했다.
개발 지식은 `unreviewed`로 보존하며 사람 승인으로 바꾸지 않았다.

새 작업본 소스로 Uvicorn 프로세스를 띄워 실제 HTTP health·OpenAPI·미로그인 `/api/me`의 401을 확인했다.
DB SELECT 1·migration·Redis PING, 설정과 11개 task/model/version의 정확한 일치 및 준비 시간 예산도 통과했다.
스모크 검사의 외부 공급자 호출·DB/Redis 쓰기는 0회이며 생성한 API 프로세스는 검사 후 종료했다.
실행 대상은 이 통합 작업본이며 원본 `develop`에 구현을 병합·게시한 상태를 뜻하지 않는다.

### 판정과 근거 산출물

실제 공급자·PostgreSQL·Redis·ARQ를 사용한 위 AI 기능 연쇄와 독립 task·Tool 경로는
명시한 입력·복구 경로·설정 범위에서 **자동 검증 완료**다.
이번 회차에서 STT·Vision·TTS 공급자를 새로 호출하거나 음성 9턴·실제 로그인·FE 브라우저 전체 흐름을 검사하지 않았다.
이미지 JD 독립 task는 이전 실제 공개 이미지에서 추출·보존한 블록을 사용했다.
이번 모델 비교의 주 레포는 고정 Umami 1개이며, 이 결과를 모든 언어·규모의 레포와 부하/SLO로 확대하지 않는다.
사람의 질문·평가 품질 검수, 기존 `r-0008.v3` reject, 운영 배포·원격 PR/CI 상태는 별도 범위다.

산출물은 작업본의 `.claude/scratch/full-validation/`에 보존했다.
전체 감사 `campaign-usage-audit-04.json/.md`, 독립 scope `privatefinal-scope-audit.json/.md`,
보완 회귀 `report-scope-fix-result.json`, 원인 재현 `luna-public-retry-report-readonly-diagnosis-{01,03}.json`,
각 campaign의 원입출력·usage·DB export, 활성화 `runtime-activation/{activation-result,smoke-result}.json`이 근거다.
공통 계약 검사는 기존 전용 venv를 재사용해 schema 2개·positive/negative fixture 7개·부분 OpenAPI가 통과했다.
backend venv에 해당 검사 패키지가 없어 첫 시도는 미실행(exit 2)이었으며 새 패키지는 설치하지 않았다.
초기 설계·testing 원본은 보존했고 구현 결과는 이 절로 통일했다. 커밋·push·PR은 수행하지 않았다.

<a id="jd-heading-fix-20261109"></a>

## 2026-11-09 JD 소제목 추출 오류와 기존 캐시 보완

병합된 [#15](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/15)의 추출 경로를 확인한 결과,
독립된 `필수 역량`, `주요 역할`이 요구사항으로 저장되고 20개 상한을 소모했다.
당시 리뷰에서 수정한 URL·에러·카테고리 문제와 별개로 발견한 후속 오류다.
최신 develop `18f4105b2e7e9885df118d283badbf59692ec5b4`에서 별도 로컬 브랜치
`fix/jd-requirement-headings`로 수정했다. 기존 AI 통합 작업과 보존된 실행 결과는 옮기거나 덮어쓰지 않았다.

### 변경과 저장 경계

- [`build_requirement_drafts`](../../backend/app/llm_tasks/jd_extract.py)는 공통 판별기
  `is_requirement_heading`으로 알려진 한국어 제목만 개수 배분 전에 제외한다.
  목록·강조·번호·괄호·콜론 장식은 비교용 사본에서 처리한다. 실제 요구 문장과 그룹·순서·태그는 유지한다.
  제목만 남으면 기존 `jd_extraction_failed` 오류를 반환하며 모델을 호출하지 않는다.
- [`fetch_posting`·`complete_posting`](../../backend/app/features/analysis/posting_service.py)은
  `_reusable_success`에서 저장된 제목 행을 확인한다. 해당 캐시만 원문을 재수집하고 URL 잠금 안에서
  다시 확인한다. 정상 캐시는 기존 ID를 HTTP 없이 재사용한다.
- 정제된 요구사항은 기존 버전 저장 경로로 새 공고·요구사항 ID에 저장한다. 과거 원문·요구행과
  분석 실행·면접·턴의 참조 ID는 그대로 둔다. 실패·동시 갱신의 기존 보존 경계를 유지한다.
  공개 계약·스키마·마이그레이션 변경은 없다.
- 정책과 대안은 [BE 결정 0013](../backend/decisions/0013-jd-requirement-headings-and-cache-repair.md)에 기록했다.
  초기 설계·testing 문서와 이전 ADR은 수정하지 않았다.

### 이번 실행 결과

| 확인 범위 | 결과와 한계 |
| --- | --- |
| 추출기 신규 회귀 | 수정 전 27개 중 18 실패·9 통과. 수정 후 관련 추출·Wanted 검사에 포함해 통과 |
| 추출·Wanted 관련 검사 | 88 passed. 소제목·장식·실질 문장 보존·분류·순서·태그·20개 배분·오류 경계 |
| 캐시 신규 회귀 | 수정 전 7 실패·1 통과, 수정 후 8 통과 |
| PostgreSQL 공고 관련 검사 | 6개 파일 55 passed, 실패·skip 없음. 신규 8개를 포함하므로 별도 합산하지 않음 |
| 보존된 실제 공고 독립 검사 | Wanted 361487의 원문 22문단에서 제목 2개만 제외. 실질 문장 20개 전부와 required 7·preferred 6·responsibility 7의 원래 분류·순서·태그를 확인. 원문 불변을 포함한 9개 검사 통과 |
| 정적 검사 | 변경 Python 파일의 Ruff·format과 제품 코드 mypy 통과. `git diff --check` 통과 |
| 게시 전 AI 전체 게이트 | 새 실행에서 557 passed. 전체 Ruff·format 76파일·mypy 18소스 통과 |
| 게시 전 부분 계약 검사 | 2스키마·부분 OpenAPI·7 fixture 통과. 전체 API 런타임 호환 검증은 아님 |

DB 검사는 별도 로컬 PostgreSQL 테스트 DB `task11_test_jd_heading_cache_20261109_test`에서 실행했다.
Wanted HTTP는 모의 응답을 사용했고 기존·운영 DB는 수정하지 않았다.
실제 공고 검사는 과거에 수집해 보관한 입력을 다시 읽은 것으로 이번 실시간 수집 검증은 아니다.
실제 공고 원문과 임시 검사 로그는 Git 제외 로컬 scratch에 두었다.
88개·55개·독립 검사 9개는 서로 다른 범위이며 서비스 전체 테스트 수로 합산하지 않는다.

### 남은 검증과 적용 범위

이번 실행에는 외부 모델·유료 API 호출, 배포, 브라우저 E2E가 없다. 서비스 모델·추론 강도·환경 파일은 변경하지 않았다.
등록한 한국어 제목과 장식 범위의 수정이며 모든 언어·사이트·임의 제목을 의미 분석하는 기능은 아니다.
이미 ID가 고정된 면접은 옛 자료를 계속 참조하고 새 조회부터 정제 버전을 사용한다.
새 공고와 면접을 연결한 실제 모델 재검증·배포는 별도다. 기존 PR 리뷰 게시는 이 로컬 수정의 배포를 뜻하지 않는다.

사용자의 후속 PR 게시·조건부 병합 요청에 따라 원본 브랜치를 보존하고 최신 develop 기반
`fix/jd-heading-cache-repair` 게시용 브랜치에 이번 변경만 분리한다. 게시 후 CI와 병합 결과는
해당 후속 PR의 실행·검증 기록에서 확인한다. 기존 통합본과 미병합 선행 코드는 포함하지 않는다.

## 2026-11-09 — 실제 계정의 로컬 이용 환경과 최소 진단

사용자가 서비스만 이용하고 실행·확인은 에이전트가 맡도록 별도 로컬 worktree
`work/manual-ai-service-20261109`를 구성했다. 기존 전체 작업의 원본 1,127파일은
SHA256 비교에서 변경 0이며, 원본 HEAD/작업 파일을 덮어쓰지 않았다.
통합 환경은 기존 전체 구현과 develop `31a18d28`을 결합한 로컬 실행본이다.
커밋·push·PR 게시를 수행한 변경은 아니다.

### 실행과 진단

- 같은 소스의 API·`analysis_app.WorkerSettings` 단일 worker·MSW 비활성 FE를 실행했다.
  로컬 PostgreSQL/Redis와 기존 프롬프트·루브릭·도메인 프레임·TTS 예산 원장을 재사용했다.
- 활성 프롬프트 11개는 task 목록·본문이 현재 소스와 일치하고 모델은 모두 `gpt-6-luna`다.
  비활성 v1 프롬프트의 upstream 본문을 기존 활성 버전에 덮어쓰지 않았다.
- `backend/app/core/logging.py`에 API/worker 공통 안전 예외 출력과 HTTP 결과 관측을 연결했다.
  예외는 종류·파일/함수/줄만, HTTP는 고정 라우트·메서드·상태·시간·request ID만 기록한다.
  `LOG_JSON`은 config/main/worker startup에 연결했다.
- Git 제외 `manual-ai-runtime-20261109/supervisor.py`가 소유 프로세스·health·worker heartbeat와
  시작 후 업무 상태를 약 5초마다 확인한다. 업무 DB 관측은 읽기 전용이다.
  자식 stdout도 허용된 필드·enum·UUID만 별도 JSONL로 저장한다.
- 같은 위치의 `vite.manual.config.mjs`는 원본 Vite 설정·프록시를 재사용하고
  localhost:5173의 dev 실행에만 HTTP/JS 진단 스크립트를 주입한다.
  원래 fetch Promise/응답/오류는 유지하고, 메타데이터는 exact Origin·loopback·8KiB 상한으로 검증한다.
  동적 경로는 템플릿으로 바꾸며 사건별 기록과 중복 억제한 alert를 구분한다.
  진단 로그 상한은 32MiB다. 원격 브라우저 진단 포트를 사용하지 않는다.
- 브라우저 자동 실행 명령은 도구의 자동 정책에서 차단됐다. 사용자에게 로컬 로그인 링크를 안내했다.
  실제 로그인·OAuth 동의·마이크 허용은 사용자가 직접 수행한다.

### 최신 변경 통합과 평가 자료 보존

#197의 JD 참조 검증은 기존 v2 보고서/채점 타입·Narrative·evaluation_keys를 유지한 채 결합했다.
#175 canonical 19쌍과 검수 상태는 최신 develop을 유지했다.
과거 코호트가 참조하는 58JSON+사실표는 동결 snapshot으로 보존하고 출처 resolver를 분리했다.
이 snapshot은 현재 승인된 평가자료로 직접 로드할 수 없으며, 과거 코호트의 지문을
새 자료에 맞춰 변경하거나 과거 검수 상태를 현재 품질 승인으로 승격하지 않았다.

### 이번 검증과 범위

| 범위 | 이번 실행 결과 |
| --- | --- |
| AI 전체 | 864 passed, Ruff/format 124파일·mypy 29소스 통과 |
| BE AI import·평가 연결/출처 | 35 passed |
| 안전 로그·HTTP 결과·기존 관련 회귀 | 최종 53 passed, 관련 Ruff/format/mypy 통과 |
| JD 추출 순수 회귀 | 42 passed, 실제 DB·Wanted·모델 호출 없음 |
| supervisor 개인정보·정리 경계 | 최종 9 passed, 모의 프로세스·임시 파일·라우트 prefix 검증 |
| 로컬 화면 진단 | 10개 mock 회귀·문법·원본 Vite config 로드 통과 |
| FE | TypeScript 검사와 실제 API 설정의 production build 통과 |
| 실행 확인 | API/proxy health 200, 로그인 HTML 200, 인증 전 profile 401(정상), worker heartbeat·큐 정상 |
| 진단 실제 저장 | 스크립트 주입/JS 제공 확인, 실제 health의 request ID 메타데이터 POST 204 및 JSONL 저장 확인 |
| 기존 원본 보존 | 원본 1,127파일 변경 0, 과거 코호트 입력/기대 82파일과 기존 지문 보존 |

범위가 겹치는 검사 수를 전체 서비스 테스트 수로 합산하지 않는다.
이번 준비 과정에서 공급자 호출은 0이며 설정 유효성과 기존 DB의 일치를 확인했다.
실제 사용자 계정의 전체 이용, 브라우저 DOM/클라이언트 스크립트 실행은 사용자 테스트 전까지 미실행이다.
기동 중 일시적인 health 실패와 사전 확인 중 Windows 연결 reset 기록은 보존했고,
최종 실행의 health 정상과 구분한다. 이를 실제 면접 성공으로 해석하지 않는다.

현재 실행 상태·PID·준비 검증은 Git 제외 runtime의 `status.json`·`services.json`·`readiness.json`,
검사 근거는 `agent-A/`·통합본의 `.claude/scratch/logging-verification/`·runtime의 TAP에 있다.
운영 확인 순서는 runtime의 `OPERATIONS.md`에 둔다. 수집기가 계속 실행돼도 대화 에이전트가
턴 종료 후 상주하며 자동 판단·수정하는 것은 아니다. 의미상 질문 오류는 사용자 관찰과 업무 원본을 검토한다.
관련 결정은 [0042](decisions/0042-local-user-test-observability.md)에 기록한다.

실제 FastAPI `include_router`가 `scope.route.path`에 prefix 전 고정 template을 보관하는 것도
mock DB/API 없이 실제 ASGI 앱으로 재현했다. supervisor 소비 계층에서 알려진 router의 고정
template에 `/api`를 복원하고 공식 Reason enum 값만 수용하도록 보완했다.
서비스 기능은 변경하지 않았으며, 현재 진행 작업·큐가 없는 상태에서 수집기를 재시작했다.
최종 준비 검사에서 실제 401 요청의 canonical route·상태·request ID가 함께 저장되는 것도 확인했다.

## 2026-11-09 — 저장 답변 보존과 다음 질문의 자동 복구

실제 계정 면접에서 네 답변을 저장한 뒤 5번 후보가 독립 Review에서 반려됐다.
질문에는 원인·재발 방지·검증을 물었지만 QuestionContract에는 불일치의 회복까지 요구했다.
원 실패를 보존하고, 사용자가 요청한 자동 재생성과 같은 면접 이어가기를 별도 로컬 worktree
`work/manual-ai-recovery-20261109`에 구현했다. 원 실행본과 기존 전체 작업본은 보존한다.
정책·공개 계약의 후속 결정은 [공통 0012](../shared/decisions/0012-bounded-question-recovery.md)에 둔다.

### 변경 경계

- `director_service.process_answer`는 안전한 `director_candidate_rewrite` 반려에 자동 1라운드를
  허용한다. 최초·자동·명시 수동을 합쳐 대상 질문당 Plan/Review 최대 6회다.
  독립 Review와 원문·허용 ID·질문 계약 검증을 생략하지 않는다.
- `question_retry.py`는 기존 `context_state`의 유한 원장으로 요청 UUID·대상 턴·소유권·실패 호출·
  기한·결과를 연결한다. PostgreSQL row lock, 입력 지문, 늦은 결과 폐기, 동일 요청 재생과
  새 realtime 세션 발급을 처리한다. STT·답변 분석·레포 분석은 재실행하지 않는다.
- Director v7은 v6 원문을 보존한 후속 프롬프트다. 검증된 이전 후보와 반려 사유는 새 Plan에만
  참고자료로 주며 새 독립 Review·원문 사실·허용 근거에는 섞지 않는다.
- `POST /api/interviews/{id}/question/retry`와 GET의 선택 필드 `canRetryQuestion`·
  `questionRetryCount`를 추가했다. FE는 저장된 답변으로 이어가기, 요청 중 중복 행동 차단,
  응답을 확인하지 못했을 때 같은 UUID로 결과 확인, 새 세션 재접속을 제공한다.
- 신규 업무 테이블·마이그레이션은 없다. 기존 질문/답변/분석/근거/선택 SHA와 실패 기록을
  보존한다. 정상 진행에 필요한 직전 턴의 decision·현재 턴·context 갱신은 허용한다.

### 자동 검증과 한계

AI 전체 896개, BE 기존 면접·WebSocket·REST·음성·계약 관련 182개가 통과했다.
BE 복구 전용 최종 검사는 PostgreSQL·Redis에서 23개 전부 통과했다. 질문 commit 직후 같은
요청이 재전송되는 두 경로는 수정 전 2개 실패를 재현하고 수정 후 통과했다.
기존 182개는 마지막 동시성 두 경계 보완 전의 검사이며 최종 23개와 구분한다.
FE는 새 복구 시나리오 8개를 포함한 모의 API 브라우저 회귀 52개와 타입·빌드가 통과했다.
이후 오류 문구와 주석만 정리한 변경은 관련 브라우저 18개와 포맷 검사를 다시 통과했다.
BE 전체 mypy는 219소스 통과, AI Ruff/format 125파일·mypy 29소스가 통과했다.
공통 계약의 2스키마·7 fixture·부분 OpenAPI 검사도 통과했다.
서로 겹치는 검사 수를 서비스 전체 테스트 수로 합산하지 않는다.

DB 회귀는 별도 PostgreSQL 테스트 DB와 별도 Redis DB15에서 수행한다.
모델·HTTP 응답은 모의 입력이며 이 구현 검증에서 유료 공급자를 호출하지 않았다.
실제 사용자 면접의 네 문답·T3·기존 근거·선택 레포 분석·원 실패 기록은 읽기 전용 해시로
적용 전후 비교한다. 실제 Luna 복구·음성 면접 완주와 사람의 질문 품질 검수는 이 자동 검사와
구분한다. 초기 설계·testing 원본은 수정하지 않았으며 커밋·push·PR은 수행하지 않았다.

### 로컬 적용 확인

처리 중 큐가 없는 상태에서 소유 API·worker·Vite만 종료하고 복구 실행본으로 전환했다.
활성 프롬프트는 Director만 `director_v7@luna-question-recovery-20261109`로 등록했다.
기존 Director v6와 다른 10개 활성 task 프롬프트는 보존했으며 기본 모델은 Luna다.
기동 후 API/proxy health 200, worker heartbeat, 실제 API의 retry POST 등록,
진단 주입·204 저장과 원본 전체 작업본 1,127파일·이전 실행본 1,173파일 불변을 확인했다.
업무 DB의 기존 네 문답·T3·근거·선택 레포 분석·원 실패 기록도 적용 전후 해시가 일치했다.
기존 실패의 저장된 Plan/Review는 새 코드에서 안전 rewrite 피드백으로 복원되며,
읽기 전용 검사에서 현재 면접의 `canRetryQuestion=true`·수동 횟수 0을 확인했다.
이 시점에는 실제 Luna 재생성과 사용자 화면의 이어가기 클릭은 아직 수행하지 않았다.

이후 사용자가 이어가기를 실행해 같은 면접의 5번 질문이 생성됐다. 실제 Luna의 신규 Plan 1회와
독립 Review 1회가 성공했고, Review의 plan/context/wording/contract 검사가 모두 true다.
이번 경로는 원장의 manual 1회 성공이며, 새 자동 복구 경로를 실모델로 실행한 사례는 아니다.
질문에는 불일치의 복구·재발 방지·검증을 모두 명시하고 실제 트랜잭션 경계·장애 여부는
확인되지 않은 가정으로 구분했다. 생성 후에도 기존 네 문답·T3·근거·선택 레포 분석·원 실패
기록의 해시가 모두 보존됐다. 읽기 전용 근거는 runtime의 `actual-question5-recovery.json`과
`preserved-interview-after_question.json`이다. 당시 5번은 답변 대기 중이며 9턴 완주 증거는 아니다.

### 실제 계정 음성 면접의 9턴 종료와 리포트 확인

같은 면접에서 9개 답변과 각 답변의 분석을 저장하고, 마지막 `next_step=finish`와
`completed/current_turn=9`를 확인했다. 10번 질문은 없으며 배분은 HR 1·기술 6·도메인 2다.
최초 5번 실패와 명시 이어가기 성공을 포함한 완주로, 무장애 완주나 새 자동 복구의 실모델
실행으로 해석하지 않는다. 종료 후에도 기존 네 문답·T3·근거·선택 레포 분석·원 실패 기록의
해시가 모두 일치했다.

리포트 화면의 GET은 생성 중 202 응답 21회 뒤 200 응답 1회였고, 서버와 클라이언트의 마지막
request ID도 일치했다. 최초 조회에서 완료 응답까지 약 64초이며 이 경로의 4xx·5xx는 없다.
생성 요청은 initial 1건 succeeded/error_code=null이고 실제 Luna의 `report_score`·`report`
호출 결과도 성공이다. 점수 6개·페르소나 피드백 3개·리비전 1개와 원본 snapshot의 일치를
확인했다. 저장 총점과 실제 응답 재구성값은 모두 66점이다.
프로필 갱신 outbox도 revision 1에서 succeeded이며 Luna 모델·프롬프트·입력 지문·역할 요약이
보존됐다. 역할 요약은 설계 제안과 실제 기여를 구분하고 본인의 구현 주장은 진술로 표시한다.

실행 성공과 별도로 다음 품질 문제를 남긴다.

- 사용자 확인상 말하지 않은 1번의 뉴스 문구가 STT 전사에 포함됐고 리포트가 무관한 마지막
  문구를 전달력 부족으로 지적했다. 전사 오류가 평가 근거에 섞인 문제다. 해당 문구가 수치
  점수에 끼친 영향은 아직 분리 검증하지 않았다. 원 음성 미보존으로 발생 원인도 미확정이다.
- `POST`·`EventService` 발음과 5번 쉼표 경계의 이어 읽기는 사용자 관찰로 기록했다.
  현재 합성은 원문 `input.text`이며 음성 전용 발음·쉼 보완은 적용하지 않았다.
- 준비 완료 후에도 준비 제목의 spinner가 남는 FE 표시 오류는 아직 수정하지 않았다.
- 3번 충분성의 단계별 구체화 요구와 8번 피드백의 실행 가능한 Python 표현 요구는 질문 계약
  밖의 감점인지 추가 연습 조언인지 구분해 재검토할 후보이며 확정 품질 오류와 구분한다.
- JD coverage는 20개 중 명시 연결 2개다. 역량 충족률이나 합격률이 아니며 직무 항목을
  넓게 다룬 면접이라고 해석하지 않는다.
- Windows proactor의 간헐적 ConnectionResetError는 보존했고 원인·이용 영향은 미확정이다.
  최종 API/proxy health·worker·queue 정상 및 리포트 조회 오류 없음과 구분한다.

이번 사후 감사는 DB read-only와 기존 진단 기록을 사용했으며 공급자 추가 호출·업무 기록
수정·리포트 재생성을 하지 않았다. 원문 전사와 리포트는 그대로 보존했다.
근거는 runtime의 `completed-practice-audit.json`·`preserved-interview-after_completion.json` 및
서비스/클라이언트 메타데이터이며 화면 DOM·원 음성 청취나 사람의 품질 승인을 대체하지 않는다.


## 2026-11-09 — 후속 변경 게시 검증

- 실행 중인 manual/recovery 원본, 기존 PR #212~#219, 실제 면접 기록을 보존했다.
- develop `31a18d2`에서 별도 게시 브랜치를 만들고 후속 신규 변경만 분리한다.
- 손상된 미게시 v7은 로컬 원본·지문으로 보존하고 정상 UTF-8 v8을 게시한다. 저장된 v7의 호환은 유지한다.
- 과거 평가 snapshot은 원본 바이트를 유지하고 디렉터리별 Git 속성을 적용했다. 실제 commit·checkout 왕복을 검증했다.
- 현재 canonical 평가 사례는 develop 기준을 유지한다. 과거 snapshot은 출처 연결용이며 현재 정답 데이터가 아니다.
- 새 통합본 AI 전체 테스트는 912개 통과, 실패·건너뜀 0개다. v8의 실제 공급자 실행은 하지 않았다.
- 분리 게시본의 단독 검사와 통합 검증은 구분한다. 과거 실제 9턴의 수동 이어가기 성공을 새 자동 복구 실행으로 보고하지 않는다.
- 선행 #215 통합 시 최신 develop의 canonical 사례를 유지해야 한다. 이전 브랜치의 과거 canonical 자료로 되돌리지 않는다.
- 기존 게시 수리 기록을 보존하고 미게시 Director ADR을 0043으로 정리했다. 문자·바이트 보존 결정은 ADR 0044를 따른다.
- 리포트 문장·요구사항 표시, 연동 관리, TTS 발음, STT 무발화 문구 대응은 후속 작업이다.

### 최종 게시 전 자동 검증

- 새 통합본에서 AI 전체 912개, BE 고유 216개, FE 면접 브라우저 75개 자동 검증을 완료했다.
- BE는 본체 186개와 설정 30개를 환경별로 나눴고 최초 216개와 최종 사례 집합이 정확히 같다. 별도 재검증한 부분 집합을 중복 합산하지 않았다.
- 최초 BE 213통과·3실패 기록을 보존했다. v8 기대값 1줄을 수정하고, 설정 검사에서 검증용 DB 환경 주입을 분리했다. 동시성 검사는 기존 조건·5초 제한 그대로 재통과했다.
- 전체 BE Ruff·format 및 app+scripts mypy 236소스, FE lint·build를 통과했다. AI 정적 검증은 위 기록과 같다.
- 게시 범위 159개 원본 경로를 직접 변경과 37개 후속 패치로 재생해 새 통합본 전체와 일치함을 확인했다. 적용 안내를 포함한 게시 파일은 175개다.
- 단독 게시본의 AST·수집·타입 검사 결과는 통합본 실행 결과와 구분한다. 필요한 선행 import가 없는 실패와 검사 환경 미준비도 PR 본문에 기록한다.
- 후속 패치는 자동 활성화되지 않는다. 선행 구현 반영, 지문 확인, 실제 코드 적용과 통합·CI 재검증 전까지 Draft를 유지한다.


<a id="review-followups-20261109"></a>
## 2026-11-09 PR 리뷰 후속 수정

- 대상: #212, #213, #216, #217, #218의 인라인 44개와 일반 리뷰. [결정 0045](decisions/0045-review-runtime-activation-and-source-recovery.md)에 실행·게시 경계를 기록했다.
- 구현: 설치된 소비자 검사 후 프롬프트 활성화, 구형 계약 기본값 호환, 작업별 ARQ 제한, 선택 개발 설정, 검색 실행 정책·질의 정규화, TTS 정산 장애·취소 마무리, L1 파일 크기 사전 검사, Claim 실행 만료·좌표 복원, PDF native 우선, 이미지 실패 캐시, 자소서 단독 처리, 도메인 판정 실패 구분, 리포트 읽기 잠금·영속 종료·연결 JD 의미 보존.
- 기존 원문·면접·요구사항 ID와 과거 계약 복원을 자동 수정하지 않는다. 기존 서비스 작업본·비밀 설정은 보존했다. 실제 외부 공급자를 추가 호출하지 않고 전용 PostgreSQL·Redis와 HTTP 대역으로 회귀 검증했다.
- 게시 시 통합 구현과 선행 미병합으로 비활성인 후속 패치를 구분한다. OpenAPI와 대응 REST 문서, outbox 생산자와 소비자의 부분 활성화를 피하고 후속 패치의 적용 전·후 지문도 재확인한다.
- 수치·명령·통과/실패/미실행과 커밋 근거는 각 원래 리뷰 스레드 및 종합 리뷰에 기록한다. 과거 실측·기존 테스트 수치를 이번 수정의 신규 결과로 재사용하지 않는다.
