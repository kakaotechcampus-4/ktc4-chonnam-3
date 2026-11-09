# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `runtime-all-consumers-test.py.patch` | `backend/tests/llm_tasks/test_runtime_capabilities.py` | `f670f01a86cf60972cf1bd4d9a258ecc0f3b56a862b2823311147da74d243805` | `4cc441f0323f68ff27d17bccc0dd7b756e45c7c45196bbb403625aa89d4acc27` | `d6e59de90da2b8d884b1226c88aea0487a9c1e3e660e01e567bc2994be868169` |
| `optional-provider-settings-test.py.patch` | `backend/tests/core/test_optional_provider_config.py` | `없음` | `6a0b5c0afd963c945c84395979877d1e5e6e940a9296b1b6aed4e85dcf327e45` | `761b2d400be84c2764b5c9a1697bcc22f90e3fec6d019f4ceb7f3b8339787e22` |
| `provider-example-assertions.py.patch` | `backend/tests/test_config.py` | `a9f2e99b4dccd346c8da371ce53a6274f3c73d0547fcda663f9c62539dbcae4a` | `491f3e3b7915b83e88aa411769e30a73d583d25c55822da47f66d52ad915ee6c` | `3829f4f06243b009a04c8fbba9d3f0242696d237d0356046facde13e8ba69e28` |
| `final-provider-settings-test.py.patch` | `backend/tests/test_final_provider_settings.py` | `없음` | `ddd16f9447816b429917dd90eceac95d5c60815595eab261df24c7b51a4b2bf4` | `79d6d3a4f695653e64e1c1f915b27bc74eeb4df65677752313479a34230bac76` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

선택 공급자 설정 회귀는 미병합 Settings 필드를 복사하지 않도록 신규 파일 패치로 보존합니다. #213 설정 패치를 실제 적용한 뒤 이 테스트도 함께 활성화합니다.

Settings 필드·예제·공급자 설정 회귀를 원자적으로 적용합니다. 활성 예제 검사는 현재 Settings가 공개하는 비밀 필드를 확인합니다. 전체 공급자 필드의 엄격한 예제 검사, 기존 final_provider_settings 원문 전체, 신규 빈 credential 회귀는 이 디렉터리에 보존하며 설정·예제 패치와 함께 활성화해야 합니다. 테스트를 삭제하거나 skip하지 않고 적용 전·후 범위를 구분합니다.



<details>
<summary>이전 안내·과거 기준 지문(현재 적용 지문으로 사용 금지)</summary>

<!-- historical-patch-guidance -->
# 리뷰 후속 패치

선행 구현이 있는 통합본에만 적용하는 신규 변경이다. 선행 파일 전체를 복사하지 않는다.

## 2026-11-09 리뷰 반영 패치 지문

아래 SHA256은 패치 파일 자체의 최신 바이트 지문이다. 대상 원문의 적용 전·후 지문은 PR 종합 리뷰와 구현 기록의 재생 검증을 함께 확인한다.

| 패치 | SHA256 |
| --- | --- |
| [runtime-all-consumers-test.py.patch](runtime-all-consumers-test.py.patch) | `70b0d85e838d8725de31902fdbb2c63ad7bb7e6b8aa83f509be9dbf835397033` |

적용 전 `git apply --check`와 실제 적용 후 검증을 모두 수행한다. 부분 활성화하지 않으며, 전체 소비자·모델·마이그레이션과 해당 테스트가 활성 소스에 반영되고 후속 패치의 preimage를 갱신해 재검증한 뒤에만 사용을 마친 패치를 제거한다. Draft·후속 패치 존재는 단독 실행 완료를 뜻하지 않는다.

</details>
