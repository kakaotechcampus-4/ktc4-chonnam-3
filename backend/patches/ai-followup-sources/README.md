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
