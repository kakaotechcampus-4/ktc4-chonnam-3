# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `361f2d0f55c4-.env.example.patch` | `backend/.env.example` | `8c6546d3472f846b53323d391ccf14b3d1b54af9569091aecd3b9f68b098a6ca` | `0e9148293c840934f22b1756996d06fec30347f07e2e34e1945514ba500fb1d4` | `7b3874f9f10bbdb08371e9d5d8319e912fa2b634c4805aa676fbbc78e39df05f` |
| `79e828b8ae08-events.py.patch` | `backend/app/shared/events.py` | `0a001d691af8a01299b1b94ed3cc45a252b9c8af33c06ec7f8a10863d5bbb89b` | `ae6a3444c191ac8276da61e2f98bdcc71bfc2b591ef393a10c616d01aadba9c7` | `687d0785e2c66adc9b92ae0f1ea73f7d36c51138aaa4be37a027aac0c8206aec` |
| `9b43f3c23789-client.py.patch` | `backend/app/integrations/stt/client.py` | `30e6e9a21b340fdec875faacd5b750b7a20a32bf47b0ca1e5bde514efde1326e` | `e67642f113712780ee6c4b5b641dd9e9095e3a3f1d7bd728e4f471a65544596e` | `ef92fab9062021c3a454be5a72938ec5ffad2305c0f4a8251ffae7b4c4538977` |
| `c2a439a5efd7-config.py.patch` | `backend/app/core/config.py` | `de80b7e8e8717d41fc73fab4bacf19a32c5c513807c42003066011a794934e41` | `3138bc9f917597b8e07a5becc5d8455cc1e3ef17af95376a952b930cbb54e6fe` | `3943f1688e86ce96da50be4ecde257e7468bf9ee1f716990c5dffc8e23447192` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

<details>
<summary>이전 안내·과거 기준 지문(현재 적용 지문으로 사용 금지)</summary>

<!-- historical-patch-guidance -->
# 공급자·실행 설정 및 개발 초기화 후속 변경

이 디렉터리는 미병합 선행 구현에 대한 **이번 신규 수정 구간만** 보존한다.
선행 코드를 다시 복사하지 않으므로 이 PR을 병합하는 것만으로 아래 변경이 실행되지는 않는다.
직접 게시한 새 모듈도 별도 PR의 계약·실행 설정에 의존할 수 있다. 현재 PR은 Draft다.

패치 소유 PR: #213. 아래 표는 이동 후 소유 범위다.

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
| `backend/.env.example` | [361f2d0f55c4-.env.example.patch](361f2d0f55c4-.env.example.patch) | `8c6546d3472f846b53323d391ccf14b3d1b54af9569091aecd3b9f68b098a6ca` | `7d252d0036a99412f2739dd298e788090eb5512ae8b76dbaeded4e86a1516071` |
| `backend/app/core/config.py` | [c2a439a5efd7-config.py.patch](c2a439a5efd7-config.py.patch) | `de80b7e8e8717d41fc73fab4bacf19a32c5c513807c42003066011a794934e41` | `52e4debf03fa3425d6f8b3036d29a5c4824810a9a8a9ab2cff3fce29758db804` |
| `backend/app/integrations/stt/client.py` | [9b43f3c23789-client.py.patch](9b43f3c23789-client.py.patch) | `30e6e9a21b340fdec875faacd5b750b7a20a32bf47b0ca1e5bde514efde1326e` | `e67642f113712780ee6c4b5b641dd9e9095e3a3f1d7bd728e4f471a65544596e` |
| `backend/app/shared/events.py` | [79e828b8ae08-events.py.patch](79e828b8ae08-events.py.patch) | `0a001d691af8a01299b1b94ed3cc45a252b9c8af33c06ec7f8a10863d5bbb89b` | `ae6a3444c191ac8276da61e2f98bdcc71bfc2b591ef393a10c616d01aadba9c7` |

실행 결과와 남은 작업의 원본 기록은 `spec/ai/implementation.md`다.
PR 본문의 게시본 검증과 과거 로컬 통합 검증을 구분해서 읽는다.

## 2026-11-09 리뷰 반영 패치 지문

아래 SHA256은 패치 파일 자체의 최신 바이트 지문이다. 대상 원문의 적용 전·후 지문은 PR 종합 리뷰와 구현 기록의 재생 검증을 함께 확인한다.

| 패치 | SHA256 |
| --- | --- |
| [361f2d0f55c4-.env.example.patch](361f2d0f55c4-.env.example.patch) | `7b3874f9f10bbdb08371e9d5d8319e912fa2b634c4805aa676fbbc78e39df05f` |
| [c2a439a5efd7-config.py.patch](c2a439a5efd7-config.py.patch) | `3943f1688e86ce96da50be4ecde257e7468bf9ee1f716990c5dffc8e23447192` |

적용 전 `git apply --check`와 실제 적용 후 검증을 모두 수행한다. 부분 활성화하지 않으며, 전체 소비자·모델·마이그레이션과 해당 테스트가 활성 소스에 반영되고 후속 패치의 preimage를 갱신해 재검증한 뒤에만 사용을 마친 패치를 제거한다. Draft·후속 패치 존재는 단독 실행 완료를 뜻하지 않는다.

</details>
