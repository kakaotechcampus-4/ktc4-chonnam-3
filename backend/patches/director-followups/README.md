# Director Context·L2 후속 패치

## 2026-10-29 수동 적용 후 상태

최신 `develop` `2fc0103`에는 #126과 공통 gateway가 병합돼 있다. 아래 2026-10-28 기록은
당시 판단의 이력이다. 이번에는 패치 1·2·3의 원문 SHA-256, 대상 base/result blob과 gateway
API를 대조한 뒤 일반 Python 코드에 수동 반영했다. `manifest.json`의 `applied_in`이 실제
적용 커밋을 가리킨다. 세 패치의 `application_required`는 이제 `false`이며 재적용하지 않는다.
패치 4도 계속 보관 전용이다. 원본 패치와 과거 base·선행 참조는 변경하지 않았다.

현재 질문/답변 분리·9번째 턴, L2 공유 예산·완료 시도 보존·취소·원문 한계 전달을 새 회귀로
검증했다. 수집 항목이 정확히 상한이고 미방문 디렉터리가 남는 경계도 추가 보완했다.
실행 결과와 후속 실행 PR의 의존성은 `spec/ai/implementation.md`에 기록한다.

## 아래는 적용 전 검토·재현 기록

이 디렉터리는 **Python 소스에 자동 적용하지 않는 검토 자료**다. 적용 대기인 패치 1·2·3과
이미 선행 코드에서 해결돼 이력으로만 보존하는 패치 4를 함께 둔다. 미병합 선행 파일 전체를
복사하지 않고 신규 수정 구간을 보존한다. 자료가 병합돼도 앱·worker·빌드·CI는 패치를 실행하지 않는다.

## 대상과 선행

| 번호 | 대상 | 상태와 범위 | 선행 확인 |
| --- | --- | --- | --- |
| 1 | `agent_context.py` | 수동 적용 대기. 현재 답변 Context·9번째 답변·실제 미확인 범위 | #82 대상 blob 및 Context 계약 |
| 2 | `answer_context.py` | 수동 적용 대기. 현재 질문 loader와 반환형 | #126 대상 blob 및 패치 1의 결과 |
| 3 | `repo_deep.py` | 수동 적용 대기. 공유 budget·호출 기록·수집 한계 전달 | #119·#114와 gateway `attempt_sink` API·기록 동작 |
| 4 | Director `agent.py` | **적용하지 않음.** base URL 보완의 역사적 원형 | #82에서 이미 반영, 아래 보관 사유 참조 |

`manifest.json`에는 대상 경로, 선행 PR/head, 정확한 base/result Git blob과 패치 SHA-256을
기록한다. **`application_required: true`인 항목만 적용 후보**다. 번호가 있다는 이유로 패치 4까지
일괄 적용하지 않는다. 선행 commit과 `validation_reference`는 관찰 기준이며 자동 병합 지시가 아니다.

2026-10-28의 기준 develop은 `4e511a992d7954fa310146bcba2f2d4c6358fb69`다. #82·#114·#119는
병합됐고 #126은 미병합이다. #82 `fcbacd2`·#119 `255d31f`·#126 `d0293ec`에서 해당 대상 blob이
manifest의 base와 같은 것을 확인한 참조다. 선행이 바뀌면 이 상태를 그대로 적용하지 않는다.

패치 3의 base는 #119 리뷰 수정본의 adapter다. 직접/프록시 base URL 전달은 선행 #119에
포함되므로 패치 3에서 다시 추가하지 않는다. 공유 budget·호출 기록·수집 한계 전달만
후속 범위이며, 같은 최종 파일을 유지하도록 호출 인자의 배치만 맞춘다.

패치 3은 공통 gateway의 `attempt_sink` 인자와 완료 시도 보존 동작을 요구한다. 과거 #114 단독에는
이 보완이 없었지만 위 develop에는 #82의 보완이 포함돼 있다. 현재 함수를 확인하지 않고 hook을
중복 구현하거나, 과거 구성의 실패를 현재 실행 결과로 사용하지 않는다.

여기서 호출 기록 hook은 `call_model`의 API다. 패치를 앱 실행 중 자동 적용하는 hook은 제공하지
않는다. 이전 manifest의 `no runtime hook` 표현도 자동 적용이 없다는 뜻으로 구분한다.

## 적용 조건

1. 일반 코드에 반영할 PR의 작성자가 `application_required`와 실제 선행 병합·head를 확인한다.
   필요한 미병합 구현은 별도 로컬 환경에서만 결합하고 게시본에 복사하지 않는다.
2. 패치 3은 **적용 전에** 현재 `call_model`이 `attempt_sink` keyword를 받는지 확인한다.
   완료 시도를 sink에 추가하는 코드와 gateway 회귀 검사도 확인한다. API나 동작이 없으면 중단하며,
   blob·SHA·apply check가 통과해도 이 조건을 대신하지 못한다.
3. LF 원문을 기준으로 대상의 `git hash-object`가 `base_blob`과 같은지 확인하고 패치의 SHA-256을
   대조한다. 적용 후보 1·2·3만 필요한 순서로 `git apply --check <patch>`를 실행한다.
4. 검토한 패치를 적용한 뒤 대상 blob이 `result_blob`과 같은지 확인한다. 패치 2는 최신 #126의
   대상 파일과 패치 1의 결과가 전제다. 선행 파일이 없는 상태를 임시 구현으로 채우지 않는다.
5. 적용 후 패치 3의 실제 gateway 경계에서 다음을 검증한다. 선언된 인자 유무만으로 끝내지 않는다.
   - 성공·재시도의 완료 metadata가 sink에 남고, 후속 시도 중 실제 task 취소에도 이전 기록을 보존한다.
   - 선택·L2가 같은 budget을 공유해 총 두 시도를 넘지 않으며, 의미 검증 종료 후 재호출하지 않는다.
   - `source_limitations`가 실제 모델 payload에 전달되고 직접·프록시 목적지 설정을 보존한다.
6. Context·현재 질문·9번째 답변·원문 한계의 회귀 검사와 실제 소비 service를 재검증한다.
   필요한 단독·선행 결합 결과와 미실행 범위를 나누어 기록한다.
7. 일반 코드 후속 PR로 반영할 때 미적용 자료와 중복되지 않도록 상태·적용 commit을 갱신한다.

base가 다르면 자동·강제·모호한 적용을 하지 않고 신규 선행에 맞춰 패치와 검증을 갱신한다.
선행 코드·테스트·의존성은 이 PR에 포함하지 않는다. 원본 전체는
`backup/director-unpublished-before-pr-20261025`와 기존 로컬 worktree에 보존한다.

## 패치 4의 보관 사유

현재 `agent.py`의 `generate_question`은 #82에서 이미 `base_url=settings.llm_base_url`을 전달한다.
현재 blob `23eb17818e23de6b2fac28854438f466e387c363`은 패치 4가 전제한 옛 결합 파일의 base와 다르다.
최신 #126은 기존 생성기를 이 파일에 두고 새 `execute_director`를 `runtime_adapter.py`로 분리한다.

패치 4의 파일·SHA·base/result·옛 선행 참조는 역사적 재현용으로 그대로 보존한다. 빈 패치나 성공을
위장하는 no-op으로 바꾸지 않는다. 이미 충족한 한 줄을 다시 추가하거나 옛 결합 파일을 되살리지 않는다.

## 재확인 책임과 시점

manifest의 `owner_role`은 실제 사람을 새로 지정하는 값이 아니라 적용 작업의 책임 범위다.
각 대상의 일반 코드 적용 PR 작성자가 다음 변경을 확인하고 `refresh_on`에 따라 갱신한다.

- 패치 1: #82 head·병합, Context 파일·저장 계약 변경.
- 패치 2: #126 head·병합, 패치 1 결과·답변 Context·현재 턴 계약 변경.
- 패치 3: #119·gateway head·병합, L2 base·호출 인자·시도 기록·예산 계약 변경.
- 보관 패치 4: 이후 Director 모듈 배치·기존 생성기의 base URL 동작 변경. 적용 대상으로 자동 복원하지 않는다.

실행 service에 의존하는 회귀 검사는 별도 면접 실행 구현 PR에 둔다. 패치 자료 단독 검사는
해시·형식·정확한 선행에 대한 적용 가능성을 확인하며 모델 품질·서비스 실행 성공을 뜻하지 않는다.
실제 검증 결과는 관련 실행 PR의 `spec/ai/implementation.md` 한 곳에 기록한다.
