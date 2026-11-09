# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `api-spec-rest-contracts.md.patch` | `frontend/docs/api-spec.md` | `faf2c0c2374c91878add376844b5aa91635f70cee8402903cd3f3cdc8b5851ee` | `ae94a2d78da0a6f6ec3591f2ee82267d2a6bdd04d6b16584dcb65a4a909c7841` | `6896fb0e63124fd329b5d7e723acdea5701c8cec8f785f484798551c8cbdfcc5` |
| `report-revision-contract-test.py.patch` | `backend/tests/contract/test_report_revision_contract.py` | `9ccaf330d4423c9d4c09f53ca2f08674a59ee4d69fcf4ad125a5ff17b032bd16` | `c01be62e652d9bdbb1aeea8563540e25f5ac2938e79f3f3bab4e71657e96fdca` | `f2115b9a0b621a97f944a91f51aa28cffb795c1d26b33351f1358bd7b48c3dff` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 새 REST OpenAPI·FE 설명·REST 회귀는 함께 반영한다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

<details>
<summary>이전 안내·과거 기준 지문(현재 적용 지문으로 사용 금지)</summary>

<!-- historical-patch-guidance -->
# 적용 대기 패치


<!-- review-fixes-b:atomic-bundle -->
## 이번 리뷰 반영과 적용 조건

현재 폴더는 실행 중인 기능이 아닌 후속 변경이다. 아래 지문은 UTF-8 LF 기준이며 `없음`은 신규 파일을 뜻한다. 파일을 읽었다는 사실이나 패치 보관만으로 적용 완료로 보지 않는다.

새 REST 설명·OpenAPI·REST 계약 회귀는 한 묶음으로 적용한다. 활성 FE 문서는 현재 develop REST 계약과 WS details 설명만 반영한다. 리포트 revision/retry 설명은 #228과 중복 게시하지 않는다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | 재생 |
| --- | --- | --- | --- | --- |
| `api-spec-rest-contracts.md.patch` | `frontend/docs/api-spec.md` | `faf2c0c2374c91878add376844b5aa91635f70cee8402903cd3f3cdc8b5851ee` | `ae94a2d78da0a6f6ec3591f2ee82267d2a6bdd04d6b16584dcb65a4a909c7841` | 통과 |
| `report-revision-contract-test.py.patch` | `backend/tests/contract/test_report_revision_contract.py` | `9ccaf330d4423c9d4c09f53ca2f08674a59ee4d69fcf4ad125a5ff17b032bd16` | `c01be62e652d9bdbb1aeea8563540e25f5ac2938e79f3f3bab4e71657e96fdca` | 통과 |

선행 PR의 실제 병합 커밋에 3-way 재기준한 뒤 적용하고, 충돌을 해결한 최종 원문·테스트·SHA256을 대조한다. 모델/API 호출 없이 통과한 로컬 회귀와 실제 운영 검증은 구분한다. 적용 커밋·입력/출력 지문·통합 회귀를 `spec/ai/implementation.md`에 남긴 후에만 패치를 제거한다. 원본 작업 브랜치·기존 검증 기록은 삭제하지 않는다.

## 2026-11-09 리뷰 반영 패치 지문

아래 SHA256은 패치 파일 자체의 최신 바이트 지문이다. 대상 원문의 적용 전·후 지문은 PR 종합 리뷰와 구현 기록의 재생 검증을 함께 확인한다.

| 패치 | SHA256 |
| --- | --- |
| [api-spec-rest-contracts.md.patch](api-spec-rest-contracts.md.patch) | `6896fb0e63124fd329b5d7e723acdea5701c8cec8f785f484798551c8cbdfcc5` |
| [report-revision-contract-test.py.patch](report-revision-contract-test.py.patch) | `f2115b9a0b621a97f944a91f51aa28cffb795c1d26b33351f1358bd7b48c3dff` |

적용 전 `git apply --check`와 실제 적용 후 검증을 모두 수행한다. 부분 활성화하지 않으며, 전체 소비자·모델·마이그레이션과 해당 테스트가 활성 소스에 반영되고 후속 패치의 preimage를 갱신해 재검증한 뒤에만 사용을 마친 패치를 제거한다. Draft·후속 패치 존재는 단독 실행 완료를 뜻하지 않는다.

</details>
