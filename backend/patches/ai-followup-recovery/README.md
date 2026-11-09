# 답변을 보존하는 면접 질문 복구 후속 변경

기존 미병합 구현을 중복 게시하지 않고 이번 수정 구간만 보존한 패치다.
이 파일을 게시해도 서비스 코드에 자동 적용되거나 기능이 활성화되지는 않는다.

선행 PR: #213, #216, #219. 모든 PR의 base는 develop이다.
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
| `backend/app/features/interview/router.py` | [d3cce1cfc381-router.py.patch](d3cce1cfc381-router.py.patch) | `5e52ad30e3aa1fb5936d923996be7f5ea250272fc0ee731c4b7889fd73198e48` | `3dac43512b0b0b579c551b1777f3f2428d4c43787c9e73266f594e5e1b977af4` |
| `spec/ai/decisions/README.md` | [eb612b16a70e-README.md.patch](eb612b16a70e-README.md.patch) | `281c4fe4c3376c88bd63ed5ac1adac8d9eadd36d2a20274a4d03d67419192150` | `bead44516591531d9d13a76611e7a570ef492900a09f0a43274f03f0e9178e79` |
| `spec/ai/implementation.md` | [ed5a46a04864-implementation.md.patch](ed5a46a04864-implementation.md.patch) | `7701bced0ab27e6d6b2617a86ede40ce1bbb72eecab8bc9a581608191715140e` | `63262a5bf0a6ed7efd3fe2e05de4f252711917ec9a24cac368cf84626a68eb69` |
