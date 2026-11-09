# 후속 패치 적용 검증

<!-- verified-current-patches -->
아래 표만 현재 게시 payload의 개별 재생 결과다. UTF-8 LF 기준 SHA256이며 `없음`은 신규/삭제 파일이다. `git apply --check` 뒤 별도 sandbox에서 실제 적용하고 선언된 원문 목표와 대조했다. **여러 PR의 전체 순서 적용·서비스 통합 통과를 뜻하지 않는다.**

일부 적용 전 원문은 미병합 선행을 결합한 로컬 기준이다. 지문만 맞춘 대체 코드를 만들거나 선행 구현을 이 PR에 복사하지 않고, 실제 병합된 선행 커밋에서 다시 기준을 확인한다.

| 패치 | 대상 | 적용 전 SHA256 | 적용 후 SHA256 | patch SHA256 |
| --- | --- | --- | --- | --- |
| `d3cce1cfc381-router.py.patch` | `backend/app/features/interview/router.py` | `5e52ad30e3aa1fb5936d923996be7f5ea250272fc0ee731c4b7889fd73198e48` | `3dac43512b0b0b579c551b1777f3f2428d4c43787c9e73266f594e5e1b977af4` | `2ad7d0143b543c8db325649183e7b2b5498ecc6b8d48cdb002b17ec342e5dba3` |
| `eb612b16a70e-README.md.patch` | `spec/ai/decisions/README.md` | `771487d9f51eeccec550483523be3c8e1fe45ce682dc0c2ce35f63662da680de` | `a30de18cec721dacc20cc6e8b88a7b706e5fb2a6ae5aa1816deb5d883e8eed6a` | `7349eb0e7c54338a8dbacc933d92123efe1716f1e0f4c1eeb596633d17dadeaa` |
| `ed5a46a04864-implementation.md.patch` | `spec/ai/implementation.md` | `2a41c9bd9157619eff8f5b3b990c9a70b931b2273d4e6a5b0284cbbfc4d7a018` | `79157ba861293f07b8d5fec6bfb42f44ed834cf402c2012bd47be3e37dd659bf` | `390294213351325dee9973c0ac3fc7d85bb6a0336fb27bfe32bc02f03b0bead2` |
| `review-director-service.py.patch` | `backend/app/features/interview/director_service.py` | `f817f12a2e8a546b177e9eaf0d0ef3db4e058410743e52e8f886609f49241f1b` | `b6965de3df3a2e28fbc8c3441741192481abdf020a5dc147b45261835de038a2` | `b9f678c62d32ff0b3bd0bf8c68aec9cb4671f0ffa76b99a10088be97f8cad1c0` |
| `review-interview-service.py.patch` | `backend/app/features/interview/service.py` | `52945b5051ed2ffc77864d89e76502b2c06a0382fae54063fab62b088ceaf09e` | `851288185dd79311e9759d671e4f0fde2d5861168c0670bc916c62b4e9ddb4ce` | `cd057253c7fcf389c06a4bb5d5c2df99bbceea0213933dc9fc639f43586aaca5` |
| `review-test_question_retry.py.patch` | `backend/tests/agents/test_question_retry.py` | `없음` | `5d6c7cf66842ba44e22ff6ce7b765e25d01026d7e1a1145905644872923ef72a` | `571b0c53e045bd6759015aa0c060ce2a83af5577479aae77667126cfa2a36e26` |
| `review-test_question_retry_prompt_version.py.patch` | `backend/tests/agents/test_question_retry_prompt_version.py` | `없음` | `e1eec6f28043cc239d7d1df3666bac8b6abcc76631a9d6f8340790fbffa8b834` | `6462aed64bb4b2b71b7eacf04a303498282074484eea2a2674d80f613264ecc4` |
| `review-test_question_retry_router.py.patch` | `backend/tests/features/interview/test_question_retry_router.py` | `없음` | `9f40c138db460369c6e6ff0ffa84a5fabc368f78e3d2f61cd0812e751adbf12b` | `e742cb1ab9dff10d8074d309e3732f6a4d9a8ec76994f97b11a1be567857eac8` |

선행의 실제 병합 커밋으로 재기준한 뒤 적용한다. 적용 커밋·지문·통합 회귀를 spec/ai/implementation.md에 기록한 뒤에만 대기 패치를 제거한다.

#213·#216·#223 패치가 실제 코드에 적용될 때까지 director_service·GET availability 호출·라우트와 해당 통합 회귀를 같은 비활성 묶음으로 보존합니다. PR 병합만으로 활성화되지 않습니다. 복구 모듈·선택 응답형·독립 경계 검사는 직접 게시합니다. 원문·T3 재실행 없이 최초 조회 요약과 Tool 결과를 복원하며 과거 성공이 현재 연결을 바꾸지 않습니다. 공통 0011은 #228 소유입니다.

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

공통 0042·0044 색인과 이 재리뷰의 구현 기록은 #222에서 먼저 반영한다. 0040은 #223, 0046은 #225 소유다. 문서 패치는 이 색인 반영 후 적용하며 코드의 실행 의존성과 문서 적용 순서를 구분한다.
