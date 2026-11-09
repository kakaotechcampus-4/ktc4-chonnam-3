# 평가 자료의 과거 출처 보존과 호환 후속 변경

기존 미병합 구현을 중복 게시하지 않고 이번 수정 구간만 보존한 패치다.
이 파일을 게시해도 서비스 코드에 자동 적용되거나 기능이 활성화되지는 않는다.

선행 PR: #214, #215. 모든 PR의 base는 develop이다.
기존 게시 패치가 있다면 먼저 적용하고 이 표의 적용 전 지문과 일치하는지 확인한다.
지문은 UTF-8 텍스트의 CRLF를 LF로 정규화한 SHA256이다. 기준이 다르면 강제 적용하지 않는다.

## 적용 조건

1. 선행 구현과 이번 PR의 직접 변경을 반영한다.
2. 대상 파일의 적용 전 지문과 실제 내용을 확인한다.
3. 각 패치에 `git apply --check`를 실행하고 통과한 패치만 `git apply`로 반영한다.
4. 적용 후 지문과 원문을 확인하고 해당 기능의 회귀·통합 검증을 다시 실행한다.
5. 실제 코드 반영과 CI 재검증 전에는 Draft 상태를 해제하거나 병합하지 않는다.

선행 #215를 통합할 때 현재 develop의 canonical 19사례를 유지한다. 옛 canonical 자료를 복원하지 않는다.
과거 snapshot은 기존 코호트의 출처 보존용이며 현재 정답이나 새 holdout이 아니다.

## 대상과 지문

| 대상 | 패치 | 적용 전 SHA256 | 적용 후 SHA256 |
| --- | --- | --- | --- |
| `ai/evals/README.md` | [9b342f0b549a-README.md.patch](9b342f0b549a-README.md.patch) | `6dda11344ffc3274dad69533f279a13c0209eaa7311a37a208771d625ab1a4fc` | `78bd18eaea68b9d7d099fec1f336bb4bbfac4b651fc0aa27f332cf046a4f75eb` |
| `ai/evals/component_regression/binding-manifest.json` | [df43c36b2dfc-binding-manifest.json.patch](df43c36b2dfc-binding-manifest.json.patch) | `10c5a15ee28c0e9dc189eed629c968b3a2dc7c8bfca8b0b999a725aaa2a7b5bb` | `cea4bf0fe954c4f8503bbdb541d607f0de464c706684dd57908886033842e86a` |
| `ai/evals/eval_cases.py` | [2eada59a6130-eval_cases.py.patch](2eada59a6130-eval_cases.py.patch) | `09d461f856b6e0ad313513f50da27720690c0cac33f6f04447d9d3349c509f65` | `1b00f496f43035d304010bf580f4897cc9be3a3c4d96afef4fcfb1aed65f47c8` |
| `ai/evals/report_source_binding_cohort/binding-manifest.json` | [cfc9293015b3-binding-manifest.json.patch](cfc9293015b3-binding-manifest.json.patch) | `1629668de8954dab27eba2b8c10e94e9ad19e3fedef2ede9fa75480bd4611db5` | `05a43064f4c2eb9a11f07d1c6dcde84ca88f518e38b656d9f46af321630aa369` |
| `ai/evals/service_regression/binding-manifest.json` | [6c98ce85cb76-binding-manifest.json.patch](6c98ce85cb76-binding-manifest.json.patch) | `064a7a1da536e8b6e59788a3e1652cad2fbe0c1ff814d4916bdf0c8d9870a919` | `043a745f5d534e7025cab7724c37d6ba92263093e312947c69725bfdabf2a0bf` |
| `ai/tests/test_eval_judge_context.py` | [1d43cc549bbc-test_eval_judge_context.py.patch](1d43cc549bbc-test_eval_judge_context.py.patch) | `a03bd36208116cab6f80fb77e8bde51bb156ab5f9f3f706e5fb282f62c226e5a` | `3d927b02ef7cb937c49d2c96ae4d09fdcb172018c53b89dcda10f73ca5716cd3` |
| `ai/tests/test_eval_report_source_binding.py` | [49d82ee66512-test_eval_report_source_binding.py.patch](49d82ee66512-test_eval_report_source_binding.py.patch) | `88629ca8b3ebe3031afe99c28f9edfd27550938c24c9ca1f9f04eb4402f7c125` | `5f3d4c76ba3da3186a0cc54dff0de2e41d076c56d3c5806de5d4cb7d808619b8` |
| `ai/tests/test_eval_verification_component.py` | [03d1e93c9ac8-test_eval_verification_component.py.patch](03d1e93c9ac8-test_eval_verification_component.py.patch) | `d7f8170b5f46c5c0af7a8af80ab58af880943c95247a8438489196cfa541dadf` | `519c6e3e294466b5e940194b12a1d59bd5d2167de483a5f0ae0fbf70b9402e87` |
| `backend/scripts/run_ai_evaluation.py` | [dfcdb304c81b-run_ai_evaluation.py.patch](dfcdb304c81b-run_ai_evaluation.py.patch) | `7ca60270393950d0a6e74da1345932a2f8b1c281c591e80e4e9f62d612ef53f9` | `17a97d454ffe6761c63cb9c31cfc423957ecdd8d41c2ff3dfb0cc3f633f97504` |
| `backend/tests/test_ai_eval_service_dataset.py` | [d12258abaa89-test_ai_eval_service_dataset.py.patch](d12258abaa89-test_ai_eval_service_dataset.py.patch) | `30ad37e384b8ce9f46180ea1d4fa667de4518217b85c6a4c2cc78e1837620dea` | `0640b30b74fba08ac85d24bf5ed6c77a30b355da20048d3f8898c2de1b485778` |
