# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `64dd8fdd67b5-openapi.yaml.patch` | `spec/shared/contracts/openapi.yaml` | `56177eaf37ba3d373f8783caa66aca96636c0ad41d37aee99ec446d158629c82` | `4c2c682d9671381827bbaad1d8a67eb161cf7e693d5f0b82059676dfa5546f9a` | `587ceb165805816d927defc379276b8d8d5dad9c7b7223fe79d8386908974e13` |
| `e4690d14d501-api-spec.md.patch` | `frontend/docs/api-spec.md` | `ae94a2d78da0a6f6ec3591f2ee82267d2a6bdd04d6b16584dcb65a4a909c7841` | `e502accbfcefd3bf58ce9adb6bc1dd99d6aace99d80e8a37579ddc35d59a7d91` | `4695103df1a2d01f3dde5b61f9596013759a7d907823b850547966f1faf6456b` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 새 REST OpenAPI·FE 설명·REST 회귀는 함께 반영한다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

공통 0011 원본은 이 계약 PR에 두고 0010의 다음 질문 복구 금지 범위만 부분 대체합니다. OpenAPI와 FE API 설명은 #212 계약 이후 함께 적용합니다. questionRetryState로 저장 UUID·실행 상태·기한을 복원하며 FE 합의와 로컬 승인을 구분합니다.

<details>
<summary>이전 안내·과거 기준 지문(현재 적용 지문으로 사용 금지)</summary>

<!-- historical-patch-guidance -->
# 면접 질문 복구 API 계약 후속 변경

기존 미병합 구현을 중복 게시하지 않고 이번 수정 구간만 보존한 패치다.
이 파일을 게시해도 서비스 코드에 자동 적용되거나 기능이 활성화되지는 않는다.

선행 PR: #212. 모든 PR의 base는 develop이다.
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
| `frontend/docs/api-spec.md` | [e4690d14d501-api-spec.md.patch](e4690d14d501-api-spec.md.patch) | `11a7cb8936ba82a90415de76c06eedd3c02092a3650324a8df733eb310d56502` | `9688feb5c32e3c0c8247e55f180ea4dfa2a9010edb3a4308b3440d8069d6a458` |
| `spec/shared/contracts/openapi.yaml` | [64dd8fdd67b5-openapi.yaml.patch](64dd8fdd67b5-openapi.yaml.patch) | `38b427483a1ecfec7fba7bbab1521134329038c86ef4b83dd5a593673235fb20` | `559ee7bcf7655067c70d744604487c6ef4512dd77a2134221ad3009adb09407a` |


<!-- review-fixes-b:atomic-bundle -->
## 이번 리뷰 반영과 적용 조건

현재 폴더는 실행 중인 기능이 아닌 후속 변경이다. 아래 지문은 UTF-8 LF 기준이며 `없음`은 신규 파일을 뜻한다. 파일을 읽었다는 사실이나 패치 보관만으로 적용 완료로 보지 않는다.

리포트 revision/retry FE 설명은 #212 계약 묶음으로 이전했다. 이 PR에는 새 질문 복구 OpenAPI 계약을 유지하며 기존 api-spec 중복 패치는 제거했다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | 재생 |
| --- | --- | --- | --- | --- |
| `64dd8fdd67b5-openapi.yaml.patch` | `spec/shared/contracts/openapi.yaml` | `38b427483a1ecfec7fba7bbab1521134329038c86ef4b83dd5a593673235fb20` | `559ee7bcf7655067c70d744604487c6ef4512dd77a2134221ad3009adb09407a` | 통과 |

선행 PR의 실제 병합 커밋에 3-way 재기준한 뒤 적용하고, 충돌을 해결한 최종 원문·테스트·SHA256을 대조한다. 모델/API 호출 없이 통과한 로컬 회귀와 실제 운영 검증은 구분한다. 적용 커밋·입력/출력 지문·통합 회귀를 `spec/ai/implementation.md`에 남긴 후에만 패치를 제거한다. 원본 작업 브랜치·기존 검증 기록은 삭제하지 않는다.

## 2026-11-09 리뷰 반영 패치 지문

아래 SHA256은 패치 파일 자체의 최신 바이트 지문이다. 대상 원문의 적용 전·후 지문은 PR 종합 리뷰와 구현 기록의 재생 검증을 함께 확인한다.

| 패치 | SHA256 |
| --- | --- |
| [64dd8fdd67b5-openapi.yaml.patch](64dd8fdd67b5-openapi.yaml.patch) | `3b9903081a9a6097d751f463db90ad0249ef6d3e8f52a13aec139fb897eb83e2` |

적용 전 `git apply --check`와 실제 적용 후 검증을 모두 수행한다. 부분 활성화하지 않으며, 전체 소비자·모델·마이그레이션과 해당 테스트가 활성 소스에 반영되고 후속 패치의 preimage를 갱신해 재검증한 뒤에만 사용을 마친 패치를 제거한다. Draft·후속 패치 존재는 단독 실행 완료를 뜻하지 않는다.

</details>
