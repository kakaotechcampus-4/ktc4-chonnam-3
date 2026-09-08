# task-15 — 면접 WebSocket (텍스트)

> 선행: task-13, task-14
> 설계 근거: [becontext.md](../../becontext.md) · [db-schema.md](db-schema.md)

## 목표

WS 핸드셰이크 + L2 deep + prepare 4단계 + 턴 루프.

## 확정본 반영 (becontext.md 대비 변경)

- **스프린트1 은 양방향 텍스트다** (FE 합의). 오디오 프레임 · `transcript` · `stt_failed` · `tts_failed` · `integrations/speech/` 는 전부 **스프린트2**.
- 답변 초안 저장 없음 — 제출 1회로 `answer_text` UPDATE.
- `deep_analysis`(M4-a) 에서 L2 를 돌리고, `notable_areas` 를 `evidences`(`tool_name=NULL`) 로 전개한다. 면접 중 Tool 산출물(`tool_name` 값 있음)과 구분돼야 "Tool 호출 0건 = 근거 없는 꼬리질문" 지표가 성립한다.
- `git_ref` 는 `session_repositories.snapshot_head_sha` 에서 복사한다.
- `depth` 1=주제 시작, 2+=꼬리질문, 새 주제면 1로 리셋.
- `turn_evidences` 필수 여부는 **페르소나별로 다르다** — `tech_lead` 는 필수, `domain_lead` 는 `jd_requirement_ids`, `hr_manager` 는 `claim_ids` 로 갈음.

## 작업

- [ ] TODO

## 완료 조건

- [ ] TODO

## 커밋 메시지

```
TODO
```
