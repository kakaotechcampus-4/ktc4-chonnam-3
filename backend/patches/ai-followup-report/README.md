# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `1754dffffbe0-history.py.patch` | `backend/app/features/report/history.py` | `85eb48f2d4d2fab43eb08709421c83fda30881170e126f8126a1d38a126be2a8` | `dd63b3a5451916f744641b9a0dfbc849284397abf766e3eccc6733148db8f7d4` | `7c80c0f2b33351cdf8bbc60935db9ec0d0731aff9da8705503cfd5f8e02763f0` |
| `26ffa57af361-test_report_history.py.patch` | `backend/tests/features/report/test_report_history.py` | `37032638637fa66c4a865d9740d0d7abaadccf5d5bc7cb4173000f2039d34595` | `6ed0a4cb5a4192722ea09a5df650daaf8acb8ba41a4b95ead015b30d3d1f6910` | `161906af6dc3d67adcefcdf2e49ddef5295f64b76ffceab93855cd0960f2ecd6` |
| `3e5dd61dfcf2-report.py.patch` | `ai/src/devon_ai/llm_tasks/report.py` | `e462dd96f8242779f8ac13be614cb8f5341180fa3530beb7e13f3e274889da74` | `4a1ac1f7bb6ab77b5832a4622213ca6137d4b116a80511d3dd24780ac5f402e8` | `2ca3016d0e56551f8e2c678a848d29747766df7bd5003dcab382a13300dfaa33` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 리포트 outbox 생산자·3인수 worker·reaper 등록·ProfileRefreshRequest/0012·전용 회귀는 함께 활성화한다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

<details>
<summary>이전 안내·과거 기준 지문(현재 적용 지문으로 사용 금지)</summary>

<!-- historical-patch-guidance -->
# 리포트의 JD와 당시 검증 경로 호환 후속 변경

기존 미병합 구현을 중복 게시하지 않고 이번 수정 구간만 보존한 패치다.
이 파일을 게시해도 서비스 코드에 자동 적용되거나 기능이 활성화되지는 않는다.

선행 PR: #218. 모든 PR의 base는 develop이다.
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
| `ai/src/devon_ai/llm_tasks/report.py` | [3e5dd61dfcf2-report.py.patch](3e5dd61dfcf2-report.py.patch) | `0ed3deeaba370f7cd434cfa70d8839844edc90b9ca4b9c238a891ef27d1a11f0` | `632c805ac735d75f7a3b91e417a72e3b6fbe057231d4f53c8195219967fd5e29` |
| `backend/app/features/report/history.py` | [1754dffffbe0-history.py.patch](1754dffffbe0-history.py.patch) | `85eb48f2d4d2fab43eb08709421c83fda30881170e126f8126a1d38a126be2a8` | `dd63b3a5451916f744641b9a0dfbc849284397abf766e3eccc6733148db8f7d4` |
| `backend/tests/features/report/test_report_history.py` | [26ffa57af361-test_report_history.py.patch](26ffa57af361-test_report_history.py.patch) | `37032638637fa66c4a865d9740d0d7abaadccf5d5bc7cb4173000f2039d34595` | `6ed0a4cb5a4192722ea09a5df650daaf8acb8ba41a4b95ead015b30d3d1f6910` |


<!-- review-fixes-b:atomic-bundle -->
## 이번 리뷰 반영과 적용 조건

현재 폴더는 실행 중인 기능이 아닌 후속 변경이다. 아래 지문은 UTF-8 LF 기준이며 `없음`은 신규 파일을 뜻한다. 파일을 읽었다는 사실이나 패치 보관만으로 적용 완료로 보지 않는다.

#218의 LinkedRequirement 보완을 먼저 반영한 새 preimage를 사용한다. 점수 턴에는 질문이 연결한 JD만 주며 원문 source notes의 위치·한계는 보존한다. 원래 full source를 직접 복사해 선행 구현을 다시 게시하지 않는다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | 재생 |
| --- | --- | --- | --- | --- |
| `1754dffffbe0-history.py.patch` | `backend/app/features/report/history.py` | `85eb48f2d4d2fab43eb08709421c83fda30881170e126f8126a1d38a126be2a8` | `dd63b3a5451916f744641b9a0dfbc849284397abf766e3eccc6733148db8f7d4` | 통과 |
| `26ffa57af361-test_report_history.py.patch` | `backend/tests/features/report/test_report_history.py` | `37032638637fa66c4a865d9740d0d7abaadccf5d5bc7cb4173000f2039d34595` | `6ed0a4cb5a4192722ea09a5df650daaf8acb8ba41a4b95ead015b30d3d1f6910` | 통과 |
| `3e5dd61dfcf2-report.py.patch` | `ai/src/devon_ai/llm_tasks/report.py` | `e462dd96f8242779f8ac13be614cb8f5341180fa3530beb7e13f3e274889da74` | `4a1ac1f7bb6ab77b5832a4622213ca6137d4b116a80511d3dd24780ac5f402e8` | 통과 |

선행 PR의 실제 병합 커밋에 3-way 재기준한 뒤 적용하고, 충돌을 해결한 최종 원문·테스트·SHA256을 대조한다. 모델/API 호출 없이 통과한 로컬 회귀와 실제 운영 검증은 구분한다. 적용 커밋·입력/출력 지문·통합 회귀를 `spec/ai/implementation.md`에 남긴 후에만 패치를 제거한다. 원본 작업 브랜치·기존 검증 기록은 삭제하지 않는다.

## 2026-11-09 리뷰 반영 패치 지문

아래 SHA256은 패치 파일 자체의 최신 바이트 지문이다. 대상 원문의 적용 전·후 지문은 PR 종합 리뷰와 구현 기록의 재생 검증을 함께 확인한다.

| 패치 | SHA256 |
| --- | --- |
| [3e5dd61dfcf2-report.py.patch](3e5dd61dfcf2-report.py.patch) | `2ca3016d0e56551f8e2c678a848d29747766df7bd5003dcab382a13300dfaa33` |

적용 전 `git apply --check`와 실제 적용 후 검증을 모두 수행한다. 부분 활성화하지 않으며, 전체 소비자·모델·마이그레이션과 해당 테스트가 활성 소스에 반영되고 후속 패치의 preimage를 갱신해 재검증한 뒤에만 사용을 마친 패치를 제거한다. Draft·후속 패치 존재는 단독 실행 완료를 뜻하지 않는다.

</details>
