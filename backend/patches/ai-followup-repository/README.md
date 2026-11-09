# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `29c447117dc4-repository_sources.py.patch` | `backend/app/features/interview/repository_sources.py` | `b197cbb51beb3bc55cdbd5e221d66d0105cd2c2e6306530dbe7587a1cb75470a` | `638c0422df2a68c0ce1cbcfc563e05d2d5c9f410591eb289e2df94d4fdd249e6` | `b5188a43849f8267d6a20f676efb467031b894e854dac3aad46b943037aa7f8f` |
| `896f516bdbe0-prepare.py.patch` | `backend/app/features/interview/prepare.py` | `42cbdb959294f8e3a71c239fd08ceb3e01e58fc7289f01d3406afcdf103f8053` | `a1e55e5795a6e078b10d16911db8edf3f236aa32cc8f1b3ba55758fe79e5b75c` | `8c8177156d1a0ab5651de85feb63a9432a80d97d508b4341de7a9598d282bb88` |
| `b2df3500563e-source_segments.py.patch` | `backend/app/features/interview/source_segments.py` | `f3eaa4fcf63ed65d1c2edfe78fcd6d7f76f04491ed2c060670269d3319eefe1e` | `2fc172caa93902793f31683e7b41736299f79e5581554a6fece05ee5e603949b` | `37d8c6c4abc8a4ad26d7c0a2d94bdc254e1f25cc9c47b65bbeccb0597f0e0a6f` |
| `f15fc4d1956e-test_repository_segments.py.patch` | `backend/tests/agents/test_repository_segments.py` | `3a2ee1cf84b7f29dbc8feb61f975e925f5b5d83992eb1e26cdce233c0239939c` | `26249a37e3f39a35641f1a3591c77cf70c8b50d63c2dce5dca078976aff42fd3` | `1a4b218c9c83be3be4d97ae3f178e28ff99beed632db52a1dbb6ecabd5f41813` |
| `f27faad1e842-test_director_repository_sources.py.patch` | `backend/tests/agents/test_director_repository_sources.py` | `501a93570035e02049a0677a09c47d7046ffd37c0a43e9fec4d3c9e69e4470a5` | `5074e9ea4074d0e80d48a025ba0cb8b49af201ac05eaa65b07c4e7067fc0c195` | `fa60799efcc57206b8448a0ff394d65c7167cf27cd0aa00e39da5894813f0c6d` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

<details>
<summary>이전 안내·과거 기준 지문(현재 적용 지문으로 사용 금지)</summary>

<!-- historical-patch-guidance -->
# 레포 원문 선정과 구간 읽기 후속 변경

기존 미병합 구현을 중복 게시하지 않고 이번 수정 구간만 보존한 패치다.
이 파일을 게시해도 서비스 코드에 자동 적용되거나 기능이 활성화되지는 않는다.

선행 PR: #213, #216. 모든 PR의 base는 develop이다.
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
| `backend/app/features/interview/prepare.py` | [896f516bdbe0-prepare.py.patch](896f516bdbe0-prepare.py.patch) | `4711aa7456dcb3d632f555677e717f26e3e1e77e1c4c393c4e4d0cbc418b294b` | `ea809c763f4636ecb374fec9b157fcb99d6cb626d78f91e34b8d1cf66bf3bde4` |
| `backend/app/features/interview/repository_sources.py` | [29c447117dc4-repository_sources.py.patch](29c447117dc4-repository_sources.py.patch) | `b197cbb51beb3bc55cdbd5e221d66d0105cd2c2e6306530dbe7587a1cb75470a` | `638c0422df2a68c0ce1cbcfc563e05d2d5c9f410591eb289e2df94d4fdd249e6` |
| `backend/app/features/interview/source_segments.py` | [b2df3500563e-source_segments.py.patch](b2df3500563e-source_segments.py.patch) | `f3eaa4fcf63ed65d1c2edfe78fcd6d7f76f04491ed2c060670269d3319eefe1e` | `2fc172caa93902793f31683e7b41736299f79e5581554a6fece05ee5e603949b` |
| `backend/tests/agents/test_director_repository_sources.py` | [f27faad1e842-test_director_repository_sources.py.patch](f27faad1e842-test_director_repository_sources.py.patch) | `501a93570035e02049a0677a09c47d7046ffd37c0a43e9fec4d3c9e69e4470a5` | `5074e9ea4074d0e80d48a025ba0cb8b49af201ac05eaa65b07c4e7067fc0c195` |
| `backend/tests/agents/test_repository_segments.py` | [f15fc4d1956e-test_repository_segments.py.patch](f15fc4d1956e-test_repository_segments.py.patch) | `3a2ee1cf84b7f29dbc8feb61f975e925f5b5d83992eb1e26cdce233c0239939c` | `26249a37e3f39a35641f1a3591c77cf70c8b50d63c2dce5dca078976aff42fd3` |

## 2026-11-09 리뷰 반영 패치 지문

아래 SHA256은 패치 파일 자체의 최신 바이트 지문이다. 대상 원문의 적용 전·후 지문은 PR 종합 리뷰와 구현 기록의 재생 검증을 함께 확인한다.

| 패치 | SHA256 |
| --- | --- |
| [896f516bdbe0-prepare.py.patch](896f516bdbe0-prepare.py.patch) | `8c8177156d1a0ab5651de85feb63a9432a80d97d508b4341de7a9598d282bb88` |

적용 전 `git apply --check`와 실제 적용 후 검증을 모두 수행한다. 부분 활성화하지 않으며, 전체 소비자·모델·마이그레이션과 해당 테스트가 활성 소스에 반영되고 후속 패치의 preimage를 갱신해 재검증한 뒤에만 사용을 마친 패치를 제거한다. Draft·후속 패치 존재는 단독 실행 완료를 뜻하지 않는다.

</details>
