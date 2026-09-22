# 답변 분석 구현과 검증 기록

상태: 3번 항목의 AI 단발 task·fake 검증 구현. 실제 모델 품질·BE 연결·리포트 반영은 미실행.

## 기준과 적용 범위

- 사용자의 3번 구현·분할 커밋·원격 push 지시에 따라 진행한다. PR은 생성하지 않는다.
- 선행 2번이 develop에 미병합이라 `feature/ai-llm-boundary@2fc8c6d`에서
  `feature/ai-answer-analysis`를 분기했다.
- [답변 평가 명세](../features/answer-evaluation.md), [ADR 0004](../decisions/0004-answer-assessment-policy.md),
  [조회 정책](../decisions/0003-evidence-lookup-policy.md),
  [task-09](../../../ai/docs/task-09-answer-analysis.md),
  [호출 경계](2026-09-22-llm-boundary.md)를 적용한다.
- 최신 `origin/develop@ebbe13d`의 평가·계약·task-09도 대조했다. 최신 ADR 0014의
  충분성 null 시 이미 확인한 내용 보존 규칙에 맞춰 기존 `validate_analysis`를 수정했다.
  미채택 새 평가 enum·공개 필드·저장 구조는 추가하지 않는다.
- 입력·실패 전달용 상세 타입은 이번 task 내부 표현이다. 이 문서로 DB Evidence·ToolResult·
  JSONB·공개 응답의 전체 직렬화 형식을 새로 승인하지 않는다.

## 실행 경계

`analyze_answer`는 2번의 `call_model`을 재사용한다. 정상 경로는 모델 1회 호출이며,
timeout/provider/parse/schema 실패만 공통 계층에서 총 2회까지 호출한다. semantic 실패는
재호출하지 않는다. 추가 조회 Tool·다음 질문 생성·점수 계산·저장·서비스 복구는 실행하지 않는다.

BE가 `ModelRequest`의 공통 평가 prompt, model, schema와 각 version, timeout/token 상한을
주입한다. 운영 prompt·Persona 설정·provider SDK를 AI 패키지에 추가하지 않는다. task 이름은
기존 `answer_analysis_v1`을 검사한다. `request.input_json`은 아래 확정 인수로 만든 입력으로
교체하며 임의 부가 데이터나 평가 정답과 병합하지 않는다.

| 인수 | 처리 |
| --- | --- |
| `question` | `ContractChecked[Question]` 필수; 확정한 문장과 Question Contract 사용 |
| `question_turn`, `answer` | `SubmittedAnswer`의 기존 `type=answer`, `turn`, `text`만 사용; Turn 불일치·초안·빈 문자열·잘못된 타입은 모델 호출 전에 거부 |
| `evidence` | BE가 권한·출처를 확인한 task용 원문; ID·repo·고정 ref·path·source_kind·content·tool_name 전달 |
| `evidence_refs` | Context Builder가 현재 평가에 사용할 수 있다고 선택한 근거 ID; 실제 원문 존재 검사 |
| `allowed_locations` | BE가 허용한 repo/ref/path; 준비 ref와 다른 자료는 호출 전 거부 |
| `tool_results` | 실제 실행 상태·확보 items·조회 범위·한계·오류 코드; 미조회는 빈 tuple |
| `history` | 관련 이전 질문·제출 답변·최초 검증 분석; 중복·미래 Turn·현재 답변 인용 혼용 차단 |

입력 검증 실패는 안전한 필드명만 담은 `ContractError`로 호출자에게 전달한다. 모델 호출 뒤의
parse/schema/semantic 실패는 `ModelFailed`와 attempt 기록으로 반환한다. 세션 소유권,
실제 답변 저장 여부·전송 성공 여부는 BE가 확인해야 한다. `type=answer`만으로 저장 완료나
권한 검증이 증명되지는 않는다. 정상 제출된 “모르겠습니다”는 평가 입력으로 그대로 전달한다.

## 세 축과 검증

모델이 `evaluation_status`를 먼저 판단하고, 판단 가능한 충분성·기술적 정확성·기여 정합성을
각각 기존 필드로 생성하는 공통 prompt를 BE에서 주입해야 한다. AI는 Persona를 현재 질문과
history의 모델 입력에서 제외하므로 같은 질문에 Persona만 바꿔도 평가 입력과 rubric이 같다.

- 충분성은 실제 `required_points` key만 허용하며 확인 항목은 현재 답변의 실제 구절을 가져야 한다.
- null 충분성에는 이유가 필요하고 이미 확인한 covered/missing 내용을 삭제하지 않는다.
- 기술 판단은 답변 인용·유효한 근거·명시한 한계 중 적어도 하나를 가져야 한다.
- 기여 진술과 외부 근거는 별도 필드로 유지한다. 코드 존재를 개인 작성 사실로 변환하지 않는다.
- 조회 후보는 현재 답변의 미확인 주장과 연결하고 한계·목적·허용 위치를 가진다. 이미 supported인
  주장을 재조회하거나 연결된 claim 없이 조회를 요청하면 semantic 실패다.
- 조회 결과가 현재/후속 평가에 영향을 주는지, 설명이 기술적으로 타당한지, 인용이 실제 요구를
  충족하는지 등의 자연어 판단은 모델 책임이다. 문자열 포함·ID 검사로 이 의미를 증명하지 않는다.

입력 prompt의 내용·model의 판단 품질은 fake로 검증하지 않았다. 별도 판정 모델을 추가 호출하거나
답변 길이·전문용어 수·한국어 특정 단어로 충분성·거짓 여부를 자동 분류하지 않는다. fake 테스트는
명세에서 도출한 후보를 task가 보존하고 잘못된 key·인용·참조·조합을 거절하는지 검증한다.

## 근거·조회·보존

`AnalysisEvidence`는 BE가 검증한 task용 excerpt다. 현재 구현의 `path`는 허용 목록의 실제 파일
또는 metadata 위치 식별자를 받으며 가짜 줄 번호를 생성하지 않는다. 상세 위치·요약·DB ID
매핑은 BE의 원본 Evidence 연결 범위다.

`AnalysisToolResult`는 기존 found/not_found/insufficient_analysis/tool_error를 유지한다.
found에는 item, not_found에는 실제 조회 범위가 필요하고, 부족/오류에는 한계가 필요하다.
tool_error일 때만 오류 코드를 요구한다. 일부 조회 실패에서도 유효한 item은 보존한다.

선택되지 않은 근거는 직접 evidence와 tool_results.items 양쪽에서 모델 입력에 포함하지 않는다.
tool_results는 현재 task용으로 items를 선택한 표현이며 원래 상태·조회 범위·한계는 보존한다.
따라서 현재 task에 사용할 item이 없어도 과거 도구 실행의 found 상태를 not_found로 바꾸지 않는다.
원본 tool 객체는 수정하지 않는다. 실제 조회 상태가 claim의 지지 여부를 자동 확정하지 않는다.

`AnalysisHistory`는 최초 질문·답변·검증된 분석을 동결된 값으로 보존한다. 후속 질문의 평가가
충분해져도 과거 partial 분석을 덮어쓰지 않으며, 팀원 구현 정정도 현재 답변으로 전달한다.
다음 Director와 리포트는 이 문답 연결과 정정을 소비해야 한다. 이번에는 최종 리포트 생성·
DB 보존·과거 답변 편집·재평가·입력 복구를 구현하지 않았다.

## 필수 대조 사례와 검증

| 명세의 대조 사례 | fake 기반 task 검사 |
| --- | --- |
| 같은 질문의 충분·부분·불충분 | 동일 Contract에서 세 결과와 구절/key 대응 보존 |
| 길고 틀림 / 짧고 타당함 | 충분성·기술 판단을 별도 필드로 유지 |
| 질문하지 않은 항목 | TTL missing point를 semantic 실패로 거부 |
| 팀원 구현·기여 정정 | 현재 teammate 판정 전달, 과거 self 진술 보존 |
| 무관 코드·다른 버전 | 미선택 근거 ID 거부, 잘못된 ref는 호출 전 거부 |
| 도구 실패 | 조회 미발견/분석 부족/오류와 unverified 보존, 근거 없는 conflicting 거부 |
| 평가 불가 / 설명 부족 | 질문 전제·해석 문제의 null 평가와 정상 “모르겠습니다”의 설명 부족 구분 |
| 후속 보완 | 현재 질문의 보완 결과와 과거 원문·최초 분석을 함께 전달; 최종 피드백 연결은 후속 구현 |

캐시 예문 “조회가 많아서 DB 부하를 줄이려고 캐시했습니다”는 `reads`, `choice`의 인용을 남기고
`writes`만 미확인으로 반환하는 후보를 검증했다. TTL을 추가하면 실패한다.

- 기준선 157개에서 신규 task 테스트 51개를 추가해 전체 208개를 검증했다.
- 신규 구현·보완에 앞서 정상/실패 테스트를 작성하고 실제 실패를 확인했다.
- 독립 리뷰에서 발견한 tool_results의 미선택 근거 전달 우회를 수정하고 재검토했다.
- 검증 명령: `uv --directory ai sync --locked --python 3.12`,
  `uv --directory ai run --locked ruff check .`,
  `uv --directory ai run --locked ruff format --check .`,
  `uv --directory ai run --locked mypy src`, `uv --directory ai run --locked pytest`.
- 공유 계약 검사는 전역 Python 대신 uv Python 3.12와 `.claude/scripts/requirements-checks.txt`로
  `.claude/scripts/check_contracts.py`를 실행한다. 최종 결과는 완료 보고에 남긴다.
- **미실행:** 실제 모델 의미 판단·품질·비용, BE prompt/schema 설정 연결·권한·DB 저장·WS 연동,
  원문 영구 보존·입력 복구·최종 피드백 생성.
- **범위 밖:** 4번 Director, 5번 턴 정책, FE/BE·보호 파일 변경, provider 의존성 추가, PR 생성.
