# AI 실행 설정과 안전 로그 후속 변경

기존 미병합 구현을 중복 게시하지 않고 이번 수정 구간만 보존한 패치다.
이 파일을 게시해도 서비스 코드에 자동 적용되거나 기능이 활성화되지는 않는다.

선행 PR: #213. 모든 PR의 base는 develop이다.
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
| `backend/.env.example` | [361f2d0f55c4-.env.example.patch](361f2d0f55c4-.env.example.patch) | `7d252d0036a99412f2739dd298e788090eb5512ae8b76dbaeded4e86a1516071` | `0af79d302abf55914345aef174d27da8304de02984c9caefe21cc722a98f2f26` |
| `backend/app/core/config.py` | [c2a439a5efd7-config.py.patch](c2a439a5efd7-config.py.patch) | `52e4debf03fa3425d6f8b3036d29a5c4824810a9a8a9ab2cff3fce29758db804` | `e84e006da9079f9300d0215b2002395099f47b1a7e009520e71cf1268114c2cd` |
| `backend/app/integrations/llm/client.py` | [0f8cacfd4c9a-client.py.patch](0f8cacfd4c9a-client.py.patch) | `d9b58f4f02d569bb0614e1ae08798db55608d445fe99c205ccab2b4a04fc15ec` | `3fab5db14b8ad44570c5a249e33e8817c6b2c01e70022e27b499284a972cf57f` |
| `backend/tests/test_config.py` | [f8eee7ea7064-test_config.py.patch](f8eee7ea7064-test_config.py.patch) | `526c9939a0e220973cde2802a60727963c7ce4e033fd089c562f6ac560f6dd73` | `cfa390e8db309bb4cf70a686d1db2a87e85078e5e69b47b5fc420b87c19d769b` |
