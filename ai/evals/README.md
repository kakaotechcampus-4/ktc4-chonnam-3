# AI 평가 작업 공간

이 디렉터리는 [`spec/ai/verification.md`](../../spec/ai/verification.md)와
[ADR 0007](../../spec/ai/decisions/0007-evaluation-design-policy.md)이 설명하는 평가 작업 공간이다.
로컬 합성 fixture와 비교 방법은 [ADR 0009](../../spec/ai/decisions/0009-ai-evaluation-method.md)를 따른다.

- `inputs/`는 모델이 받을 수 있는 정보만 둔다.
- `expectations/`는 기대·금지 결과와 검수 메모를 둔다. 이 내용은 모델 prompt나 retrieval 입력에
  들어가면 안 된다.

로컬 합성 사례는 이 디렉터리들에 JSON 쌍으로 둔다. 한 쌍은 같은 `case_id`와 `version`을 가지며,
loader는 불일치·중복·짝 없는 파일을 거부해야 한다. 입력 쪽은 실행 payload와 사례·split·source group
제어 정보를 구분한다. 모델에는 실행 payload만 전달한다. 기대값, 검수 정보, 제어 정보는 prompt,
retrieval query, tool 입력에 들어가면 안 된다.

## 용어

- **평가 사례(case)**: `q-0003` 같은 ID 하나다. 입력 파일(`inputs/`)과 기대 파일(`expectations/`)이 같은
  `case_id`와 `version`으로 짝을 이룬다. 입력에는 모델이 받는 `payload`와 제어 정보가, 기대에는 모델에게
  보여 주지 않는 정답 기준과 검수 정보가 있다.
- **종류(`control.kind`)와 ID 접두어**:

| 접두어 | kind | 평가하는 것 | `payload` 내용 |
| --- | --- | --- | --- |
| `e-` | `evidence` | 근거를 찾고 인용하는 능력 | 질문과 자료(`materials`) |
| `q-` | `question` | Director가 다음에 하는 질문 | 현재 턴, 가능한 Persona, 남은 횟수, 대화 이력, 직전 분석, 근거 |
| `f-` | `flow` | 면접 흐름의 적절성(계속·종료 등) | `q-`와 같은 구조 |
| `r-` | `report` | 리포트 생성 결과(서술과 6개 key 점수) | 면접 9턴 전체 대화, 근거, 과제 |

- **split**: `dev`(개발용)와 `holdout`(최종검증용)이다.
- **source group**: 같은 합성 원천에서 만든 사례 묶음(`sg-r1` 등)이다. `dev`와 `holdout`에 함께 둘 수 없다.
- **쌍(pair)**: 질문은 같고 답변만 다른 `report` 사례 두 건(`stronger`, `weaker`)이다. 정확한 점수 대신
  점수의 순서 관계를 검사한다(아래 report 사례).
- **version**: 같은 ID의 내용을 바꿀 때 올리는 번호다(`q-0003.v1`).
- **검수 상태(`review.status`)**: `unreviewed`, `approved`, `pending`, `invalid` 중 하나다(아래 사례 검수).

## 후보 사례 형식

로컬 합성 사례의 후보 형식이다. 파일은 `inputs/{case_id}.v{version}.json`과
`expectations/{case_id}.v{version}.json`이다. 쌍은 파일 이름으로 맺고, 중복과 불일치는 파일 안의
`case_id`와 `version`으로 찾는다.

```json
// inputs/q-0003.v1.json
{"case_id": "q-0003", "version": 1,
 "control": {"kind": "question", "split": "dev", "source_group_id": "sg-r1", "synthetic": true},
 "payload": {}}

// expectations/q-0003.v1.json
{"case_id": "q-0003", "version": 1,
 "allowed": [{"id": "a1", "purpose": "..."}],
 "forbidden": [{"id": "f1", "reason": "...", "type": "..."}],
 "grader_controls": [{"kind": "allowed", "output": "..."}],
 "review": {"status": "unreviewed", "author": null, "reviewer": null,
            "reviewed_at": null, "pending_notes": []}}
```

- `control.kind`는 `evidence`, `question`, `flow`, `report` 중 하나이고 `split`은 `dev` 또는
  `holdout`이다.
- `payload`만 모델에 전달할 수 있다. loader는 `payload` 안을 해석하지 않고 그대로 전달하며, 종류별
  구조는 사례를 쓰면서 정한다.
- `grader_controls[].kind`는 `allowed`, `forbidden`, `ambiguous`, `invalid_ref`, `tool_failure`
  중 하나이다.
- `review.status`는 `unreviewed`, `approved`, `pending`, `invalid` 중 하나이다. 작성자가 아닌 사람이
  실제로 확인하기 전에는 검수자 이름과 날짜를 `null`로 둔다.
- 이 형식은 합성 fixture 전용이다. 데이터베이스나 공개 API 스키마가 아니다.
- `evals/eval_cases.py`는 쌍을 읽고 다음을 거부한다: 짝 없는 파일, 중복, 파일 이름 불일치, 알 수 없는
  키(입력 파일에 기대값이 섞이는 경우 포함), 합성이 아닌 사례, 같은 source group이 `dev`와
  `holdout`에 함께 있는 경우, 작성자 외 검수자가 없는 `approved`(앞뒤 공백을 지우고 대소문자를 무시해
  비교하며, 작성자·검수자·날짜가 공백뿐이어도 거부), 읽을 수 없는 UTF-8 파일(`CaseError`로 알림).
- `evals/grader_check.py`는 승인된 사례의 control 출력으로 채점기를 시험해 control 종류별로 correct,
  false accept, false reject, abstained, error를 센다. 채점기는 control 종류를 보지 못한다. 종류별
  기대 판정은 작성자의 가정이며 팀 확인이 필요하다. 승인됐지만 `grader_controls`가 비어 검사할 출력이
  없는 사례는 전체 수에는 남기고 `evaluated_cases`에서는 빼며 `excluded_cases`에 `no_controls`로 센다.

## report 사례

`control.kind`가 `report`인 사례는 리포트 생성 결과를 평가한다. 서술 기대값은 다른 종류와 같게
`allowed`/`forbidden`에 쓴다. 점수는 정확한 숫자가 아니라 같은 질문에 답변만 다른 두 사례의 **순서
관계**로 검사한다. 점수 기준과 환산표는 `backend/scripts/seed_score_criteria.py`의 `rubric`과
`LEVEL_SCORES`(0단계 0점, 1~4단계 20·45·70·90점)이다.

`payload`는 정상 면접 한 건 전체다.

```json
{"history": [{"turn": 1, "persona": "hr_manager", "question": "...", "answer": "...",
              "question_contract": {"purpose": "...",
                                    "required_points": [{"key": "...", "description": "..."}],
                                    "evaluation_scope": "..."}}],
 "evidence": [{"ref": "...", "path": "...", "lines": "...", "text": "..."}],
 "task": "종합 피드백과 Persona별 피드백, 6개 key 점수를 쓰세요."}
```

- `history`는 정상 완료 면접의 9턴이다. 첫 질문은 `hr_manager`이고 [공통 결정 0008](../../spec/shared/decisions/0008-fixed-persona-allocation.md)에 따라
  `tech_lead` 6턴, `domain_lead` 2턴, `hr_manager` 1턴으로 고정한다. `question`·`flow` 사례의
  `persona_left`는 남은 횟수이며 loader가 이력의 진행 횟수와 합해 6/2/1이 되는지 검사한다.
- 턴마다 `question_contract`가 있어야 한다. 질문을 하기 전에 정한 질문 목적(`purpose`), 요구한 내용
  (`required_points`, key는 질문 안에서 고유), 평가 범위(`evaluation_scope`)이며, 점수 판정이 묻지 않은
  key를 낮게 매기지 않도록 하는 근거다. 실제 Question Contract의 `assumptions`·`basis_refs`는 평가용
  형식에서 뺐다. loader가 모든 `report` 사례에서 이 형식을 검사한다.
- 턴의 선택 필드 `follows`는 그 턴이 후속 질문인 이전 턴 번호다. 있으면 더 앞선 실제 턴이어야 한다.
- 턴의 선택 필드 `evidence_refs`는 그 턴의 질문·평가 근거로 쓴 `evidence`의 `ref` 목록이다. 서술이 인용한
  근거가 인용한 턴에 묶여 있는지 보는 기준이며 없는 ref나 같은 ref를 두 번 쓰면 loader가 거부한다.
- payload의 선택 필드 `tool_results`는 근거 조회 결과다: `{"turn": 6, "status": "tool_error",
  "limitations": ["..."], "error_code": "..."}`. `status`는 `found`·`not_found`·
  `insufficient_analysis`·`tool_error`이고 `tool_error`는 `error_code`와 한계 문구가, `insufficient_analysis`는
  한계 문구가 필요하다. 서술이 조회 실패(`tool_error`)와 찾지 못함(`not_found`)을 구분하는지 보는 기준이다.
- `abandoned` 등 비정상 종료는 리포트를 만들지 않으므로 사례로 두지 않는다.

점수 순서 관계는 `expectations`의 선택 필드 `pair`로 쓴다.

```json
"pair": {"pair_id": "rp-0001", "role": "stronger", "key": "technical_reasoning", "min_gap": 10}
```

- 같은 `pair_id`에 `stronger` 한 건과 `weaker` 한 건이 있어야 한다. 둘 다 `report` 사례이고
  `split`, `source_group_id`, `key`, `min_gap`이 같다.
- 두 사례는 질문·Persona·Turn·`evidence`·`task`가 같고 `answer`만 다르다(loader가 검사한다).
- 통과 조건은 `stronger`의 `key` 점수가 `weaker`보다 `min_gap`점 이상 높은 것이다. 다른 key는 이
  쌍에서 비교하지 않는다. `min_gap` 10은 임시 값이며 실행기로 점수 흔들림을 잰 뒤 다시 정한다.
- 작성 규칙(검수자가 확인): 설계상 두 사례의 `key` 점수 차이가 `min_gap`의 두 배 이상이어야 한다.
  점수는 해당 key를 평가한 턴들의 평균이며, 질문이 그 key를 묻지 않은 턴은 평균에서 뺀다. `technical_reasoning`·`problem_solving`·
  `project_understanding`은 `tech_lead` 6턴, `company_job_fit`은 `domain_lead` 2턴,
  `contribution_clarity`는 `hr_manager` 1턴이 근거이므로 근거 턴이 많은 key는 여러 턴의 답변을 함께
  바꿔야 한다.
- 쌍을 만들 수 없는 사례는 `pair`를 생략한다. 이 사례는 순서 판정에서 빼고 건수를 따로 적으며
  통과로 세지 않는다.
- 모든 `report` 사례의 출력에는 순서 판정과 별도로 형식 검사를 한다: 6개 key가 모두 있고 key 점수와
  `totalScore`가 0~100 정수이며, `totalScore`가 key 점수 평균과 1 이하로 다르다.
- `evals/report_check.py`의 `grade_reports`가 출력(공개 리포트 모양: `totalScore`, `scores[{key, score}]`)
  에 형식 검사와 쌍 순서 판정을 한다. 출력 키는 `r-0001.v1` 같은 파일 이름 stem이다. 출력이 없거나
  형식이 틀린 쌍은 통과가 아니고, 쌍 없는 사례는 건수로 따로 적는다. 기본으로 둘 다 `approved`인 쌍만
  품질 건수에 넣는다(ADR 0009). 서술 판정은 이 검사에 포함하지 않는다.

## 사례 검수 (작성자 제안, 팀 확인 대기)

사례를 쓴 뒤 모델을 돌리기 전에, 작성자가 아닌 사람이 허용·금지 결과가 원문과 승인된 정책에 맞는지
확인한다. 사례마다 검수자는 한 명이다. 의견이 갈리면 사례를 `pending`으로 두고 양쪽 이유를
`pending_notes`에 적는다. 이때 다른 검수자가 허용 결과 확대, 새 버전으로 재작성, 무효화 중 하나로
정한다. 승인 한 명에 열린 `pending`이 없으면 검수가 끝난 것으로 보고 `review`에 기록한다.

검수자(GitHub 로그인. 작성자는 자기 사례의 검수자가 될 수 없다):

| 사례 종류 | 검수자 |
| --- | --- |
| `evidence`, `flow` | `kyeonsol` |
| `question` | `gdh0730` |
| `report` | 리포트 사례를 추가할 때 지정 |

그 사람이 실제로 확인하기 전에는 `reviewer`를 `null`로 둔다.

검수자가 JSON과 사실표를 오가지 않도록 사례마다 한 장짜리 검수 시트를 만든다. 기대값 파일의 선택
필드 `source_fact`(예: `F-R1-001`)가 `fact-table.md`의 항목을 가리키고, 시트에는 모델이 받는 것, 원본
사실, 정답 기준, 채점기 시험용 가짜 답, 판단할 질문 4개가 담긴다. `ai/`에서
`uv run python evals/review_sheet.py [case_id ...]`로 만들며 결과는 무시되는 `ai/report/review-sheets/`에
`{case_id}.v{version}.md` 이름으로 저장된다(버전마다 시트가 따로 남는다). 쌍을 이루는 `report` 사례의
시트에는 쌍 ID, 강한/약한 역할, 비교 key, `min_gap`, 상대 사례와 달라진 답변과 비교 검수 질문이 들어간다.
쌍이 없는 `report` 사례는 서술 기준 검수 질문만 받는다. 시트에는 정답이 있으므로 모델 입력에 쓰지 않는다.

현재 사례는 19건이다: `evidence` 6건(`e-0001`~`e-0006`), `question` 10건(`q-0001`~`q-0010`),
`flow` 1건(`f-0001`), `report` 2건(`r-0001`, `r-0002`). 검수 상태는 `approved` 6건(`e-` 전부),
`pending` 4건(`q-0002`, `q-0005`~`q-0007`), `unreviewed` 9건이다. `pending` 사례는 품질 집계에서 뺀다. 자료·근거 사례의 `payload`는 `question`과
`materials`(`ref`, `path`, `lines`, `text`)이고, 자료 `text`는 공개 저장소 원문이 아니라
`fact-table.md`의 사실 구조만 본떠 새로 쓴 합성 내용이다. 질문·흐름 사례의 `payload`는 Director의
입력을 단순화한 평가용 형식(`turn`, `allowed_personas`, `persona_left`, `history`, `latest_analysis`,
`evidence`, `task` 등)이며 실제 입력 객체와 필드가 완전히 같지 않다. 실행기를 만들 때 변환이 필요하다.
질문·흐름 사례의 금지 유형 이름(`topic_jump`, `false_premise` 등)은 작성자가 임시로 붙였고 팀 합의
코드가 아니다. 실제 채점기와 평가 실행 harness는 없다. 이 디렉터리는 런타임 패키지와 배포물에
포함되지 않는다.

같은 원본에서 나온 사례는 같은 source group에 둔다. 개발용과 최종검증용(holdout)은 서로 다른 source
group을 써야 한다. holdout 사례가 구현이나 정책 변경에 쓰였다면 회귀검사 자료가 되며 사용 이력을
남겨야 한다. 이름을 바꾸거나 복사해도 아직 쓰지 않은 holdout이 되지 않는다.

실제 사용자 자료나 공개하지 않은 holdout 정답을 여기에 커밋하지 않는다. 임시 평가 출력은 무시되는
`ai/report/` 경로에 저장한다.
