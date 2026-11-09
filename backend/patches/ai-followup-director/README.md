# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `0a6431ee6f3e-runtime-prompts.json.patch` | `ai/prompts/runtime-prompts.json` | `1ea9e9552f26ccdeee5304750830edc756e4bfc3d4a764f45bba76105eadf2a0` | `389313f4702ed1568b1fc6d47cc8b7fe2224332f327bd15651ce85e1ccbc0be7` | `63915d3be2e834be047111b270658ab81ce48e19cafcdf7c17383da7719b8f8a` |
| `a3232ed1b94d-test_runtime.py.patch` | `ai/tests/agents/director/test_runtime.py` | `4f3475bca9b79905de6e3f1b98b8d7bf20468033caf86ad620f9a45a4ee89e7f` | `6327021c1e9d1f1f1810f9c334495406e84a8b87a7f7865a378e2343cd4c0f94` | `93b234cde66e23be41d562398d1117b0902e858f3c5d80bc630e64c0582bbfcb` |
| `c710088e06e9-test_configure_ai_runtime.py.patch` | `backend/tests/test_configure_ai_runtime.py` | `ca50adcc7b7bc628a1fb48796b6e3127460ed079fe41915241e6e7e9542a7132` | `494ec3b78c0515fbd238bb4be2fa5126f86bec492ec5f865f987036fc0910a1a` | `ead9765bb1682e6281a306aa3bd6c0bcf6567edfa4a54c32df3d5787b03a9459` |
| `ce4eee9a5b86-runtime.py.patch` | `ai/src/devon_ai/agents/director/runtime.py` | `1adc7f2bca324307bd326107113e54894e6aceb8dee32764e708c5b1bd438309` | `cab10e3a197313697389bdb61d54e3972363e98cbbbd01b7c2b965658bbf6b73` | `c23896a03759aa2cf546590cd6c3d140a2348fe8b0f21c4b6647423c61f77c3a` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

선행 PR은 #213·#216과 평가 실행기의 #214, 요청 크기 도우미의 #222입니다. #213의 지원 버전 검사를 #216에서도 보존한 뒤 이 runtime 패치를 적용합니다. 호출 시점 검사와 등록 시점 검사를 모두 유지하며 알 수 없는 버전은 모델 호출 전에 거절합니다. 복구 참고자료는 v7·v8의 Plan에만 전달하고 독립 Review에는 전달하지 않습니다. ADR 0040의 투영 구현은 이 PR 소유입니다.



<details>
<summary>이전 안내·과거 기준 지문(현재 적용 지문으로 사용 금지)</summary>

<!-- historical-patch-guidance -->
# Director 턴과 근거 참조 안정성 후속 변경

기존 미병합 구현을 중복 게시하지 않고 이번 수정 구간만 보존한 패치다.
이 파일을 게시해도 서비스 코드에 자동 적용되거나 기능이 활성화되지는 않는다.

선행 PR: #213, #216. 모든 PR의 base는 develop이다.
기존 게시 패치가 있다면 먼저 적용하고 이 표의 적용 전 지문과 일치하는지 확인한다.
지문은 UTF-8 텍스트의 CRLF를 LF로 정규화한 SHA256이다. 기준이 다르면 강제 적용하지 않는다.

## 적용 조건

1. 선행 구현과 이번 PR의 직접 변경을 반영한다.
2. 대상 파일의 적용 전 지문과 실제 내용을 확인한다.
3. 각 패치에 `git apply --check`를 실행하고 통과한 패치만 `git apply`로 반영한다.
4. 적용 후 지문과 원문을 확인하고 해당 기능의 회귀·통합 검증을 다시 실행한다.
5. 실제 코드 반영과 CI 재검증 전에는 Draft 상태를 해제하거나 병합하지 않는다.

## 대상과 지문

| 대상 | 패치 | 적용 전 SHA256 | 적용 후 SHA256 |
| --- | --- | --- | --- |
| `ai/prompts/runtime-prompts.json` | [0a6431ee6f3e-runtime-prompts.json.patch](0a6431ee6f3e-runtime-prompts.json.patch) | `1ea9e9552f26ccdeee5304750830edc756e4bfc3d4a764f45bba76105eadf2a0` | `389313f4702ed1568b1fc6d47cc8b7fe2224332f327bd15651ce85e1ccbc0be7` |
| `ai/src/devon_ai/agents/director/runtime.py` | [ce4eee9a5b86-runtime.py.patch](ce4eee9a5b86-runtime.py.patch) | `cc9c938d4553f2562898bcff31dc6e3792e9c6f1dea751739658b7b600265813` | `910c4e639de137cfe46ccabddac92c70baeede6c2f6ac885fa1f010b812eb9bb` |
| `ai/tests/agents/director/test_runtime.py` | [a3232ed1b94d-test_runtime.py.patch](a3232ed1b94d-test_runtime.py.patch) | `ffdd9a21a076b358f8b8864f119165a08488603e26f01e3b6b427d7589b2e726` | `6bf36189bbc070ace4a8cc25b188719a6bd37bf0f692a73fc5d7e42e9eeba3c0` |
| `backend/tests/test_configure_ai_runtime.py` | [c710088e06e9-test_configure_ai_runtime.py.patch](c710088e06e9-test_configure_ai_runtime.py.patch) | `ca50adcc7b7bc628a1fb48796b6e3127460ed079fe41915241e6e7e9542a7132` | `494ec3b78c0515fbd238bb4be2fa5126f86bec492ec5f865f987036fc0910a1a` |

## 2026-11-09 리뷰 반영 패치 지문

아래 SHA256은 패치 파일 자체의 최신 바이트 지문이다. 대상 원문의 적용 전·후 지문은 PR 종합 리뷰와 구현 기록의 재생 검증을 함께 확인한다.

| 패치 | SHA256 |
| --- | --- |
| [ce4eee9a5b86-runtime.py.patch](ce4eee9a5b86-runtime.py.patch) | `33a61188f68518b35ce5afc3346989627099e525e8022640d3e20a74f71aef54` |

적용 전 `git apply --check`와 실제 적용 후 검증을 모두 수행한다. 부분 활성화하지 않으며, 전체 소비자·모델·마이그레이션과 해당 테스트가 활성 소스에 반영되고 후속 패치의 preimage를 갱신해 재검증한 뒤에만 사용을 마친 패치를 제거한다. Draft·후속 패치 존재는 단독 실행 완료를 뜻하지 않는다.

</details>
