# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

제거한 no-op: `f8eee7ea7064-test_config.py.patch` (기존 SHA256 `5f95ff327f76d9031bb7d04ff194791c6db0568511608d215bb67942bb83192d`). 해당 설정 검사 함수가 #213에 통합되어 후속 차이가 사라졌다. 변경 hunk가 없는 원격 산출물은 삭제하고 원문은 검증 기록에 보존한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `0f8cacfd4c9a-client.py.patch` | `backend/app/integrations/llm/client.py` | `d9b58f4f02d569bb0614e1ae08798db55608d445fe99c205ccab2b4a04fc15ec` | `3fab5db14b8ad44570c5a249e33e8817c6b2c01e70022e27b499284a972cf57f` | `2fd620740452b1e5b0e8f36c93ac76399ac3ef61a47d47c07e8fda598ab6f30f` |
| `361f2d0f55c4-.env.example.patch` | `backend/.env.example` | `0e9148293c840934f22b1756996d06fec30347f07e2e34e1945514ba500fb1d4` | `80644b49900f6d0447213ecf110976fda73a632a0b305cb6abc4d80cc5bd7d8b` | `21148eb4bf5930525ae453d7babd5ff5285f7b5b880a6fb07c9fc693e9d4f4f6` |
| `c2a439a5efd7-config.py.patch` | `backend/app/core/config.py` | `3138bc9f917597b8e07a5becc5d8455cc1e3ef17af95376a952b930cbb54e6fe` | `15452cec0086abc7381ebccfb6c3cc66a75b6f27e1a62d95f398b89494305d60` | `31dc0c26996cdfa517ccd4ce5cb53add2fdf043bbb68eecfce7de7e50026060c` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

<details>
<summary>이전 안내·과거 기준 지문(현재 적용 지문으로 사용 금지)</summary>

<!-- historical-patch-guidance -->
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

## 2026-11-09 리뷰 반영 패치 지문

아래 SHA256은 패치 파일 자체의 최신 바이트 지문이다. 대상 원문의 적용 전·후 지문은 PR 종합 리뷰와 구현 기록의 재생 검증을 함께 확인한다.

| 패치 | SHA256 |
| --- | --- |
| [361f2d0f55c4-.env.example.patch](361f2d0f55c4-.env.example.patch) | `21148eb4bf5930525ae453d7babd5ff5285f7b5b880a6fb07c9fc693e9d4f4f6` |
| [c2a439a5efd7-config.py.patch](c2a439a5efd7-config.py.patch) | `31dc0c26996cdfa517ccd4ce5cb53add2fdf043bbb68eecfce7de7e50026060c` |
| [f8eee7ea7064-test_config.py.patch](f8eee7ea7064-test_config.py.patch) | `5f95ff327f76d9031bb7d04ff194791c6db0568511608d215bb67942bb83192d` |

적용 전 `git apply --check`와 실제 적용 후 검증을 모두 수행한다. 부분 활성화하지 않으며, 전체 소비자·모델·마이그레이션과 해당 테스트가 활성 소스에 반영되고 후속 패치의 preimage를 갱신해 재검증한 뒤에만 사용을 마친 패치를 제거한다. Draft·후속 패치 존재는 단독 실행 완료를 뜻하지 않는다.

</details>
