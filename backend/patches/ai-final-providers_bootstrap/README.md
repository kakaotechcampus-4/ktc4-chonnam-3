# 공급자·실행 설정 및 개발 초기화 후속 변경

이 디렉터리는 미병합 선행 구현에 대한 **이번 신규 수정 구간만** 보존한다.
선행 코드를 다시 복사하지 않으므로 이 PR을 병합하는 것만으로 아래 변경이 실행되지는 않는다.
직접 게시한 새 모듈도 별도 PR의 계약·실행 설정에 의존할 수 있다. 현재 PR은 Draft다.

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

실행 결과와 남은 작업의 원본 기록은 `spec/ai/implementation.md`다.
PR 본문의 게시본 검증과 과거 로컬 통합 검증을 구분해서 읽는다.
