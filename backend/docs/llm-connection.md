# LLM 환경 설정과 연결 점검

모든 명령은 `backend/`에서 실행한다. `get_settings()`가 `.env`를 읽고 프로세스 동안
캐시하므로 변경 후 API·worker를 재시작한다. Docker에서 환경변수를 주입했다면 컨테이너를
재생성해 새 값을 적용한다. 프로세스 환경변수가 같은 이름의 `.env` 값보다 우선한다.

## 연결 설정

- OpenAI 직접 연결: `OPENAI_API_KEY`를 사용하며 공식 `/v1/responses`로 요청한다.
- Responses 호환 프록시: `PROXY_TOKEN`과 `CHAT_PROXY_URL`을 함께 설정한다.
  두 값이 있으면 프록시를 선택하며, 하나만 있으면 LLM 호출 전에 설정 오류로 처리한다.
  `OPENAI_API_KEY`가 함께 있어도 프록시에는 `PROXY_TOKEN`을 보낸다.
- `CHAT_PROXY_URL`은 `/responses`를 제외한 HTTPS 기본 주소다. `/tenant/v1` 같은
  경로는 유지하고 끝의 `/`만 정리한다. userinfo·query·fragment는 허용하지 않는다.
- `OPENAI_MODEL`이 있으면 점검·프롬프트 등록의 기본 모델로 사용한다. 없으면
  `LLM_DEFAULT_MODEL`을 사용한다. 팀 기본 모델 결정은 그대로 유지한다.

다음 네 실행 상한은 직접 연결과 프록시 모두 필수다. 비어 있으면 health 등 일반 앱 기동은
허용하지만 LLM 호출 설정 검증은 실패한다. 예시는 합성 저장소 **1건 점검용**이며,
여러 저장소 배치나 면접용 확정 예산은 입력·출력 크기를 측정해서 정한다.

```dotenv
LLM_TIMEOUT_SECONDS=30
LLM_MAX_OUTPUT_TOKENS=1024
LLM_MAX_INPUT_BYTES=32768
LLM_MAX_RESPONSE_BYTES=131072
```

시간은 provider 시도 1회당 초, 크기는 HTTP 본문 byte다. 기존 총 2회 시도 상한과
semantic 실패 재호출 금지 정책을 유지한다. 실제 키·프록시 주소를 커밋하지 않는다.

## 실제 연결 점검

```text
uv run --locked python -m scripts.check_llm
```

현재 `.env` → `Settings.require_llm()` → BE L1 → AI L1 → 공통 Responses 호출을 실행한다.
임시 요청 주소 변경이나 가짜 공급자를 사용하지 않는다. 합성 Python CLI 저장소 1건만
전송하며 API 사용량이 발생한다. 결과는 성공 여부·모델·사용량·지연·오류 분류만 출력한다.
성공 종료 코드는 0, 실패는 1이다. 설정·설치 예외의 상세값은 비밀 노출 방지를 위해 숨긴다.

진단용 prompt version `l1_connection_check`는 DB에 등록하지 않으며 분석 결과도 저장하지
않는다. 이 점검의 성공은 운영 프롬프트 품질이나 API·worker·DB 전체 실행 성공을 뜻하지 않는다.

## 앱에서 사용할 프롬프트 등록

실제 모델은 DB에서 읽은 `PromptSpec.model`을 사용한다. 환경 모델을 변경해도 기존 DB의
모델을 덮어쓰지 않는다. L1 캐시는 prompt version으로 구분되므로 모델·본문을 바꾸면
새 version을 등록한다. 기존 version에 다른 모델·본문을 덮어쓰면 충돌로 거절한다.

검수된 UTF-8 본문 파일과 격리된 로컬 DB를 준비한 뒤 실행한다. `DATABASE_URL`의 DB에
실제로 쓰며, 지정한 task의 활성 version을 바꾸므로 적용 대상을 먼저 확인한다.

```text
uv run --locked python -m scripts.register_prompt --task repo_shallow --version l1_proxy_local_v1 --template path/to/reviewed-prompt.md
```

등록 모델은 현재 `require_llm().llm_default_model`이다. 단일 transaction으로 등록과 활성
전환을 수행하며 실패하면 되돌린다. 다른 task는 유지한다. version은 DB 컬럼 한도인 20자
이내로 지정한다. 검수된 본문 없이 진단용 프롬프트를 운영 프롬프트로 대신 등록하지 않는다.
기존 고정 일곱 v1 초기 seed는 유지하며 새 명령은 준비된 특정 task/version만 등록한다.

앱의 활성 프롬프트 조회·캐시·결과 저장은 해당 service가 담당한다. L1 pipeline·API/worker
연결(#80·#108), Director service 연결(#82)은 각 PR의 통합 상태를 따로 확인한다.
실제 검증 결과와 미완료 범위는 [BE 구현 기록](../../spec/backend/implementation.md)을 따른다.
