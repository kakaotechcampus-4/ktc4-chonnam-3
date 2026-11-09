# 현재 리뷰 보완과 적용 조건

선행은 #213·#216·#222이며 prepare 연결에는 #174가 필요합니다. #222의 실제 request_size 구현을 재사용하며 복사하지 않습니다.

선정 입력은 byte·enum 개수·enum 문자 수를 함께 제한합니다. 기본 900개·14,000자는 선택한 공급자에 맞춰 설정하는 보수적 상한이며 모든 모델의 지원 보장이 아닙니다. 구조 안내는 개수와 최대 8개 예시만 모델에 전달합니다.

전체 관찰은 RepoAnalysis.result의 _source_inventory에 고정 SHA·프롬프트별로 한 번 보존합니다. 세션에는 개수·지문·참조만 둡니다. 캐시는 같은 inventory를 재사용하며, 동시 생성한 다른 목록을 덮거나 기록하지 않은 후보를 게시하지 않습니다. 조회 후보와 원문 Evidence는 계속 분리합니다.

실제 prepare·수집기와 그 DB 회귀는 패치로 함께 보존합니다. 적용 전에는 해당 기능의 단독 완료를 뜻하지 않습니다. ADR 0040은 Director 입력에 관한 #223의 구현과 연결하며, 구조·예산 기준은 #225의 ADR 0039도 함께 검토합니다.

이번에 개별 재생한 패치만 아래에 적습니다. 각 원문에서 git apply --check·실제 적용·목표 SHA 대조를 통과했으며 전체 PR 순서 적용·서비스 통합 통과를 뜻하지 않습니다. 나머지 기존 코호트 패치는 선행 통합 후 재기준·검증해야 합니다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `29c447117dc4-repository_sources.py.patch` | `backend/app/features/interview/repository_sources.py` | `b197cbb51beb3bc55cdbd5e221d66d0105cd2c2e6306530dbe7587a1cb75470a` | `f7e7034c6ff7be641a241be388eaa2252a055d322b3037f84c1e523393dff866` | `c7e1e0a9d3365b9ee9359e41c22aa70f37ad1cbbeef01a218cfa330d602381f4` |
| `896f516bdbe0-prepare.py.patch` | `backend/app/features/interview/prepare.py` | `42cbdb959294f8e3a71c239fd08ceb3e01e58fc7289f01d3406afcdf103f8053` | `f81f8de3d8699845e6f43d7c38ea08f10c46bb071a6b83450c9b0337e91d7601` | `c1bf13e5ae2e4133f5b51f7b46fffadf021a5574a1ad7edff61fe7948707b9bb` |
| `b2df3500563e-source_segments.py.patch` | `backend/app/features/interview/source_segments.py` | `f3eaa4fcf63ed65d1c2edfe78fcd6d7f76f04491ed2c060670269d3319eefe1e` | `2fc172caa93902793f31683e7b41736299f79e5581554a6fece05ee5e603949b` | `37d8c6c4abc8a4ad26d7c0a2d94bdc254e1f25cc9c47b65bbeccb0597f0e0a6f` |
| `f15fc4d1956e-test_repository_segments.py.patch` | `backend/tests/agents/test_repository_segments.py` | `3a2ee1cf84b7f29dbc8feb61f975e925f5b5d83992eb1e26cdce233c0239939c` | `26249a37e3f39a35641f1a3591c77cf70c8b50d63c2dce5dca078976aff42fd3` | `1a4b218c9c83be3be4d97ae3f178e28ff99beed632db52a1dbb6ecabd5f41813` |
| `f27faad1e842-test_director_repository_sources.py.patch` | `backend/tests/agents/test_director_repository_sources.py` | `501a93570035e02049a0677a09c47d7046ffd37c0a43e9fec4d3c9e69e4470a5` | `fdd431d91b881511158cc7fabe6ff11f7175b759ff4464a4d51338822f239b5a` | `90c6fca2ed083e670036778610f93e77a841a5a4429f57cb9211c85df7436592` |
| `create-test_repository_inventory_storage.py.patch` | `backend/tests/agents/test_repository_inventory_storage.py` | `없음` | `d784d9669abe63a42454482f8952aac75e0980ea7152db6adb76f8eebf00d553` | `32b5bbff15131b6b757291579dcadb0d383648291e9de1cccd282b8d3d133f5d` |

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
