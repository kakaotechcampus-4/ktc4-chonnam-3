# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `d3cce1cfc381-router.py.patch` | `backend/app/features/interview/router.py` | `5e52ad30e3aa1fb5936d923996be7f5ea250272fc0ee731c4b7889fd73198e48` | `3dac43512b0b0b579c551b1777f3f2428d4c43787c9e73266f594e5e1b977af4` | `2ad7d0143b543c8db325649183e7b2b5498ecc6b8d48cdb002b17ec342e5dba3` |
| `eb612b16a70e-README.md.patch` | `spec/ai/decisions/README.md` | `29e7c086217f4d0bd233b1e825998c07d5f24198becd4d177fee9b53ed07ee14` | `30fa32d84d8d475b32ebb2cf5bc1d5f4787a6851e6e70ad86111045ae45b6554` | `12eccc62e0574f1a02a84e571d012511dc1d05463d31addc6d7cb3db09515c54` |
| `ed5a46a04864-implementation.md.patch` | `spec/ai/implementation.md` | `73f11f4480999e2f12b3d6357dcbf6dc282c5d9038546596e8b40747f47b1008` | `1cc79f279ae8b1bbbbb52de322078e100c8ce8146ba557b48d0ae6cd4bddcd99` | `bdfb249894a8455255349e212c7e44bf7f4a018b555cced8e71cc0638c881e9b` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

<details>
<summary>이전 안내·과거 기준 지문(현재 적용 지문으로 사용 금지)</summary>

<!-- historical-patch-guidance -->
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

## 2026-11-09 리뷰 반영 패치 지문

아래 SHA256은 패치 파일 자체의 최신 바이트 지문이다. 대상 원문의 적용 전·후 지문은 PR 종합 리뷰와 구현 기록의 재생 검증을 함께 확인한다.

| 패치 | SHA256 |
| --- | --- |
| [eb612b16a70e-README.md.patch](eb612b16a70e-README.md.patch) | `12eccc62e0574f1a02a84e571d012511dc1d05463d31addc6d7cb3db09515c54` |
| [ed5a46a04864-implementation.md.patch](ed5a46a04864-implementation.md.patch) | `bdfb249894a8455255349e212c7e44bf7f4a018b555cced8e71cc0638c881e9b` |

적용 전 `git apply --check`와 실제 적용 후 검증을 모두 수행한다. 부분 활성화하지 않으며, 전체 소비자·모델·마이그레이션과 해당 테스트가 활성 소스에 반영되고 후속 패치의 preimage를 갱신해 재검증한 뒤에만 사용을 마친 패치를 제거한다. Draft·후속 패치 존재는 단독 실행 완료를 뜻하지 않는다.

</details>
