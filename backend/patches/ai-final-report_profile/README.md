# 리포트 재시도·검토·버전과 프로필 갱신 후속 변경

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
| `backend/app/features/profile/queries.py` | [333d22492c30-queries.py.patch](333d22492c30-queries.py.patch) | `7381969597b35a108b95cd9a382136cfb7b102321667f14b5753a7aa3121d2cd` | `f812ec37a190459468371d8a17505dd8f1927f13a98d1493543585c55d8d1d85` |
| `backend/app/features/profile/service.py` | [0e327f5662e1-service.py.patch](0e327f5662e1-service.py.patch) | `68ccf703e990ddafab6d13ab37cd0dfa9ecaba5ca557069e6ab581d4c9b1344d` | `1163d89d695940db7613f1e5fe470d321290df206390a8d59199638fbac6dcd2` |
| `backend/app/workers/arq_app.py` | [a0d68e234461-arq_app.py.patch](a0d68e234461-arq_app.py.patch) | `e149c36918e908726677820058d8caa2d0e5915ffa662bd369ea164e568f65ef` | `90cece27a850e9b10e277ca1996f488732d16c622efaa08a3dc98cdb8a860116` |
| `backend/app/workers/tasks/profile_summary.py` | [7ed9e7d1011c-profile_summary.py.patch](7ed9e7d1011c-profile_summary.py.patch) | `06e04f96170f34be0a12c68d5e82181ed34f37cec463a80873d5760ae03a6b07` | `502dc762624d03aa6ef2c134710826e051d4b4fd008456a3d41276d43de2a097` |
| `backend/tests/features/profile/test_profile_service.py` | [0863c8209178-test_profile_service.py.patch](0863c8209178-test_profile_service.py.patch) | `d39e58fcd2e9c7710fb1601464472797c223b95ca5cc1a2c122a2333f45d6dc5` | `7fd5e066c92994140f9900d67573b529a2f80bdaefeabc7f3e83113a7fb0c24f` |
| `backend/tests/features/profile/test_profile_worker.py` | [5e0621825be7-test_profile_worker.py.patch](5e0621825be7-test_profile_worker.py.patch) | `74ed4a9807b9c4004a724d0e07adc45e55a89c9b4310b944f8b92a7ad67f14f5` | `98350840b3e78bc1acdaa2caaa851992a65fbe56d9ee699831dd987a62c61fd9` |

실행 결과와 남은 작업의 원본 기록은 `spec/ai/implementation.md`다.
PR 본문의 게시본 검증과 과거 로컬 통합 검증을 구분해서 읽는다.
