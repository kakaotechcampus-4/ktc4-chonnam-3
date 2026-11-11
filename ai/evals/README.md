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
  형식에서 뺐다. 기본 loader와 서비스 자료는 이 형식을 검사하며, 축약 v1의 명시적 검수 예외는
  아래 원본 버전 구분을 따른다.
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
저장된다. 시트에는 정답이 있으므로 모델 입력에 쓰지 않는다.

사례의 검수 상태는 각 `expectations/*.json`의 `review`가 원본이다. 실행·검증 현황은
[단일 구현 기록](../../spec/ai/implementation.md)을 참조한다. 자료·근거 사례의 `payload`는 `question`과
`materials`(`ref`, `path`, `lines`, `text`)이고, 자료 `text`는 공개 저장소 원문이 아니라
`fact-table.md`의 사실 구조만 본떠 새로 쓴 합성 내용이다. 질문·흐름 사례의 `payload`는 Director의
입력을 단순화한 평가용 형식(`turn`, `allowed_personas`, `persona_left`, `history`, `latest_analysis`,
`evidence`, `task` 등)이며 실제 입력 객체와 필드가 완전히 같지 않다. 실행기를 만들 때 변환이 필요하다.
질문·흐름 사례의 금지 유형 이름(`topic_jump`, `false_premise` 등)은 작성자가 임시로 붙였고 팀 합의
코드가 아니다. 실제 서비스 실행에는 명시적인 `service_input`과 해당 task의 타입 검증이 필요하다.
축약 사례를 임의로 서비스 입력으로 변환하거나 정답 필드를 모델에 전달하지 않는다.
이 디렉터리는 런타임 패키지와 배포물에 포함되지 않는다.

실행 진입점은 `backend/scripts/run_ai_evaluation.py`다. `--execute --manifest <파일>`은 서비스
출력을 만들고, `--llm-judge --max-judge-attempts <상한>`은 별도 Judge 예산을 사용한다.
승인된 기존 control만 확인할 때는 `--calibrate-judge-only --approved-only`를 사용한다.
이 모드는 서비스 모델을 실행하지 않으며, `service_input`이 없는 사례를 서비스 실행 성공으로 세지 않는다.
Judge v1은 허용·금지 기준과 출력 하나를 사용한다. v2는 해당 사례에 실제 제공된 원문·위치·
질문 계약·면접관 역할·조회 상태를 `judge-context.v1` whitelist와 64KiB 상한으로 함께 전달한다.
control의 정답 종류·검수 메타데이터는 숨기고, 없는 원문은 추정하지 않는다.
`--rejudge-results <기존 결과>`는 사례·기대값·출력·binding 지문이 맞는 저장 출력만 새 Judge로
재판정한다. 서비스 모델을 다시 실행하지 않으며 원래 실패와 출력은 보존한다.
실행 모드·모델·입출력 지문·예산 소진·미실행 상태를 함께 확인하며 release gate의 미확정을 임의로 승인하지 않는다.

같은 원본에서 나온 사례는 같은 source group에 둔다. 개발용과 최종검증용(holdout)은 서로 다른 source
group을 써야 한다. holdout 사례가 구현이나 정책 변경에 쓰였다면 회귀검사 자료가 되며 사용 이력을
남겨야 한다. 이름을 바꾸거나 복사해도 아직 쓰지 않은 holdout이 되지 않는다.

실제 사용자 자료나 공개하지 않은 holdout 정답을 여기에 커밋하지 않는다. 임시 평가 출력은 무시되는
`ai/report/` 경로에 저장한다.


## 현재 검수 원본과 과거 출처의 구분

현재 inputs/expectations의 v1은 최신 develop 원본을 유지한다. 검수 상태를 코호트 실행 성공으로
approved로 올리지 않는다. 검수 시트는 버전별 파일명을 사용하고 쌍의 비교 정보를 표시한다.

최신 pilot v1의 report에는 축약 history만 있다. 검수 시트와 control 교정은
load_cases(..., allow_legacy_report_contracts=True)를 명시해서만 이 형식을 읽는다.
기본 loader와 실제 service_input의 Question Contract 검사는 완화하지 않는다.

source_snapshot_20261108은 기존 service_regression/report_source_binding_cohort/
component_regression이 참조한 이전 58개 JSON과 사실표의 불변 사본이다. 과거 approved 메타데이터도
그 당시 출처의 일부이며 현재 품질 분모가 아니다. snapshot은 실행 사례로 직접 로드하지 못한다.
각 binding-manifest의 source_snapshot이 이 출처를 명시하고 기존 지문을 그대로 검증한다.
원문·기준·v2/v3 입력을 새 결과에 맞춰 고치지 않는다.

### 출처 경로와 실행 지문

binding의 `original_files`에 있는 `ai/evals/inputs/...`와 `expectations/...`는 당시
원문의 논리 경로다. `source_snapshot`이 선언된 코호트에서는 이 경로를 현재 canonical로
읽지 않고 `source_snapshot_20261108/inputs/...`와 `expectations/...`로 해석한다.
과거 snapshot의 승인 표시도 현재 사례의 승인이 아니다. [원문 비교 색인](source_snapshot_comparison.json)은
색인에 기록된 develop commit과의 차이를 설명하며 어느 쪽도 덮어쓰지 않는다.

보고서 코호트의 `prior_binding_sha256`, `prior_expectation_sha256`,
`snapshot_template_sha256`은 형제 `service_regression`의 이전 입력·기대값·template에 대한
UTF-8 LF 지문이다. 상대 경로 표기를 임의의 상위 디렉터리 접근 권한으로 해석하지 않는다.
참조 원문이 없거나 선언한 지문과 다르면 사례를 실행하기 전에 거절한다.

현재 서비스 경로 검증은 `service_regression/runtime-manifest.json`을 사용한다.
이 파일은 Director v8·답변 분석 v6·Report v3·Score v3를 지정하는 입력 검증용 manifest다.
기존 `manifest.json`은 v4/v2 비교용으로 보존한다. `fixture-model-not-for-provider-execution`은
실제 호출 모델이 아니며, 실제 평가에는 별도 모델 manifest와 명시적 예산을 사용한다.

새 평가 결과의 dataset 지문은 `format_version: 2`, `file_hash_format: utf8_lf`로 표시한다.
checkout 줄바꿈만 다른 자료는 같은 portable 지문으로 비교하고 raw 지문도 별도로 남긴다.
과거 무표시 결과는 기존 raw 의미로만 읽으며 원본 결과를 수정하지 않는다.
불변 archive의 provenance는 계속 raw 바이트를 검증하므로 LF로 다시 저장하지 않는다.

CLI 출력 경로는 실행 전에 독점 생성하며 모든 모드에서 기존 결과를 덮어쓰지 않는다.
사례 시작·완료 때 checkpoint를 저장하고 중단 결과는 `run_state: interrupted`로 구분한다.
이 기록은 자동 재개나 이미 처리한 유료 호출의 재실행 허가가 아니다. 중단 당시 처리 중인
호출의 사용량은 최종 응답을 받지 못했다면 미확인일 수 있다. 완료 결과만 재판정에 사용한다.
종료 코드 0은 요청한 기술 검사가 오류 없이 끝났다는 뜻이며 품질 승인이 아니다.
기술 실행·입력·Judge 오류는 비0으로 알리고 사람 검수 대기는 결과에 따로 남긴다.

## Director study와 원문 판정

`backend/scripts/run_director_study.py`는 `ServiceExecutor`와 공통 평가 실행기를 사용한다.
`director_cases.py`의 typed 사례를 기본 `pilot` 또는 `dev`, `holdout`, `all`로 선택한다.
`pilot`은 개발 사례의 부분집합이다. `--case-id`를 반복해 같은 사례의 변경 전후 실행을 교대로
배치할 수 있다. `--export-cases <새 디렉터리>`는 기존 loader가 읽는 입력·기대값 쌍과 코호트
manifest를 내보낸다. 실행 순서와 예산을 정한 후 자료·기준을 동결하고 최종 검증 자료를 사용한다.

명령의 작업 디렉터리는 `backend/`다. 다음 예시의 manifest와 결과 경로는 로컬 파일로 준비한다.
프롬프트 버전은 CLI에 고정하지 않고 manifest의 `version`, `template_path`로 선택한다.
manifest의 `prompts`에는 Director 하나를 지정하며 모델은 `gpt-6-luna`다. `limits`와 선택적인
`task_limits`는 원본 `.env`의 `call_limits("director")`와 같아야 한다. 연구를 위해 추론 강도·토큰
상한을 낮추지 않는다. API 키는 manifest에 쓰지 않고 `--env-file`로 원본 설정 경로를 지정한다.

```powershell
# 기본 모드는 설정의 비밀값을 읽거나 모델을 호출하지 않는 typed 입력 검증이다.
uv run python scripts/run_director_study.py --manifest $manifest --selection pilot --output $validation

# $attemptLimit와 $wallLimit는 실행 전에 정한 양의 유한 상한이다.
uv run python scripts/run_director_study.py --manifest $manifest --selection pilot --output $results --execute --max-model-attempts $attemptLimit --max-wall-seconds $wallLimit --env-file $envFile --ledger $ledger --export-review-packets $packets
```

`--execute`는 요청·응답 모델이 Luna인지 검사하고 환경의 모델 선택과 작업별 제한도 확인한다.
HTTP 시도 예산과 전체 실행 시간 예산은 별개다. 재시도도 시도 예산에 포함한다. 저장된 응답이 없는
중단 호출을 무료 또는 미실행으로 추정하지 않는다. 결과 파일은 새 경로를 사용하며 같은 결과를
덮어쓰지 않는다. 예산 소진·미실행·실행 실패는 성공이나 품질 통과에 포함하지 않는다.

서비스 실행, 코드 검사, Codex 원문 판정, 선택적인 소수 Luna 보조 대조를 구분한다. 기본 실행은
유료 Judge를 자동 추가하지 않는다. Codex가 읽을 검토 자료는 `--export-review-packets`로 내보낸다.
이미 저장된 결과에서 검토 자료만 다시 만들 때도 `eval_runner.review_packets()`를 사용한다.

### 판정 대상과 정책 자료의 바인딩

검토 자료는 기준, 실제 후보 출력, 실제 모델 표시 범위를 함께 제공한다. Director 실행의
`source_snapshot`에는 Plan·Review 경계의 입력과 프롬프트·모델·출력 스키마 버전, payload 지문을
보존한다. 모델 전용 projection에서 제외한 원본 필드를 Judge 입력에 다시 넣지 않는다.
각 스냅샷의 `schema_version`을 확인하고 해당 검증기로 읽는다. 프롬프트 원문과 해시를 담는
스냅샷에서는 이를 당시 정책 자료로 함께 검토한다. 이를 담지 않은 과거 형식은 당시 버전의
검증 가능한 정책 자료를 별도로 연결하거나 누락 한계를 남긴다. 현재 프롬프트로 과거 정책을
소급 대체하지 않는다. 프롬프트·원문·생성자의 이유는 서로 다른 자료이며 정책의 정확성도 별도
검토 대상이다. 생성자가 작성한 이유를 질문의 승인 근거로 취급하지 않는다.

Judge 문맥의 바이트 예산을 넘으면 `source_snapshot`에 전체 범위를 보존하고 누락을 표시한다.
제공되지 않은 범위를 읽었다고 판정하지 않는다. Codex가 별도 스냅샷을 직접 확인했다면 실제로
추가 확인한 위치와 범위를 판정 이유에 기록한다. 당시 질문·답변, 원문 위치·버전, 후속 기여 정정을
확인하고 판단 자료가 부족한 기준은 `unclear`로 남긴다.

`recorded_grader.py`는 다음 세 지문으로 저장 판정을 대상에 결합한다.

- `rubric_sha256`: 허용·금지 기준
- `candidate_sha256`: 실제 후보 출력
- `source_context_sha256`: 해당 후보의 검토 문맥

각 기준을 한 번씩 판정하고 `satisfied`, `violated`, `unclear`와 이유를 기록한다. 허용 항목은
의무 조건이며, 한 항목 안의 `one_of_allowed` 대안은 하나를 충족하면 된다. 가능한 대안을 모두
필수로 해석하지 않는다. 금지 항목의 `satisfied`는 금지 행동이 없다는 뜻이다. 미적용 조건은
사례별 기준 편성 단계에서 구분하며 자료 부족과 혼동하지 않는다. 기준 누락·중복·잘못된 지문과
기준별 결과에 모순되는 종합 판정은 거부한다. 지문 일치는 의미 판정의 정확성을 보증하지 않는다.

저장 판정 문서의 `reviewer.kind`는 `codex_source_review`다. `actor`, `review_context`, 확인 가능한
`model_id`를 기록하고, 모델 ID를 모르면 `null`로 둔다. 구현에 참여한 세션을 독립 사람 검수로
기록하지 않는다. 다음 재판정 명령은 서비스 모델을 다시 호출하지 않는다. 원래 Codex 판정의
사용량·비용을 수집하지 않았다면 0으로 계산하지 않는다.

```powershell
uv run python scripts/run_director_study.py --manifest $manifest --selection pilot --rejudge-results $results --recorded-judgments $judgments --output $reviewed
uv run python scripts/run_director_study.py --compare $baselineResults $candidateResults --output $comparison
uv run python scripts/run_director_study.py --controls-only --output $controlPackets
```

재판정은 원래 서비스 출력·시도·시간·실패를 보존하고 판정만 연결한다. 비교는 코호트·설정과
사례별 입력·기준·원문 그룹이 같은 쌍만 허용한다. 모델 표시 범위를 바꾸는 실험에서는 동일한
시나리오 입력과 별개로 각 실행의 `source_snapshot` 차이도 확인한다. 변경 요인과 코드·프롬프트
버전을 기록하고 캐시·순서·동시 부하 조건을 맞춘다. 성공 쌍의 서비스 시간과 실패 시 기다린
시간·토큰·시도 수를 나눠 집계하며 Judge 시간을 서비스 시간에 더하지 않는다. 비용을 가격화하지
못한 쌍은 `None`으로 보존한다. 세부 토큰을 총 토큰에 중복 합산하지 않는다.

`--controls-only`는 제어 후보 검토 자료와 별도 `*.labels.json`을 만든다. 기대 라벨은 모델에
보내지 않는다. 정상·오류·자료 부족 출력으로 평가자의 오수락·오거절·판단 보류를 구분한다.
제어 라벨은 작성자의 기대이므로 원문·기준과의 일관성도 확인해야 한다. 라벨 일치만으로 평가자의
일반적인 정확성을 확정하지 않는다. 필요한 Luna 보조 대조에는 별도의 표본과 유한 예산을 정한다.

### 자료의 독립성과 자동 검증 범위

기본 코호트는 24개 합성 원문 그룹에 다섯 답변 상황을 적용한다. 개발 60개와 holdout 60개는
원문 그룹을 분리하고 pilot 12개는 개발 집합에 포함한다. 제어 출력 24개는 서비스 생성 사례와
분리한다. 그룹 ID를 바꾸어 같은 원문을 다른 split에 넣는 것도 거부한다.

서로 다른 언어·경로의 원문도 검증 후 저장하는 처리 골격을 공유한다. 따라서 이 자료를 독립적인
실제 레포 120건이나 새로운 아키텍처 일반화의 증거로 해석하지 않는다. 같은 그룹의 변형·반복·턴은
상관된 관측으로 다루고 그룹 단위 결과를 함께 표시한다. 이 표본 수는 실행 규모이며 통계적
충분성·지연 목표·평가자 정확도의 근거가 아니다. 최종 자료를 본 뒤 수정했다면 그 자료는 다음부터
회귀 검증용이다. 실제 레포·공고·구조의 일반화 검증에는 별도 자료가 필요하다.

자동 검증과 사람 검수는 서로 다른 상태다. 실제로 끝낸 입력·실행·원문 판정의 범위와 분모를
명시해 해당 범위를 `자동 검증 완료`로 기록할 수 있다. 사람 미검수를 이유로 완료한 자동 검사를
미실행으로 바꾸지 않는다. 반대로 자동 판정으로 기존 `review.status`를 `approved`로 승격하거나
사람의 품질·출시 승인으로 기록하지 않는다. 필수 오류·실패·판단 불가를 평균 품질로 상쇄하지 않는다.

## Director trajectory의 질문별 재개

`backend/scripts/run_director_trajectory.py`는 동일한 원문에서 실제 생성 질문에 답변을 결합해
`ServiceExecutor`의 Director와 T3를 이어 실행한다. manifest에는 Director와 `answer_analysis`
두 프롬프트를 선언하고 각 작업의 `.env` 제한을 `task_limits`에 맞춘다. 특정 프롬프트 버전은
기본값으로 가정하지 않으며 한 세션을 재개할 때 프롬프트 본문·버전·모델·제한을 유지한다.

시작 자료는 `--seed-case-id` 또는 `--seed-file <파일>` 중 하나로 선택한다. 외부 파일은 Case의
일곱 필드 `case_id`, `version`, `kind`, `split`, `source_group_id`, `payload`, `expectation`만 둔다.
`kind`는 `question`이고 payload는 실제 `prepare()`를 통과하는 typed Director 입력이어야 한다.
원문은 primary 저장소 하나에 묶고 근거와 허용 위치의 저장소·SHA를 일치시킨다. 공고와 외부
자료는 코드 Evidence로 섞지 않고 각각의 타입·출처를 유지한다. 코드 위치·버전을 채우거나
provenance의 요약을 코드 원문으로 대신하지 않는다.

파일은 최대 512KiB만 읽고 중복 JSON 키·추가 필드·기대값 ID/버전 불일치·원문 버전 혼합을
거부한다. `--seed-sha256`를 함께 지정하면 실제 읽은 바이트의 SHA-256도 대조한다. 파일 지문·길이와
payload 지문은 실행 metadata에 보존한다. 이 파일 제한과 실제 모델 요청의 입력 바이트 제한은
별도이며 후자는 기존 Gateway가 검사한다. 수집 원천·원본 snapshot의 진실성은 별도 provenance로
확인한다. loader의 `provenance_verified: false`는 그 검증을 CLI가 대신 수행하지 않는다는 뜻이다.
provenance sidecar는 Case 파일에 합치거나 모델에 전달하지 않는다.

```powershell
uv run python scripts/run_director_trajectory.py --manifest $trajectoryManifest --seed-case-id dq-01-partial --session-id $sessionId --output $step00

# 실제 수집 원문으로 구성한 외부 seed도 기본은 호출 없는 검증이다.
uv run python scripts/run_director_trajectory.py --manifest $trajectoryManifest --seed-file $seedFile --seed-sha256 $seedHash --session-id $sessionId --output $seedValidation

# 실제 첫 질문 생성. --execute가 없으면 모델 호출 없는 입력 검증이다.
uv run python scripts/run_director_trajectory.py --manifest $trajectoryManifest --seed-case-id dq-01-partial --session-id $sessionId --output $liveStep00 --execute --max-model-attempts $stepAttemptLimit --max-session-attempts $sessionAttemptLimit --max-wall-seconds $wallLimit --env-file $envFile --ledger $ledger
uv run python scripts/run_director_trajectory.py --manifest $trajectoryManifest --resume $liveStep00 --answer-file $answer01 --output $liveStep01 --execute --max-model-attempts $stepAttemptLimit --max-session-attempts $sessionAttemptLimit --max-wall-seconds $wallLimit --env-file $envFile --ledger $ledger
```

처음에는 seed 선택과 `--session-id`를 지정한다. 재개에는 이 옵션 대신 완료된 단계의
`--resume`을 사용한다. 재개 시 seed 파일·파일 지문·cohort ID·세션 ID를 다시 지정해 자료를
교체할 수 없다. `run_state: completed`는 해당 CLI 단계의 완료이며 면접 전체 완료는
`trajectory.status`로 구분한다. `awaiting_answer`이면 실제 질문을 읽고 다음 JSON을 새 파일에 쓴다.
`question_sha256`는 질문 문장만이 아닌 `trajectory.turns[-1].question` 전체를
`director_cases.content_hash()`로 계산한 값이다.

```json
{
  "question_sha256": "<실제로 생성된 question 객체의 SHA-256>",
  "text": "<해당 질문과 고정한 합성 지원자 사실관계에 맞춘 답변>",
  "origin": "synthetic_codex"
}
```

다른 질문의 준비 답변을 재사용하지 않는다. 기본 답변 생성용 LLM 호출도 추가하지 않는다.
질문에 결합되지 않은 답변이나 바뀐 원문·상태 지문을 거부한다. 답변 없이 대기 상태를 읽으면
기존 질문을 반환하며 생성 호출을 반복하지 않는다. 처리 중 상태와 미확인 호출은 완료된 재개
지점이 아니므로 장부를 확인한 뒤 다룬다. 이 로컬 도구의 상태 지문은 업무 DB의 인증·분산
idempotency를 대체하지 않는다.

정상 9턴의 기본 호출 구조는 최초 질문 Plan·Review 2회, 답변 T3 9회, 다음 여덟 질문
Plan·Review 16회다. `--max-model-attempts`는 현재 단계의 상한이고 `--max-session-attempts`는
저장된 시도를 누적한 세션 상한이다. 후자의 기본 36은 정상 27회에 T3의 추가 시도 여지를 둔
실행 제한이며 품질·비용 목표가 아니다. 실행 전에 두 상한과 시간 예산을 명시하고 마지막 답변
이후에는 추가 질문을 만들지 않는다. 사용량 미확인은 별도 장부에 남긴다.

trajectory는 **텍스트 AI 코어** 범위다. REST·DB·Redis·WebSocket·STT·TTS와 Tool I/O를 실행하지
않는다. T3가 레포 조회나 마지막 턴 이전의 외부 조회를 요구하면 `requires_tools`로 멈추며
조회한 것처럼 결과를 채우지 않는다. 마지막 답변의 분석이 성공했고 외부 질의만 남았다면 새
검색을 하지 않고 `external_lookup_not_executed:final_turn` 한계를 남긴 뒤 완료한다. 마지막
턴이라도 레포 검증 요청이 있으면 Tool 처리가 필요하므로 중단한다. 운영의 `process_answer()`가
처리하는 실제 보완 조회·복구까지 같은 경로라고 해석하지 않는다. 운영 `start_director()`는
과거 분석의 `prior_analyses` 맵도 읽지만 이 도구의
`ServiceExecutor` 경로는 현재 분석과 과거 문답 원문을 전달하며 그 맵을 따로 주입하지 않는다.
각 턴 분석을 상태에 보존한다는 사실과 모델이 운영과 같은 분석 입력을 받았다는 주장은 구분한다.
실제 Controller·DB·WS 통합은 별도 환경에서 검증해야 한다.

이 절은 실행 방법과 해석 규칙이다. 실행 건수·검증 결과·진행 현황은
[단일 구현 기록](../../spec/ai/implementation.md)에만 남긴다.
