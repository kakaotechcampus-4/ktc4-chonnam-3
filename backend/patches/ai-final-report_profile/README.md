# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `0863c8209178-test_profile_service.py.patch` | `backend/tests/features/profile/test_profile_service.py` | `d39e58fcd2e9c7710fb1601464472797c223b95ca5cc1a2c122a2333f45d6dc5` | `7fd5e066c92994140f9900d67573b529a2f80bdaefeabc7f3e83113a7fb0c24f` | `819681f7b24e02c4aeaea54c50f652a57e09e8ea39d441cd75e568f215decd65` |
| `0e327f5662e1-service.py.patch` | `backend/app/features/profile/service.py` | `68ccf703e990ddafab6d13ab37cd0dfa9ecaba5ca557069e6ab581d4c9b1344d` | `1163d89d695940db7613f1e5fe470d321290df206390a8d59199638fbac6dcd2` | `7d8c733cc3f5a0531875fb6da5f26e0cd71471abb7e1bc230b0f45e7e0cba15c` |
| `333d22492c30-queries.py.patch` | `backend/app/features/profile/queries.py` | `7381969597b35a108b95cd9a382136cfb7b102321667f14b5753a7aa3121d2cd` | `f812ec37a190459468371d8a17505dd8f1927f13a98d1493543585c55d8d1d85` | `dbe91cadaa03359087eaad644a3e60ac529ce9e023e8c39d22bae8f4eb0a95ec` |
| `5e0621825be7-test_profile_worker.py.patch` | `backend/tests/features/profile/test_profile_worker.py` | `74ed4a9807b9c4004a724d0e07adc45e55a89c9b4310b944f8b92a7ad67f14f5` | `98350840b3e78bc1acdaa2caaa851992a65fbe56d9ee699831dd987a62c61fd9` | `e68c6d5cba6a68346579b793f6504bbb819f4e180510c85b192b6d7ab8be1415` |
| `7ed9e7d1011c-profile_summary.py.patch` | `backend/app/workers/tasks/profile_summary.py` | `06e04f96170f34be0a12c68d5e82181ed34f37cec463a80873d5760ae03a6b07` | `502dc762624d03aa6ef2c134710826e051d4b4fd008456a3d41276d43de2a097` | `2cae1027b52c41bcaf08b4b2732188afbe53dfcc6d69e4621928fa665ad9a600` |
| `a0d68e234461-arq_app.py.patch` | `backend/app/workers/arq_app.py` | `06d36fe192ba5aa84a76f63da43edd276eb225ecfc3703a5fe73e1b02e3de041` | `cc8cf41bb2c98d8185a3c11fb08f751e5356636d606847455e74e0423f0f02d7` | `f3541a842fc6aefc5184ccaaf40e6972bc561bb546ae0df16042457c3b108f92` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 리포트 outbox 생산자·3인수 worker·reaper 등록·ProfileRefreshRequest/0012·전용 회귀는 함께 활성화한다. #165와 report/service.py를 접합할 때 report_viewed 기록과 commit_events를 유지한다. 활성 게시본은 선행 구현을 제외한 상태이므로 양쪽을 단순 3-way 병합하면 같은 조회 구간에서 충돌할 수 있으며, 이 조건을 확인하지 않은 자동 병합은 허용하지 않는다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

<details>
<summary>이전 안내·과거 기준 지문(현재 적용 지문으로 사용 금지)</summary>

<!-- historical-patch-guidance -->
# 리포트 재시도·검토·버전과 프로필 갱신 후속 변경

이 디렉터리는 미병합 선행 구현에 대한 **이번 신규 수정 구간만** 보존한다.
선행 코드를 다시 복사하지 않으므로 이 PR을 병합하는 것만으로 아래 변경이 실행되지는 않는다.
직접 게시한 새 모듈도 별도 PR의 계약·실행 설정에 의존할 수 있다. 현재 PR은 Draft다.

패치 소유 PR: #218. 아래 표는 이동 후 소유 범위다.

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


<!-- review-fixes-b:atomic-bundle -->
## 이번 리뷰 반영과 적용 조건

현재 폴더는 실행 중인 기능이 아닌 후속 변경이다. 아래 지문은 UTF-8 LF 기준이며 `없음`은 신규 파일을 뜻한다. 파일을 읽었다는 사실이나 패치 보관만으로 적용 완료로 보지 않는다.

활성 호출은 기존 user-only profile job을 유지한다. 이 폴더와 `ai-final-report_profile`·`ai-review-218`의 생산자 복원, `ProfileRefreshRequest`/0012 모델·마이그레이션 및 models export, profile_refresh_queue, 3인수 profile_summary worker, profile_refresh_reaper와 arq_app 등록, 관련 원문 회귀를 함께 적용한다. worker나 생산자 한쪽만 먼저 활성화하지 않는다.

busy도 최대 5회 전달 회차에 포함하며 다음 전달만 worker 전체 상한 뒤로 늦춘다. 회차는 fencing 값이므로 감소시키지 않는다. 24시간 만료와 실패 행을 보존하고 종료 후 안전한 profile_refresh_terminal 로그로 상한·만료를 구분한다. 별도 알림 시스템을 구현했다는 뜻은 아니다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | 재생 |
| --- | --- | --- | --- | --- |
| `0863c8209178-test_profile_service.py.patch` | `backend/tests/features/profile/test_profile_service.py` | `d39e58fcd2e9c7710fb1601464472797c223b95ca5cc1a2c122a2333f45d6dc5` | `7fd5e066c92994140f9900d67573b529a2f80bdaefeabc7f3e83113a7fb0c24f` | 통과 |
| `0e327f5662e1-service.py.patch` | `backend/app/features/profile/service.py` | `68ccf703e990ddafab6d13ab37cd0dfa9ecaba5ca557069e6ab581d4c9b1344d` | `1163d89d695940db7613f1e5fe470d321290df206390a8d59199638fbac6dcd2` | 통과 |
| `333d22492c30-queries.py.patch` | `backend/app/features/profile/queries.py` | `7381969597b35a108b95cd9a382136cfb7b102321667f14b5753a7aa3121d2cd` | `f812ec37a190459468371d8a17505dd8f1927f13a98d1493543585c55d8d1d85` | 통과 |
| `5e0621825be7-test_profile_worker.py.patch` | `backend/tests/features/profile/test_profile_worker.py` | `74ed4a9807b9c4004a724d0e07adc45e55a89c9b4310b944f8b92a7ad67f14f5` | `98350840b3e78bc1acdaa2caaa851992a65fbe56d9ee699831dd987a62c61fd9` | 통과 |
| `7ed9e7d1011c-profile_summary.py.patch` | `backend/app/workers/tasks/profile_summary.py` | `06e04f96170f34be0a12c68d5e82181ed34f37cec463a80873d5760ae03a6b07` | `502dc762624d03aa6ef2c134710826e051d4b4fd008456a3d41276d43de2a097` | 통과 |
| `a0d68e234461-arq_app.py.patch` | `backend/app/workers/arq_app.py` | `e149c36918e908726677820058d8caa2d0e5915ffa662bd369ea164e568f65ef` | `cc8cf41bb2c98d8185a3c11fb08f751e5356636d606847455e74e0423f0f02d7` | 통과 |

선행 PR의 실제 병합 커밋에 3-way 재기준한 뒤 적용하고, 충돌을 해결한 최종 원문·테스트·SHA256을 대조한다. 모델/API 호출 없이 통과한 로컬 회귀와 실제 운영 검증은 구분한다. 적용 커밋·입력/출력 지문·통합 회귀를 `spec/ai/implementation.md`에 남긴 후에만 패치를 제거한다. 원본 작업 브랜치·기존 검증 기록은 삭제하지 않는다.

## 2026-11-09 리뷰 반영 패치 지문

아래 SHA256은 패치 파일 자체의 최신 바이트 지문이다. 대상 원문의 적용 전·후 지문은 PR 종합 리뷰와 구현 기록의 재생 검증을 함께 확인한다.

| 패치 | SHA256 |
| --- | --- |
| [a0d68e234461-arq_app.py.patch](a0d68e234461-arq_app.py.patch) | `f3541a842fc6aefc5184ccaaf40e6972bc561bb546ae0df16042457c3b108f92` |

적용 전 `git apply --check`와 실제 적용 후 검증을 모두 수행한다. 부분 활성화하지 않으며, 전체 소비자·모델·마이그레이션과 해당 테스트가 활성 소스에 반영되고 후속 패치의 preimage를 갱신해 재검증한 뒤에만 사용을 마친 패치를 제거한다. Draft·후속 패치 존재는 단독 실행 완료를 뜻하지 않는다.

</details>
