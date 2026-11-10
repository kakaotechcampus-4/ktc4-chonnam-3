# TTS 운영 진단

현재 운영 API 이미지에서 TTS 설정·Google 음성 목록·Redis 예산을 읽는다.
앱 이미지 빌드, 서버 checkout, 서비스 재시작, 음성 합성, 예산 초기화는 하지 않는다.
전체 배포 개선 작업과 독립적으로 도입할 수 있다.

화면의 `질문 음성을 재생하지 못해 텍스트로 보여드려요`는 음성 주소 없음·서버 요청 실패·
브라우저 재생 실패가 공유하는 안내다. 텍스트 표시를 켜 둔 상태에서는 이 안내가 가려질 수 있다.
텍스트 토글이 실패의 원인이라는 의미는 아니다.

## 등록과 실행

1. 이 변경을 기본 브랜치 `develop`에 반영한다. PR에서는 표준 라이브러리 모의 검사만 실행한다.
2. GitHub Actions의 `Diagnose TTS on EC2`에서 `Run workflow`를 선택하고 `develop`을 지정한다.
3. 실행 결과의 `diagnostic.report.checks`와 `diagnostic.completion`을 확인한다.

GitHub 설정·진단 파일만 바뀐 push는 앱을 자동 배포하지 않는다. 기존 수동 배포는 유지하며,
`backend`, `ai`, `frontend`, `ops`, Compose 또는 Docker 파일이 함께 바뀌면 자동 배포한다.
배포 워크플로만 수정한 경우에도 이미지 자동 재배포는 생략되므로 필요한 실제 배포는 수동 실행한다.

이 워크플로는 기존 AWS 역할을 사용한다. OIDC가 이 저장소·`develop`의 실행을 허용해야 하며,
SSM SendCommand/GetCommandInvocation과 중단 처리용 CancelCommand 권한을 확인한다.
저장소 쓰기 권한이 있는 실행자가 수동 실행한다. 역할 신뢰 설정을 임의로 확대하지 않는다.

## 확인 범위

- 실행 중인 API 컨테이너가 정확히 하나인지 확인한다. 검사 전후 ID·이미지·시작 시각이
  달라지면 성공으로 처리하지 않는다.
- runner의 검토한 probe를 stdin으로 전달한다. 새 API 모듈 설치가 필요하지 않다.
- 공급자·인증 선택·세 페르소나 목소리·사용량 설정을 검사한다.
- Google의 한국어 음성 목록 GET 1회로 접근과 목소리 지원을 확인한다. 음성 생성 요청은 0회다.
- API 환경이 가리키는 Redis에서 현재 UTC 월·프로젝트의 장부와 실행 식별자·잔여량을 읽는다.
- 키·토큰·연결 주소·프로젝트 식별자·질문·답변·응답 원문을 Actions에 출력하지 않는다.

프로브 전체 30초, 원격 명령 60초, SSM 실행 75초의 제한을 둔다. 조회·취소 실패를 정상으로
처리하지 않는다. 실패 후 원문 예외를 붙이거나 완료 여부를 추정하지 않는다.

## 결과에 따른 복구

| 코드 | 의미와 다음 조치 |
| --- | --- |
| `provider_not_configured` | 실제 API에 TTS 공급자가 설정되지 않았다. 서버 설정과 API 반영 상태를 확인한다. |
| `credentials_missing` | Google 인증정보가 없다. 검수한 운영 인증 설정을 준비한다. |
| `static_access_token_requires_refresh` | 토큰이 API key보다 우선한다. 실제 만료·갱신 방식과 목록 조회 결과를 확인한다. |
| `invalid_voice_mapping` / `unsupported_free_voice` | 세 persona와 한국어 Chirp3 HD 매핑을 기존 결정에 맞춘다. |
| `catalog_access_denied` | 표시된 HTTP 상태와 허용된 Google 사유로 API 사용 설정·권한·인증을 확인한다. |
| `voice_unavailable` | 운영에 설정한 목소리가 Google의 한국어 목록과 맞지 않는다. |
| `redis_unavailable` | 실행 중 API가 사용하는 Redis 연결을 확인한다. 장부를 삭제하지 않는다. |
| `budget_unconfigured` | Google 프로젝트와 월 상한 설정을 확인한다. |
| `budget_uninitialized` / `budget_epoch_changed` | 실제 Cloud 잔여량과 진행 중 요청 부재를 확인한 뒤 기존 예산 관리 절차로 조정한다. |
| `budget_exhausted` | 확인된 사용 가능량이 소진됐다. 임의의 새 한도를 지급하지 않는다. |
| `api_container_unavailable` / `runtime_changed_during_check` | 컨테이너 상태나 동시 배포를 확인한 뒤 안정된 시점에 다시 진단한다. |

운영 설정 변경과 예산 조정은 이 진단에 포함하지 않는다. 실패 원인을 확인한 뒤 해당 변경만
검토해서 수행한다. 이미 사용한 문자·진행 중 예약·과금 불명확 이력을 보존한다.

## 성공의 의미

모두 ready여도 실제 질문의 음성 합성·재생 성공은 아직 검증하지 않은 상태다. 음성 목록
접근 성공이 합성 권한·잔여 할당량·브라우저 자동 재생까지 증명하지는 않는다. 장부 잔여량도
실제 질문의 문자 수와 비교해야 한다. Google 실제 사용량과 이 장부는 서로 다른 관찰값이다.

진단 후 실제 음성 질문 요청의 결과와 재생을 확인한다. 합성 요청이 실패하는지, 정상 음성을
받고 브라우저가 재생을 거절하는지를 구분한 뒤 TTS 복구 완료로 판단한다.

## 사용자가 지정한 허용량의 최초 등록

`Initialize TTS allowance on EC2`는 현재 월의 장부가 완전히 비어 있을 때만 사용하는 수동 작업이다.
`develop`을 선택하고 문자 수·현재 UTC 연월·`APPLY_OPERATOR_ALLOWANCE`를 명시한다.
기본 문자 수는 제공하지 않으며 PR 검증과 병합만으로 운영 장부가 바뀌지 않는다.

이 경로는 사용자가 지정한 앱 허용량을 등록한다. Google이 확인한 실제 무료 잔여량을 의미하지 않는다.
장부에 `allowanceSource=user_requested_amount`, `cloudUsageVerified=false`와 입력값·시각·실행 식별자를
함께 기록한다. 공급자 확인 없이 `cloud_usage_confirmed` 근거를 사용하지 않는다.

- 배포 작업과 같은 GitHub 실행 잠금을 사용한다. API 이미지는 교체하지 않는다.
- 현재 API의 설정·Redis·프로젝트를 사용하며, 공급자 timeout+5초 동안 빈 장부와 Redis 상태를 확인한다.
- Redis WATCH와 단일 Lua 실행으로 다른 초기화와의 충돌·월 전환을 차단한다.
- 기존 `initialize_budget`의 계산을 재사용한다. 일부 필드라도 있으면 덮어쓰지 않고 중단한다.
- 명령 종료가 불명확하면 자동 재시도하지 않는다. 적용 여부가 불명확하다는 상태를 별도로 남긴다.
- 등록 후 읽기 진단과 짧은 실제 합성 한 번을 수행한다. 테스트 문자도 같은 장부에서 예약·정산한다.
- 합성 성공은 브라우저 재생 성공까지 증명하지 않는다. 실제 질문 재생을 추가 확인한다.

이미 초기화된 장부의 상한을 올리거나 Redis 교체 후 자동으로 새 허용량을 지급하는 용도로 사용하지 않는다.
