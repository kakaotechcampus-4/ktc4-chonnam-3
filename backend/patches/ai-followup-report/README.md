# 현재 리뷰 보완과 적용 조건

선행은 #213·#218·#216입니다. #197이 이미 반영한 LinkedRequirement의 id·category·text 세 필드와 엄격한 ID 연결을 보존합니다. source_field·tech_tags를 이 계약에 추가하지 않습니다. 잘못된 다섯 필드 기대값은 활성 테스트에서 수정했습니다.

ScoreTurn의 새 ID 필드와 legacy replay 옵션을 사용하는 회귀는 구현과 함께 대기 패치로 보존합니다. 기존 develop 호환 회귀는 활성 상태로 유지합니다. requirements 키 누락은 기본적으로 거절하며, 내부 allow_legacy_requirements=True로 명시한 과거 재현만 빈 목록으로 읽습니다. null·잘못된 값·존재하지 않는 연결 ID는 예외에서도 거절합니다.

과거 기록에 후보 키가 없으면 호환 경로를 유지합니다. 키가 있지만 타입이 손상됐으면 제한 사항을 남기고 조회 권한을 늘리지 않습니다. 실제 인용을 검증할 수 없으면 기존 검증 오류로 거절합니다. 아래 지문은 명시한 로컬 선행 원문에서의 개별 재생 근거이며 최신 develop에 바로 적용된다는 뜻이 아닙니다.

이번에 개별 재생한 패치만 아래에 적습니다. 각 원문에서 git apply --check·실제 적용·목표 SHA 대조를 통과했으며 전체 PR 순서 적용·서비스 통합 통과를 뜻하지 않습니다. 나머지 기존 코호트 패치는 선행 통합 후 재기준·검증해야 합니다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `test_generate_report-legacy-requirements.py.patch` | `ai/tests/llm_tasks/test_generate_report.py` | `21ee3b699d7bdcf7f205b842daaf333cc5ffb62032732459e21eb462625e92ba` | `ca422a9f4bd5a968a8f81027f0f424c2739305eefe03d7c4065892dadcaf0520` | `2a976aa3e3994fd560903a3a07aebb00eb32d4540c1f3f0e59ac39a6298bb75a` |
| `test_report_score-jd-ids.py.patch` | `ai/tests/llm_tasks/test_report_score.py` | `0887808545a0e8855d1cafc94d33793018ec42aec95658a018f4387c53dbab20` | `009de8ab5274dc7d5408d3f9d6d45d7a2e9136bb2f30ead403592592c20dd511` | `31e9deeb2b0a10d166415d71f02e7de459b43169159e6453037d698c8367ae55` |
| `1754dffffbe0-history.py.patch` | `backend/app/features/report/history.py` | `85eb48f2d4d2fab43eb08709421c83fda30881170e126f8126a1d38a126be2a8` | `2a85a0abf22d2157f06e1acad9a98c0ad647be124cd9dd8d83ebfe68ef456447` | `cc955ef05d2a7b2e13fa623a6799fa4ebd7118d9d5cd8f2fd0aad840b4ce38d9` |
| `26ffa57af361-test_report_history.py.patch` | `backend/tests/features/report/test_report_history.py` | `37032638637fa66c4a865d9740d0d7abaadccf5d5bc7cb4173000f2039d34595` | `0d54ab6ccdb92b69d8029021003eac37e2e5f9681b531d14835a573462d12776` | `15179e1d4e7b6136159fa6ad88df28c23e2d5c66f55d2158e7f5325c78bbb0f8` |
| `3e5dd61dfcf2-report.py.patch` | `ai/src/devon_ai/llm_tasks/report.py` | `e462dd96f8242779f8ac13be614cb8f5341180fa3530beb7e13f3e274889da74` | `f38dfa4a457bfc9570fd006aff125a510f972bd07ac213a22df9f9fd8619ff10` | `06608c1c7b2cf96a2ba2ae7a62afe9ec2b27784144830dc97bf4cb811cc1c8be` |

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
