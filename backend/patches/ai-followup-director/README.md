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
