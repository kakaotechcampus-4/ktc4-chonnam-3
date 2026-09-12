# task-12 - 평가 체계 준비

상태: 구현 가이드. 현재 실제 평가자료와 loader·harness·채점기는 미구현이다.

## 목표

모델과 서비스 품질을 신뢰할 수 있게 검증할 미래 평가 체계의 자료 분리, 검수, 실행 기록
경계를 구현한다. 이 가이드 작성만으로 실제 사용자 자료나 holdout 정답을 추가하거나 현재
AI 기능의 품질 통과를 선언하지 않는다.

현재 loader·harness 파일은 없지만, 향후 구현에서는 합성·비식별 fixture와 후보 로컬
loader·harness로 분리·누출·채점기 검사를 먼저 만들 수 있다. 운영 자료와 수치 출시 기준은
별도 결정까지 보류한다.

전체 순서는 [AI 구현 파이프라인](pipeline.md)을 따른다. 기능별 policy fixture가 준비된 뒤
진행하며 [task-08 근거 도구](task-08-evidence-tools.md),
[task-09 답변 분석](task-09-answer-analysis.md), [task-10 Director](task-10-director.md),
[task-11 리포트](task-11-report.md)의 검증 범위를 입력으로 삼는다.

## 근거

- [0007 평가 설계 정책](../../spec/ai/decisions/0007-evaluation-design-policy.md)의 네 사례,
  source group, 독립 검수, 입력 격리, holdout 재분류와 전체 결과 기록 원칙을 따른다.
- [0009 평가 방법](../../spec/ai/decisions/0009-ai-evaluation-method.md)의 합성 로컬 JSON 쌍,
  검수 불일치·grader 검증과 통제 비교 방법을 따른다.
- [AI 검증 기준](../../spec/ai/verification.md)의 모델 평가 자료 정책과 평가 설계 정책 확인을
  실행 기준으로 삼는다.
- [평가 workspace 안내](../evals/README.md)는 현재 빈 작업 위치와 자료 보호 경계를 설명한다.
- [AI 후속 기능 경계](../../spec/ai/features/extensions.md)의 Sprint 2 항목을 Sprint 1 평가
  완료 조건으로 끌어오지 않는다.

## 선행 조건

- [ ] 평가할 기능과 승인된 의미 정책, 허용 결과와 금지 결과의 근거를 식별한다.
- [ ] 실제 provider/model 검증은 AI-L01 결정 뒤 실행하며 임의 ID를 기록하지 않는다.
- [ ] 자료 사용 권한·보존·삭제가 필요한 실제 자료는 AI-L18 승인 전 수집하지 않는다.
- [ ] 실제 사례 수·비율·수치 목표·출시 기준은 AI-L19 합의 전 고정하지 않는다.
- [ ] 현재 [inputs](../evals/inputs/)와 [expectations](../evals/expectations/)는 `.gitkeep`만
  둔 빈 디렉터리임을 확인한다.

## 대상 파일과 책임

- [평가 workspace](../evals/README.md): 모델 입력 가능 자료와 기대·금지 결과를 분리한다.
- `ai/evals/inputs/`: 향후 승인된 실행 입력 위치다. 검수 정답이나 비밀정보를 넣지 않는다.
- `ai/evals/expectations/`: 향후 기대·금지 결과와 검수 메모 위치다. 모델 입력에서 격리한다.
- 향후 후보 로컬 loader·harness: 합성·비식별 JSON 쌍으로 입력 격리, source group/split,
  전체 결과 상태와 채점기 대조를 검사할 수 있다. 정확한 운영 schema·저장·배포 형식은 미정이다.
- production DB: 이 가이드만으로 `eval_cases`나 `eval_runs` 테이블을 추가하지 않는다.

## 작업

- [ ] 사례를 자료·근거, 질문·답변·다음 행동, 면접 흐름, Report 네 종류로 구분한다.
- [ ] 같은 원본 프로젝트의 모든 파생 사례에 같은 source group을 부여한다.
- [ ] 같은 source group이 development와 독립 최종검증 split 양쪽에 들어가지 않게 검사한다.
- [ ] 합성 로컬 사례는 `inputs/`와 `expectations/`의 JSON 쌍으로 만들고 같은
  `case_id`와 `version`으로 연결한다.
- [ ] loader는 mismatch, duplicate, orphan 쌍을 거부한다.
- [ ] 입력 파일의 실행 payload와 식별·분류·split·source group 제어 정보를 분리한다.
  모델에는 실행 payload만 전달하고 기대값·검수·control 정보도 전달하지 않는다.
- [ ] 실제 운영에서도 모델이 받는 Question Contract 등은 입력에 유지하고 평가 전용 정답만 숨긴다.
- [ ] 기대 결과는 원문, 질문 범위와 Accepted 정책에 연결하고 확인되지 않은 사실을 만들지 않는다.
- [ ] 여러 행동이 타당할 때 단일 문구 일치 대신 허용 집합과 목적을 검수한다.
- [ ] 작성자 외 검수자의 실제 확인 뒤에만 검수자·날짜·결과를 기록한다.
- [ ] 미검수 사례를 완료로 표시하거나 가상의 검수자를 채우지 않는다.
- [ ] 검수자 불일치는 양쪽 출처 근거와 이유를 가진 `pending`으로 보존한다. 해결 시
  허용 결과 확대, 사례 version 변경·재작성, 사례 무효화 중 하나를 택할 수 있지만
  모델 출력이나 모델 다수결에 맞춰 정답을 바꾸지 않는다.
- [ ] grader는 허용·금지·모호·유효하지 않은 참조·tool 실패 control로 검사하고
  false accept와 false reject를 종류별로 구분한다.
- [ ] holdout을 보고 기능·prompt·정책을 수정하면 해당 사례를 regression으로 재분류한다.
- [ ] 이름 변경·복사·다른 형식 파생으로 사용한 source group을 새 holdout처럼 만들지 않는다.
- [ ] 재분류 전 실행 이력과 원문을 보존하고 결과에 맞춰 기대 정답을 소급 변경하지 않는다.
- [ ] 통과·실패·보류·미실행·범위 밖 상태를 모두 기록한다. `pending`과 무효 사례는
  전체 수와 coverage에 남기고, 품질 분모는 독립 검수가 끝난 판정 가능 사례로 별도
  표시하며 제외 수와 이유를 함께 보고한다.
- [ ] 사용자 자료 노출, 없는 근거, 원문 변형, 종료 후 질문 같은 중대 오류를 평균값으로 상쇄하지 않는다.
- [ ] 실제 실행에서 확인된 commit, provider/model, prompt/schema/policy/dataset version을 기록한다.
- [ ] token·latency·비용은 실측값과 계산 근거가 있을 때만 기록하고 미수집 값을 0으로 채우지 않는다.
- [ ] 초기 제안 규모나 split 비율을 확정 목표로 복사하지 않는다.
- [ ] 합성·비식별 fixture용 후보 로컬 loader·harness와 분리·채점기 검사는 운영 결정과
  독립적으로 구현한다.
- [ ] baseline과 candidate는 같은 사례·source group에서 한 요인씩 바꾸고 task 실패,
  품질, 비용, 지연을 함께 비교한다. 권한·참조·parser·tool·source 부재 실패는 검색
  방법 결함과 구분한다.
- [ ] 승인 범위 안의 방법 비교와 범위 확대 제안 실험을 분리한다. 범위 확대가 필요한
  실패 사례도 보존하되 실제 확장 실험은 사전 승인 뒤에만 실행한다.
- [ ] 실제 사용자 자료, 독립 검수 완료 사례, production schema, 수치 목표와 출시 기준은
  AI-L18·AI-L19의 해당 결정 전 만들거나 완료로 표시하지 않는다.

## 검증

추가 예정, 현재 없음: `ai/tests/test_eval_data_boundaries.py`.

- [ ] source group 중복과 split 누출을 의도적으로 넣은 fixture를 거절하는지 검사한다.
- [ ] mismatch, duplicate, orphan fixture 쌍을 모두 거부하는지 검사한다.
- [ ] expectation과 review 메모가 prompt·retrieval 입력에 섞이지 않는지 검사한다.
- [ ] 모델 호출 경계에 실행 payload 외 loader control metadata가 없는지 검사한다.
- [ ] 실제 운영 입력과 평가 전용 정답을 과도하게 함께 제거하지 않는지 검사한다.
- [ ] 독립 검수 누락, holdout 사용 뒤 미재분류와 과거 기록 삭제를 탐지한다.
- [ ] 모든 결과 상태가 보고되고 안전 오류가 평균 품질로 가려지지 않는지 검사한다.
- [ ] 정상 출력과 고의 오류 출력으로 채점기 자체의 구분 능력을 별도 검증한다.
- [ ] grader control별 false accept/false reject와 `pending`의 전체 수·품질 분모 분리가
  보고되는지 검사한다.
- [ ] 같은 사례 비교가 변경 요인과 실패 원인을 남기고 승인 범위별 결과를 섞지 않는지
  확인한다.

정책 검사 통과는 실제 사례의 권한 확보, 독립 검수, 모델 실행이나 출시 승인이 아니다.

## 완료 조건

- [ ] 네 사례 종류와 source group 기반 split 경계가 자동 검사 가능한 형태로 정의된다.
- [ ] 실행 입력과 expectation·검수 메모 격리가 테스트된다.
- [ ] holdout 사용 이력과 regression 재분류가 삭제 없이 추적된다.
- [ ] 전체 상태와 중대 오류를 누락하지 않는 실행 보고가 검증된다.
- [ ] 실제 자료·수치·provider·출시 기준을 미결정 상태에서 발명하지 않는다.

## 결정 대기와 재개 조건

| 항목 | 지금 가능한 작업 | 실제 평가 재개 조건 |
| --- | --- | --- |
| AI-L01 provider | provider 독립 fixture 설계 | 호출 가능한 model ID와 기록 방식 검증 |
| AI-L18 자료 운영 | 합성·비식별 fixture와 비밀 제외 검사 | 실제 자료의 동의·권한·마스킹·보존·삭제·배포 정책 승인 |
| AI-L19 수용 기준 | 0009의 로컬 JSON 쌍, 후보 loader·harness, 격리·grader·통제 비교 검사 | 실제 사례 수·검수자·조정 결과·control 자료, 최종 수치 목표와 출시 기준 합의 |

대기 항목의 현재 상태는 [later.md](../../later.md)에서 확인한다.
