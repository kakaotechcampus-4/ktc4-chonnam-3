# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `13bfc72889f7-test_jd_extract_image.py.patch` | `ai/tests/llm_tasks/test_jd_extract_image.py` | `06bf6f14cc976acff494974058eaebae281b215292a3ae46e50fa38d77d36b7e` | `da443b594084cd34bdb5f92abcdbe4cf34ef68ba0e28f7cdcaf30b6e1f8b180f` | `4f9e994f1faca0bcfaed896c407b1319b285db7a8b62a6831b9e0979786ac85b` |
| `28d69d0462f1-jd_extract_image.py.patch` | `ai/src/devon_ai/llm_tasks/jd_extract_image.py` | `31ceb7a185dac869cbe5a0daf28278673fcee73d75b2d2d7bf9e539229dd3463` | `d300d40e4ba5909c76da7e35e84d92d3d8a753449cdf905093e3a462cdadf319` | `63b21499184e0bc3a9b97dcae963709359a540ee32e40d74bca5d7f97fd87903` |
| `5e608d2d5224-external_source.py.patch` | `backend/app/db/models/external_source.py` | `cef09ee82e98e468dff487ed4db89a2971b013709f6645ab2a721cba22e7136b` | `8dc258b0a63da2534be96925c67317b7492bd2540b7e5f23276fbd6cdd9242b3` | `5bbc8432c3223477b1d1ddf7bd1cd534ef428a5ac8c102ebdd57246957e34a9a` |
| `6f3e3f41beed-test_director_runtime_service.py.patch` | `backend/tests/agents/test_director_runtime_service.py` | `56a4e452a9651a786ab0b65b44e73dcb40f0ecfa8163948a65288453cc6369c3` | `faaf1c8b89e074d0c9cadbf3a47a19137dc65347ca4cfaf46184dfa4527119df` | `d3f2a2d5f84d5f4e699838ed0123572141eeb2a87d33d4fb388abe79d451825d` |
| `750223191335-test_external_knowledge.py.patch` | `backend/tests/features/interview/test_external_knowledge.py` | `6b9b52575178d9580315ad91e48f03686cc043a0e6eec71979bc3eb413d0ef0a` | `093739713c0b98cc25879cb95a329eec34a73c9c5a8249674185cfe123e20edf` | `4a4dd3298818755f8ba920468a582dd41134bc8b290cf7a2105da88b047c1d88` |
| `ae1ce2ad5773-external_knowledge.py.patch` | `backend/app/features/interview/external_knowledge.py` | `7b9e97b5976dd159331f890d1131bdeeef18ff6e9bc9ce1b2107866e720ae878` | `b55366249246f7209960c4087353539bccc7be8d5ee990c86d8649a01580555d` | `3a591af6560a3f472206fcc0bd2fc2bac7538e49b23ef9764b5cd291ff46d947` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

<details>
<summary>이전 안내·과거 기준 지문(현재 적용 지문으로 사용 금지)</summary>

<!-- historical-patch-guidance -->
# 이미지 공고와 공식 자료 수집 보완 후속 변경

기존 미병합 구현을 중복 게시하지 않고 이번 수정 구간만 보존한 패치다.
이 파일을 게시해도 서비스 코드에 자동 적용되거나 기능이 활성화되지는 않는다.

선행 PR: #213, #217. 모든 PR의 base는 develop이다.
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
| `ai/src/devon_ai/llm_tasks/jd_extract_image.py` | [28d69d0462f1-jd_extract_image.py.patch](28d69d0462f1-jd_extract_image.py.patch) | `f174542f9eeca790034bea56b1269e47df5923aab351eab0d08b73827d17e92b` | `c70593b87e320904271f85d4e0cb1275327e1d383a889b988fcd8d3d71767ad5` |
| `ai/tests/llm_tasks/test_jd_extract_image.py` | [13bfc72889f7-test_jd_extract_image.py.patch](13bfc72889f7-test_jd_extract_image.py.patch) | `06bf6f14cc976acff494974058eaebae281b215292a3ae46e50fa38d77d36b7e` | `da443b594084cd34bdb5f92abcdbe4cf34ef68ba0e28f7cdcaf30b6e1f8b180f` |
| `backend/app/db/models/external_source.py` | [5e608d2d5224-external_source.py.patch](5e608d2d5224-external_source.py.patch) | `cef09ee82e98e468dff487ed4db89a2971b013709f6645ab2a721cba22e7136b` | `8dc258b0a63da2534be96925c67317b7492bd2540b7e5f23276fbd6cdd9242b3` |
| `backend/app/features/interview/external_knowledge.py` | [ae1ce2ad5773-external_knowledge.py.patch](ae1ce2ad5773-external_knowledge.py.patch) | `a146a40f4bf22029b31d3f409e934e60341cfa22ea2a163462c97c0007e5fa57` | `9e641adeae41fa2ace16de8e0a328cfd4fbe9f7c8aaee671e1be6ea29eb03882` |
| `backend/tests/agents/test_director_runtime_service.py` | [6f3e3f41beed-test_director_runtime_service.py.patch](6f3e3f41beed-test_director_runtime_service.py.patch) | `56a4e452a9651a786ab0b65b44e73dcb40f0ecfa8163948a65288453cc6369c3` | `faaf1c8b89e074d0c9cadbf3a47a19137dc65347ca4cfaf46184dfa4527119df` |
| `backend/tests/features/interview/test_external_knowledge.py` | [750223191335-test_external_knowledge.py.patch](750223191335-test_external_knowledge.py.patch) | `7bf328e9d98c377dee275309618890e16eab0953177d7b6a73b832c1f2b0c4af` | `6b0abfb4e871ec2320369aa3a57647b12733085535c8a16cfc84b5153b20bf30` |

## 2026-11-09 리뷰 반영 패치 지문

아래 SHA256은 패치 파일 자체의 최신 바이트 지문이다. 대상 원문의 적용 전·후 지문은 PR 종합 리뷰와 구현 기록의 재생 검증을 함께 확인한다.

| 패치 | SHA256 |
| --- | --- |
| [28d69d0462f1-jd_extract_image.py.patch](28d69d0462f1-jd_extract_image.py.patch) | `63b21499184e0bc3a9b97dcae963709359a540ee32e40d74bca5d7f97fd87903` |
| [750223191335-test_external_knowledge.py.patch](750223191335-test_external_knowledge.py.patch) | `4a4dd3298818755f8ba920468a582dd41134bc8b290cf7a2105da88b047c1d88` |
| [ae1ce2ad5773-external_knowledge.py.patch](ae1ce2ad5773-external_knowledge.py.patch) | `35395304faf739d1637369afcd34ec38e37adc0a338958fa8ff6240b7921e674` |

적용 전 `git apply --check`와 실제 적용 후 검증을 모두 수행한다. 부분 활성화하지 않으며, 전체 소비자·모델·마이그레이션과 해당 테스트가 활성 소스에 반영되고 후속 패치의 preimage를 갱신해 재검증한 뒤에만 사용을 마친 패치를 제거한다. Draft·후속 패치 존재는 단독 실행 완료를 뜻하지 않는다.

</details>
