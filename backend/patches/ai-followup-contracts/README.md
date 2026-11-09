# 면접 질문 복구 API 계약 후속 변경

기존 미병합 구현을 중복 게시하지 않고 이번 수정 구간만 보존한 패치다.
이 파일을 게시해도 서비스 코드에 자동 적용되거나 기능이 활성화되지는 않는다.

선행 PR: #212. 모든 PR의 base는 develop이다.
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
| `frontend/docs/api-spec.md` | [e4690d14d501-api-spec.md.patch](e4690d14d501-api-spec.md.patch) | `11a7cb8936ba82a90415de76c06eedd3c02092a3650324a8df733eb310d56502` | `9688feb5c32e3c0c8247e55f180ea4dfa2a9010edb3a4308b3440d8069d6a458` |
| `spec/shared/contracts/openapi.yaml` | [64dd8fdd67b5-openapi.yaml.patch](64dd8fdd67b5-openapi.yaml.patch) | `38b427483a1ecfec7fba7bbab1521134329038c86ef4b83dd5a593673235fb20` | `559ee7bcf7655067c70d744604487c6ef4512dd77a2134221ad3009adb09407a` |
