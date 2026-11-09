# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `1eccdb2d9ebb-matching.py.patch` | `backend/app/features/analysis/matching.py` | `81c377943edf292b00cf5a310da73e5070acc6c2f65a0f6eac068c642c765c61` | `fc54ce6df69431a9340f9c47fa114588bd9b21701405ad2a6579c9b2bdaf32fa` | `4fd946bc14c80b8f9c8d48190712ea3ac7262efc126a4eae87e45b24690e24ec` |
| `763dbb1ac06a-director_service.py.patch` | `backend/app/features/interview/director_service.py` | `bb554bcb3389547255310f511c84712bcf93e9b4c05338e14e8c4fe8c0ae7822` | `f817f12a2e8a546b177e9eaf0d0ef3db4e058410743e52e8f886609f49241f1b` | `9061ecc83d8d3dd2dffd552b8fdc8d6721cda2f9ee9503441860d372d24ebf64` |
| `904406b85e1e-test_event_wiring_candidates.py.patch` | `backend/tests/features/test_event_wiring_candidates.py` | `f72118275d43fee1e251e8ed76c7e2dc2bcd10c277ff3555e2c90ea91fbae678` | `bef04c6187e880b6c5c08da3e7cc4eae7e3fa0ed12de9e118fa373563ad5cd2d` | `a5090021aa7f4f3314324fa3b137c0afa99a5cb52eff41a396e9a34a1161d863` |
| `a9171c8449d7-test_event_wiring_recommended.py.patch` | `backend/tests/features/analysis/test_event_wiring_recommended.py` | `455d033d55ef1290c3ae8c0f6215a8b0b06a919dfdb0f03c95fe7de98c970386` | `15f212e5e6806eeed03c48e91694e830f60de3ba4b6af42f660f31cff02a2e96` | `04b907e12fff88baa53cd101006772378b0bf10a0472f51065b45a24512d179c` |
| `bff120626f61-interview_prep_reaper.py.patch` | `backend/app/workers/tasks/interview_prep_reaper.py` | `38dba0527f1470dd38da02797e657ce9aac9e68ae9078272cad0daa50f1a88b6` | `1e2a546881adabe99b8007e13109a246d0562eb63ddcc50f4bea63a5dffcb428` | `ebde34d91f926c59f9808be900cdca67d77a794887c184fe1d67d6ceb1c2a4ed` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

<details>
<summary>이전 안내·과거 기준 지문(현재 적용 지문으로 사용 금지)</summary>

<!-- historical-patch-guidance -->
# Director·답변 분석·레포 원문·근거 Tool 후속 변경

이 디렉터리는 미병합 선행 구현에 대한 **이번 신규 수정 구간만** 보존한다.
선행 코드를 다시 복사하지 않으므로 이 PR을 병합하는 것만으로 아래 변경이 실행되지는 않는다.
직접 게시한 새 모듈도 별도 PR의 계약·실행 설정에 의존할 수 있다. 현재 PR은 Draft다.

패치 소유 PR: #216. 아래 표는 이동 후 소유 범위다.

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
| `backend/app/features/analysis/matching.py` | [1eccdb2d9ebb-matching.py.patch](1eccdb2d9ebb-matching.py.patch) | `81c377943edf292b00cf5a310da73e5070acc6c2f65a0f6eac068c642c765c61` | `fc54ce6df69431a9340f9c47fa114588bd9b21701405ad2a6579c9b2bdaf32fa` |
| `backend/app/features/interview/director_service.py` | [763dbb1ac06a-director_service.py.patch](763dbb1ac06a-director_service.py.patch) | `bb554bcb3389547255310f511c84712bcf93e9b4c05338e14e8c4fe8c0ae7822` | `f817f12a2e8a546b177e9eaf0d0ef3db4e058410743e52e8f886609f49241f1b` |
| `backend/app/workers/tasks/interview_prep_reaper.py` | [bff120626f61-interview_prep_reaper.py.patch](bff120626f61-interview_prep_reaper.py.patch) | `38dba0527f1470dd38da02797e657ce9aac9e68ae9078272cad0daa50f1a88b6` | `1e2a546881adabe99b8007e13109a246d0562eb63ddcc50f4bea63a5dffcb428` |
| `backend/tests/features/analysis/test_event_wiring_recommended.py` | [a9171c8449d7-test_event_wiring_recommended.py.patch](a9171c8449d7-test_event_wiring_recommended.py.patch) | `455d033d55ef1290c3ae8c0f6215a8b0b06a919dfdb0f03c95fe7de98c970386` | `15f212e5e6806eeed03c48e91694e830f60de3ba4b6af42f660f31cff02a2e96` |
| `backend/tests/features/test_event_wiring_candidates.py` | [904406b85e1e-test_event_wiring_candidates.py.patch](904406b85e1e-test_event_wiring_candidates.py.patch) | `f72118275d43fee1e251e8ed76c7e2dc2bcd10c277ff3555e2c90ea91fbae678` | `bef04c6187e880b6c5c08da3e7cc4eae7e3fa0ed12de9e118fa373563ad5cd2d` |

실행 결과와 남은 작업의 원본 기록은 `spec/ai/implementation.md`다.
PR 본문의 게시본 검증과 과거 로컬 통합 검증을 구분해서 읽는다.

</details>
