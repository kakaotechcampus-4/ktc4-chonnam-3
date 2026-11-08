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

아직 JSON 사례, 실제 데이터셋, 예시, 정답, 평가 실행 harness는 없다. 이 디렉터리는 런타임 패키지와
배포물에 포함되지 않는다.

같은 원본에서 나온 사례는 같은 source group에 둔다. 개발용과 최종검증용(holdout)은 서로 다른 source
group을 써야 한다. holdout 사례가 구현이나 정책 변경에 쓰였다면 회귀검사 자료가 되며 사용 이력을
남겨야 한다. 이름을 바꾸거나 복사해도 아직 쓰지 않은 holdout이 되지 않는다.

실제 사용자 자료나 공개하지 않은 holdout 정답을 여기에 커밋하지 않는다. 임시 평가 출력은 무시되는
`ai/report/` 경로에 저장한다.
