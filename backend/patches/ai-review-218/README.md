# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `cb663da9e4e3-profile_summary.py.patch` | `backend/app/llm_tasks/profile_summary.py` | `00802a432438b3cf9cbffe3b57d9244757db3ebbd2d4ebeaf1f1e1114ed78e18` | `11f60c4cb83bd2cab4b195117cdd73cf8e5980d31844d36138cff7c6ba59e3f8` | `d1b4118c4b56e1710061cbe7ee274a0a915cae3f9ff7ccc4caf71072c82bf685` |
| `create-test_profile_outbox_worker.py.patch` | `backend/tests/features/profile/test_profile_outbox_worker.py` | `없음` | `15d135e909ab9eaa89fdbef5f4badea1bec5be1ac251a6ad31b797ba34ab8e28` | `4d1757786dc3bae30b6b28e24e2a49db0f5e133be45ea0a8795eb7ada0c1beee` |
| `create-test_profile_refresh_outbox.py.patch` | `backend/tests/agents/test_profile_refresh_outbox.py` | `없음` | `d1705eac7634d4770f9a147729f815a80f185c756d9065cb47837f72ec45bea5` | `8d962c2be72795b5f9757fcbd48235738af6fbf32e7ccb5da93ca1acdbd29ae6` |
| `restore-profile-outbox-producer-service.py.patch` | `backend/app/features/report/service.py` | `59d7edea12d29728de4f90f4a58f2e0aabf29922800f265f3091184c04cb7f3d` | `e2e4a7ba31e1145d3912f1b899455e6e546556895ae5b6da0435dc07f825b95c` | `e25c34f5cea7c51ac9344b521e0ba585a5a01945bed50b2139e8636616052560` |
| `restore-report_generate.py.patch` | `backend/app/workers/tasks/report_generate.py` | `07e027302922481205cd2b4b9bcf4fa555168ba5add986daf263db5a4b03fe79` | `0c317ced5289fa45fb9a28bfbf80004119edf503f04e486b885d9d85ff986307` | `81eaa55cd0782ac4586298499641ecc4b3fa467c15c221f39ad2f77ce9fec556` |
| `restore-test_report_generate.py.patch` | `backend/tests/features/report/test_report_generate.py` | `f078aab9021b88ef8d89ce5c69d70c56efbb33d238d12bd8b914efc8e60417bb` | `a5f0744bb636c53ea99b345e505dde96d26dcc9d955ec7a8c8eeb9ee94ae9243` | `0711e10435cade101308ba380dfcd68d5456ca09d7c8ed3373b43db07b205e7a` |
| `restore-test_report_worker.py.patch` | `backend/tests/features/report/test_report_worker.py` | `db1be2ea8e2fdfa13ea48a0eaece4baf07832df4dcf597c688263a57fe541e0b` | `18f9217aec5f0e1888b037cac5befed0c0ecf2cdc5eef21819064f01d35a0ce7` | `32cc4cf86a01723afde8bbece811a8cdf816ef08f9f2ec3bc18e2ffc149fb10c` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 리포트 outbox 생산자·3인수 worker·reaper 등록·ProfileRefreshRequest/0012·전용 회귀는 함께 활성화한다. #165와 report/service.py를 접합할 때 report_viewed 기록과 commit_events를 유지한다. 활성 게시본은 선행 구현을 제외한 상태이므로 양쪽을 단순 3-way 병합하면 같은 조회 구간에서 충돌할 수 있으며, 이 조건을 확인하지 않은 자동 병합은 허용하지 않는다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

<details>
<summary>이전 안내·과거 기준 지문(현재 적용 지문으로 사용 금지)</summary>

<!-- historical-patch-guidance -->
# 적용 대기 패치


<!-- review-fixes-b:atomic-bundle -->
## 이번 리뷰 반영과 적용 조건

현재 폴더는 실행 중인 기능이 아닌 후속 변경이다. 아래 지문은 UTF-8 LF 기준이며 `없음`은 신규 파일을 뜻한다. 파일을 읽었다는 사실이나 패치 보관만으로 적용 완료로 보지 않는다.

활성 호출은 기존 user-only profile job을 유지한다. 이 폴더와 `ai-final-report_profile`·`ai-review-218`의 생산자 복원, `ProfileRefreshRequest`/0012 모델·마이그레이션 및 models export, profile_refresh_queue, 3인수 profile_summary worker, profile_refresh_reaper와 arq_app 등록, 관련 원문 회귀를 함께 적용한다. worker나 생산자 한쪽만 먼저 활성화하지 않는다.

busy도 최대 5회 전달 회차에 포함하며 다음 전달만 worker 전체 상한 뒤로 늦춘다. 회차는 fencing 값이므로 감소시키지 않는다. 24시간 만료와 실패 행을 보존하고 종료 후 안전한 profile_refresh_terminal 로그로 상한·만료를 구분한다. 별도 알림 시스템을 구현했다는 뜻은 아니다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | 재생 |
| --- | --- | --- | --- | --- |
| `cb663da9e4e3-profile_summary.py.patch` | `backend/app/llm_tasks/profile_summary.py` | `00802a432438b3cf9cbffe3b57d9244757db3ebbd2d4ebeaf1f1e1114ed78e18` | `11f60c4cb83bd2cab4b195117cdd73cf8e5980d31844d36138cff7c6ba59e3f8` | 통과 |
| `create-test_profile_outbox_worker.py.patch` | `backend/tests/features/profile/test_profile_outbox_worker.py` | `없음` | `15d135e909ab9eaa89fdbef5f4badea1bec5be1ac251a6ad31b797ba34ab8e28` | 통과 |
| `create-test_profile_refresh_outbox.py.patch` | `backend/tests/agents/test_profile_refresh_outbox.py` | `없음` | `d1705eac7634d4770f9a147729f815a80f185c756d9065cb47837f72ec45bea5` | 통과 |
| `restore-profile-outbox-producer-service.py.patch` | `backend/app/features/report/service.py` | `59d7edea12d29728de4f90f4a58f2e0aabf29922800f265f3091184c04cb7f3d` | `e2e4a7ba31e1145d3912f1b899455e6e546556895ae5b6da0435dc07f825b95c` | 통과 |
| `restore-report_generate.py.patch` | `backend/app/workers/tasks/report_generate.py` | `07e027302922481205cd2b4b9bcf4fa555168ba5add986daf263db5a4b03fe79` | `0c317ced5289fa45fb9a28bfbf80004119edf503f04e486b885d9d85ff986307` | 통과 |
| `restore-test_report_generate.py.patch` | `backend/tests/features/report/test_report_generate.py` | `f078aab9021b88ef8d89ce5c69d70c56efbb33d238d12bd8b914efc8e60417bb` | `a5f0744bb636c53ea99b345e505dde96d26dcc9d955ec7a8c8eeb9ee94ae9243` | 통과 |
| `restore-test_report_worker.py.patch` | `backend/tests/features/report/test_report_worker.py` | `db1be2ea8e2fdfa13ea48a0eaece4baf07832df4dcf597c688263a57fe541e0b` | `18f9217aec5f0e1888b037cac5befed0c0ecf2cdc5eef21819064f01d35a0ce7` | 통과 |

선행 PR의 실제 병합 커밋에 3-way 재기준한 뒤 적용하고, 충돌을 해결한 최종 원문·테스트·SHA256을 대조한다. 모델/API 호출 없이 통과한 로컬 회귀와 실제 운영 검증은 구분한다. 적용 커밋·입력/출력 지문·통합 회귀를 `spec/ai/implementation.md`에 남긴 후에만 패치를 제거한다. 원본 작업 브랜치·기존 검증 기록은 삭제하지 않는다.

## 2026-11-09 리뷰 반영 패치 지문

아래 SHA256은 패치 파일 자체의 최신 바이트 지문이다. 대상 원문의 적용 전·후 지문은 PR 종합 리뷰와 구현 기록의 재생 검증을 함께 확인한다.

| 패치 | SHA256 |
| --- | --- |
| [cb663da9e4e3-profile_summary.py.patch](cb663da9e4e3-profile_summary.py.patch) | `d1b4118c4b56e1710061cbe7ee274a0a915cae3f9ff7ccc4caf71072c82bf685` |
| [create-test_profile_outbox_worker.py.patch](create-test_profile_outbox_worker.py.patch) | `4d1757786dc3bae30b6b28e24e2a49db0f5e133be45ea0a8795eb7ada0c1beee` |
| [create-test_profile_refresh_outbox.py.patch](create-test_profile_refresh_outbox.py.patch) | `8d962c2be72795b5f9757fcbd48235738af6fbf32e7ccb5da93ca1acdbd29ae6` |
| [restore-profile-outbox-producer-service.py.patch](restore-profile-outbox-producer-service.py.patch) | `e25c34f5cea7c51ac9344b521e0ba585a5a01945bed50b2139e8636616052560` |
| [restore-report_generate.py.patch](restore-report_generate.py.patch) | `81eaa55cd0782ac4586298499641ecc4b3fa467c15c221f39ad2f77ce9fec556` |
| [restore-test_report_generate.py.patch](restore-test_report_generate.py.patch) | `0711e10435cade101308ba380dfcd68d5456ca09d7c8ed3373b43db07b205e7a` |
| [restore-test_report_worker.py.patch](restore-test_report_worker.py.patch) | `32cc4cf86a01723afde8bbece811a8cdf816ef08f9f2ec3bc18e2ffc149fb10c` |

적용 전 `git apply --check`와 실제 적용 후 검증을 모두 수행한다. 부분 활성화하지 않으며, 전체 소비자·모델·마이그레이션과 해당 테스트가 활성 소스에 반영되고 후속 패치의 preimage를 갱신해 재검증한 뒤에만 사용을 마친 패치를 제거한다. Draft·후속 패치 존재는 단독 실행 완료를 뜻하지 않는다.

</details>
