# 턴 정책과 전환 구현 기록

상태: 사용자 5번 범위의 순수 정책·전환·Director 연결 구현. BE 저장·종료 연동과 실제 모델은 미검증.

## 기준과 소유권

- 선행 4번이 미병합이므로 `feature/ai-director-question@50f0cc1`에서
  `feature/ai-turn-policy`를 분기했다. PR은 생성하지 않는다.
- 기준은 [텍스트 면접](../features/interviewer.md#고정-9턴-정책),
  [답변 정정](../features/answer-evaluation.md#후속-답변과-정정),
  [정성 평가 결정](../decisions/0004-answer-assessment-policy.md)이다.
- 최신 `origin/develop@ebbe13d`도 대조했다. 최신 명세의 Controller 후보 제한과
  유연한 Persona 배분을 적용하되 다른 브랜치 문서 전체를 병합하지 않는다.
- Controller의 실제 권한·DB 확정·세션 상태·동시성·전송은 BE 소유다. 이번 코드는 BE가
  확정한 기록을 입력받는 순수 계산·검사이며, DB schema나 별도 Agent가 아니다.
- `CLAUDE.md`·`ai/CLAUDE.md`의 기존 backend 경로 안내와 달리, 사용자가 명시한
  `ai/src/devon_ai/` 범위에서 작업했다. BE/FE·보호 파일·의존성은 수정하지 않았다.

## Persona 후보 계산

`allowed_personas(presented)`는 이미 제시한 Persona의 순서 있는 tuple을 받는다.
빈 기록이면 첫 질문 후보는 `hr_manager`만 반환한다. 9개면 후보가 없다.
잘못된 enum·첫 Persona·9개 초과·이미 최소 횟수 달성이 불가능한 기록은 거절한다.

각 후보를 한 번 추가한 뒤 아래 조건을 만족하는 후보만 반환한다.

```text
추가 후 남은 질문 수 = 9 - (이미 제시한 질문 수 + 1)
필요한 기술 질문 수 = max(0, 5 - 추가 후 tech_lead 횟수)
필요한 비기술 질문 수 = max(0, 3 - 추가 후 HR·domain 합산 횟수)
허용 조건 = 필요한 기술 질문 수 + 필요한 비기술 질문 수 <= 남은 질문 수
```

기술 6턴은 Director가 고려할 목표다. 기술 5턴·비기술 4턴도 정상이며 목표를 강제 최소로
바꾸지 않는다. 첫 HR 이후 HR 재선택을 허용하고, HR·domain 각각의 최소치·고정 교대를 두지 않는다.

## 질문 수와 완료 답변 수

`TurnProgress`는 두 종류의 불변 tuple을 보관한다.

- `questions`: BE 질문 ID와 정확히 검증된 질문. tuple 위치가 최초 Turn이다.
- `history`: 답변 처리가 완료된 순서의 기존 `AnalysisHistory`.

질문 수와 완료 답변 수는 각각 기록 길이에서 계산한다. 차이는 0 또는 1이어야 한다.
답변의 Turn·질문 전체가 해당 위치의 제시된 질문과 같아야 하고, 질문 ID는 중복될 수 없다.
복원 입력에도 같은 검사를 적용한다. 기존 질문·Persona를 quota 보정을 위해 고치지 않는다.

| 함수 | 처리 |
| --- | --- |
| `record_question(progress, ready)` | 현재 답변 처리가 끝난 상태에서 허용된 다음 질문 하나를 반영한 새 객체 반환 |
| `complete_answer(progress, record)` | 대기 중인 질문에 해당하는 완료 분석을 한 번 반영한 새 객체 반환 |
| `finish_allowed(progress)` | 9번째 답변 처리까지 끝났을 때만 정상 완료 가능 |
| `plan_question(progress, question_id, contract, remaining_candidates=...)` | 준비된 질문 목적에 다음 Turn·계산한 Persona 권한 연결 |
| `validate_turn_decision(...)` | 기존 DirectorDecision을 계산한 질문·종료 권한으로 검사 |
| `feedback_context(progress)` | 9개 완료 문답의 ID·질문·답변·최초 분석을 피드백용 입력으로 복사 |

`record_question`은 생성 성공을 DB 확정으로 간주하지 않는다. BE가 실제 확정한 뒤 projection에
반영해야 한다. 전송만 실패했다면 BE는 같은 질문을 재전달하며 이 함수를 다시 호출해 턴을 늘리지 않는다.
중복 질문·답변 전환은 거절한다. Tool·재작성·재계획·모델 attempt는 이 전환 함수를 호출하지 않는다.

정상 제출된 답변의 평가가 `not_evaluable`인 것과 처리 실행 자체의 실패는 구분한다.
유효하게 처리된 평가 보류 결과는 완료 기록에 보존할 수 있다. `ModelFailed`는 완료 분석이나
성공 질문으로 변환하지 않는다. 9번째 질문만 보낸 상태에서는 정상 종료도 피드백 입력도 허용하지 않는다.

## Director 연결

기존 `generate_question`에 `progress`를 주입하면 다음 Turn·중복 질문 ID·Persona 권한을
모델 호출 전에 확인한다. 더 좁은 Persona 후보는 허용하지만 quota상 불가능한 후보를 늘릴 수 없다.
이력은 `progress.history`를 사용하며 별도 history와 충돌하면 거절한다. 질문 수·완료 답변 수·
Persona별 횟수·기술 목표 6턴을 입력에 포함한다. 모델 결과를 받는 것만으로 진행 기록을 바꾸지 않는다.

기존 호출 호환을 위해 `progress=None`도 유지한다. 이 경로는 4번처럼 BE가 계산한
QuestionPlan 권한을 전제로 하며 이번 quota·전체 기록 검사를 자동 적용하는 경로가 아니다.
BE 연결 시 `plan_question` → `generate_question(progress=...)` → 현재 상태 재확인·DB 확정 →
`record_question` 순서를 사용한다. 답변 처리 후 `complete_answer`와 계산된 종료 조건을 사용한다.

## 기여 정정과 피드백

“팀원이 구현했습니다”라는 같은 답변도 최초 질문에 따라 다르게 보존한다.

- 역할을 묻는 질문: 역할이 확인됐다는 `sufficient` 분석을 유지한다.
- 직접 구현을 잘못 전제한 질문: `not_evaluable`·충분성 null·전제 정정 이유를 유지한다.

턴 정책이 기여 값만 보고 충분성이나 기술 평가를 다시 판정하지 않는다. 정정 전의 본인 기여 진술과
정정 후의 타인 기여 진술을 각 질문·Turn에 묶어 모두 전달한다. 다른 주제의 역할까지 일괄 변경하지 않는다.
독립 질문 검토가 정정된 전제를 다시 사용하는 후보를 부적절하다고 판단하면 기존 `replan` 분류로 닫는다.

`feedback_context`는 원문·최초 분석·이후 정정을 누락하지 않는 **입력 구성**이다. 실제 리포트 생성·
최종 문장의 정정 반영 품질·점수 계산 완료를 뜻하지 않는다. 의미 판단은 기존 분석 모델·독립 검토기의
책임이고, 이번 검증은 fake 분석·검토를 이용한 기록 보존과 분기 검사다.

## 검증과 남는 범위

- 모든 정상 9턴 Persona 배열을 독립적으로 열거해 각 prefix의 허용 후보와 계산 결과를 대조했다.
- 첫 HR·HR 재선택·기술 5/6회·불가능한 분포·잘못된 타입·중복 ID·잘못된 답변 Turn·질문 변경·
  9번째 질문 대기·9번째 답변 완료·10번째 질문 금지·모델 재시도·재작성 시 기록 불변을 검사했다.
- 두 기여 정정 사례와 stale 전제 재계획, 피드백 입력의 원본 보존을 검사했다.
- 최종 검증 통과: uv locked sync, Ruff check/format(47개 파일), mypy(12개 소스),
  pytest **293 passed / 1 skipped**, git diff --check. 기준선 257개에서 통과 사례 36개를 추가했다.
- 공유 계약 검사 통과: 스키마 2개·부분 OpenAPI·양성/음성 fixture 7개. 실제 runtime·TypeScript
  일치·전체 API 범위·호환성까지 검증한 것은 아니다.
- 독립 코드 리뷰에서 중요·경미 수정 지적이 없었으며 Director 테스트도 85 passed / 1 skipped였다.
- **보류 1건:** 과거 입력을 편집·복구하고 최초 분석을 재평가하는 AI-L09 사례는 명시적 skip이다.
  최신 명세가 채택한 기존 기록 보존·이후 발언 반영과 구분한다. 새 복구 API·재평가 이력을 추가하지 않았다.
- **미실행:** 실제 모델·리포트 품질, BE DB·WS 통합, 종료 경합·중복 전송·재연결 장애 검증.
- **BE 책임:** 사용자 종료 후 결과는 질문 ID·Turn을 현재 DB와 비교해 저장 전에 차단해야 한다.
  AI의 오래된 projection만으로 현재 세션의 종료·권한·중복을 보장할 수 없다.
- **범위 밖:** SDK·점수 산식·새 enum/WS/DB·음성·FE/BE 변경·PR 생성.
