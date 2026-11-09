# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `64dd8fdd67b5-openapi.yaml.patch` | `spec/shared/contracts/openapi.yaml` | `d3a89e0eec997286b72eb98ec1f997a542e36760abec0814d9ff96deecaf30d7` | `56177eaf37ba3d373f8783caa66aca96636c0ad41d37aee99ec446d158629c82` | `2587f192bc31fea23c13c65859f454238b4768f51ddcb63adca9fc2c48e0c09b` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 새 REST OpenAPI·FE 설명·REST 회귀는 함께 반영한다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

<details>
<summary>이전 안내·과거 기준 지문(현재 적용 지문으로 사용 금지)</summary>

<!-- historical-patch-guidance -->
# 공개 API와 AI 내부 계약 정의 후속 변경

이 디렉터리는 미병합 선행 구현에 대한 **이번 신규 수정 구간만** 보존한다.
선행 코드를 다시 복사하지 않으므로 이 PR을 병합하는 것만으로 아래 변경이 실행되지는 않는다.
직접 게시한 새 모듈도 별도 PR의 계약·실행 설정에 의존할 수 있다. 현재 PR은 Draft다.

패치 소유 PR: #212. 아래 표는 이동 후 소유 범위다.

## 적용 순서

1. PR 본문에 연결한 선행 PR과 필요한 계약·구현을 develop에 반영한다.
2. 각 대상 파일을 UTF-8 LF로 정규화한 SHA256이 아래 기준 지문과 같은지 확인한다.
   다르면 파일을 덮어쓰지 말고 최신 코드에 신규 수정의 의도를 병합한다.
3. 저장소 루트에서 해당 `.patch`에 `git apply --check <경로>`를 실행한다.
   모두 검토한 뒤 `git apply <경로>`로 적용하고 최종 지문·호출·모델 입력·저장 경로를 재검증한다.
4. 최종 반영 파일의 정적 검사·회귀·PostgreSQL 통합 검사와 공유 계약 검사를 실행한다.
   이 통합 검증이 통과하기 전에는 전체 기능 완료나 병합 가능 상태로 표시하지 않는다.

patch 안의 앞뒤 문맥은 위치 확인을 위한 것이며 선행 구현 전체를 게시한 것이 아니다.
기존 파일을 보완하는 다른 PR과 파일이 겹치면 적용 순서와 최종 내용을 함께 검토한다.


## 대상과 지문

| 대상 파일 | patch | 적용 전 SHA256 | 적용 후 SHA256 |
| --- | --- | --- | --- |
| `spec/shared/contracts/openapi.yaml` | [64dd8fdd67b5-openapi.yaml.patch](64dd8fdd67b5-openapi.yaml.patch) | `d3a89e0eec997286b72eb98ec1f997a542e36760abec0814d9ff96deecaf30d7` | `38b427483a1ecfec7fba7bbab1521134329038c86ef4b83dd5a593673235fb20` |

실행 결과와 남은 작업의 원본 기록은 `spec/ai/implementation.md`다.
PR 본문의 게시본 검증과 과거 로컬 통합 검증을 구분해서 읽는다.


<!-- review-fixes-b:atomic-bundle -->
## 이번 리뷰 반영과 적용 조건

현재 폴더는 실행 중인 기능이 아닌 후속 변경이다. 아래 지문은 UTF-8 LF 기준이며 `없음`은 신규 파일을 뜻한다. 파일을 읽었다는 사실이나 패치 보관만으로 적용 완료로 보지 않는다.

새 REST 설명·OpenAPI·REST 계약 회귀는 한 묶음으로 적용한다. 활성 FE 문서는 현재 develop REST 계약과 WS details 설명만 반영한다. 리포트 revision/retry 설명은 #228과 중복 게시하지 않는다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | 재생 |
| --- | --- | --- | --- | --- |
| `64dd8fdd67b5-openapi.yaml.patch` | `spec/shared/contracts/openapi.yaml` | `d3a89e0eec997286b72eb98ec1f997a542e36760abec0814d9ff96deecaf30d7` | `56177eaf37ba3d373f8783caa66aca96636c0ad41d37aee99ec446d158629c82` | 통과 |

선행 PR의 실제 병합 커밋에 3-way 재기준한 뒤 적용하고, 충돌을 해결한 최종 원문·테스트·SHA256을 대조한다. 모델/API 호출 없이 통과한 로컬 회귀와 실제 운영 검증은 구분한다. 적용 커밋·입력/출력 지문·통합 회귀를 `spec/ai/implementation.md`에 남긴 후에만 패치를 제거한다. 원본 작업 브랜치·기존 검증 기록은 삭제하지 않는다.

## 2026-11-09 리뷰 반영 패치 지문

아래 SHA256은 패치 파일 자체의 최신 바이트 지문이다. 대상 원문의 적용 전·후 지문은 PR 종합 리뷰와 구현 기록의 재생 검증을 함께 확인한다.

| 패치 | SHA256 |
| --- | --- |
| [64dd8fdd67b5-openapi.yaml.patch](64dd8fdd67b5-openapi.yaml.patch) | `2587f192bc31fea23c13c65859f454238b4768f51ddcb63adca9fc2c48e0c09b` |

적용 전 `git apply --check`와 실제 적용 후 검증을 모두 수행한다. 부분 활성화하지 않으며, 전체 소비자·모델·마이그레이션과 해당 테스트가 활성 소스에 반영되고 후속 패치의 preimage를 갱신해 재검증한 뒤에만 사용을 마친 패치를 제거한다. Draft·후속 패치 존재는 단독 실행 완료를 뜻하지 않는다.

</details>
