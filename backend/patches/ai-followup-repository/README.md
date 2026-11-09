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
