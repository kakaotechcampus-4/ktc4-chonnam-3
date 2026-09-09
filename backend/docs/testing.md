# 테스트 전략

| 계층 | 방법 |
|---|---|
| 계약 | `tests/contract/` — `types/api.ts` 기대 키 집합 대조 ([layer-rules.md](layer-rules.md) 5절) |
| 라우터 | `httpx.AsyncClient(transport=ASGITransport(app))` + 실제 테스트 DB |
| 서비스 | 트랜잭션 롤백 픽스처 |
| Director | LLM 클라이언트를 프로토콜로 추상화 → 스텁 주입. **DB 없이 돈다** |
| LLM task | 같은 방식. 배치 부분 파싱이 핵심 케이스 |
| 외부 API | `httpx.MockTransport` — 네트워크 금지 |
| WS | `TestClient.websocket_connect` |

⚠ **SQLite 로 대체하지 않는다.** `JSONB` · `TEXT[]` · 부분 유니크 인덱스 · `gen_random_uuid()` 가
전부 Postgres 전용이고, 그게 스키마의 핵심이다. `docker compose` 의 Postgres 를 그대로 쓴다.

## 반드시 있어야 할 테스트 4개

용어사전 §8 이 "어기면 지표가 계산되지 않는다" 고 한 것들을 테스트로 고정한다.

### ① 질문 생성 시 `turn_evidences` 가 함께 INSERT 된다

**페르소나별로 나눠서 단정한다.** 아래 조건을 하나도 만족하지 않는 턴이 있으면 실패로 잡는다.

| persona | 통과 조건 |
|---|---|
| `tech_lead` | `turn_evidences` 행이 있다 |
| `domain_lead` | `jd_requirement_ids` 가 비어 있지 않다 |
| `hr_manager` | `claim_ids` 가 비어 있지 않다 |

`tech_lead` 에만 `turn_evidences` 를 요구하는 이유는 나머지 둘이 코드가 아니라 JD·업종·자소서를
근거로 묻는 페르소나이기 때문이다. 전 페르소나에 `turn_evidences` 를 요구하면 정상 동작이
오탐으로 잡힌다.

### ② `is_ai_recommended` 가 5개를 넘지 않는다

`is_selected` 상한이 5개라서, 추천을 8개 내면 **채택률이 구조적으로 62.5% 를 못 넘어** 지표가
처음부터 망가진 채 쌓인다. 추천이 아무리 좋아도 상한 때문에 낮게 나온다.

> 원래 이 자리에는 "`topic_code` 가 `topic_taxonomy` 에 없으면 INSERT 가 실패한다 (FK)" 가
> 있었다. **`interview_turns.topic_code` 는 1차에 FK 를 걸지 않기로 확정**돼서 2차로 옮긴다.

### ③ 확정 해제한 레포가 DELETE 되지 않고 `is_selected=false` 로 남는다

`selection_source`(`ai_kept` / `ai_removed` / `user_added`) 기록까지 함께 검증한다.

정성 분석의 실제 입력은 채택률 숫자가 아니라 이 목록이다.

```sql
SELECT r.full_name, sr.ai_score, sr.ai_reason
FROM session_repositories sr JOIN repositories r ON ...
WHERE sr.selection_source = 'ai_removed';
```

n=10 이어도 이 목록을 직접 읽으면 바로 보인다 — "포크 레포를 추천했네", "3년 전 프로젝트를
1순위로 올렸네", "JD 가 백엔드인데 프론트 레포를 추천했네". 채택률 0.62 라는 숫자는 아무것도
알려주지 않지만, 뺀 레포의 이름과 추천 사유는 뭘 고쳐야 할지 정확히 알려준다.

`selection_source='user_added'`(더보기로 직접 추가) 는 **룰 필터가 놓친 레포**다 —
필터 조건을 어떻게 바꿔야 할지 나온다.

### ④ `events.event_name` 이 고정 10개 밖의 값이면 거부된다

## 2차로 옮긴 것

- `topic_code` FK 위반 테스트 (1차에 FK 없음)
- `evidence_conflicts` 행 생성 검증 (1차엔 빈 테이블)
- `verified` 판정 정확도 Eval (L2 전용)

## Eval — 무엇을 재는가

`repo_analyses.model` / `prompt_version` / `input_tokens` / `output_tokens` / `latency_ms` 가
존재하는 이유.

| # | 대상 | 방법 |
|---|---|---|
| 1 | `tech_stack` 정확도 회귀 | 사람이 손으로 라벨링한 레포 20개 골든셋과 `prompt_version` × `model` 별 일치율 비교 |
| 2 | `verified` 판정 정확도 (L2) | README 에는 있는데 코드엔 없는 기술을 실제로 `verified:false` 로 잡아냈는가. **거짓 주장 탐지율** — 서비스 차별점의 핵심이라 회귀가 나면 안 된다 |
| 3 | **추천 채택률과의 상관 ★** | `prompt_version` 별 `was_ai_recommended AND is_selected` 비율. 오프라인 정확도가 아니라 **실사용자가 AI 추천을 얼마나 받아들였는가**. 1번보다 이게 진짜 지표다 |

`model` 이 `prompt_version` 과 분리된 이유는 프롬프트를 그대로 두고 **모델만 바꾸는** 경우가
있기 때문이다 (비용 절감으로 Opus → Sonnet). 그때 품질이 얼마나 떨어지는지 비교하려면 두 축이
분리돼야 한다.

### 배치 vs 개별 비용 실측

배치(한 프롬프트에 여러 레포)로 가기로 했지만 **그게 정말 이득인지 검증이 안 됐다.**
토큰은 줄지만 품질과 지연은 나빠질 수 있다.

| 지표 | 계산 | 무슨 결정에 쓰이나 |
|---|---|---|
| 토큰 절감률 | `SUM(input_tokens)` 배치 vs 개별 | 배치 유지 여부 |
| 총 지연 | `latency_ms` | 배치 1회(15초) vs **개별 병렬(5초)**. 병렬이면 개별이 더 빠를 수 있다 |
| 위치별 품질 | 배치 내 순서별 `tech_stack` 정확도 | 뒤쪽 품질이 떨어지면(lost in the middle) 배치 크기를 줄인다 |
| 실패 전파 | `status='failed'` 비율 | 배치는 1건 파싱 실패가 전체를 날릴 위험. 개별은 1건만 실패 |

⚠ 위치별 품질은 **지금 스키마로는 못 잰다.** 같은 배치의 row 가 `analyzed_at` 이 전부 같아서
순서를 복원할 수 없다 → `batch_position SMALLINT` (P2, 미결).

배치의 진짜 위험은 비용이 아니라 **실패 전파**다. 그래서 배치 응답을 레포 단위로 부분 파싱하고,
`raw_output` 에 원문 전체를 남겨 **파싱 로직만 고쳐 재분석 없이 복구**할 수 있게 한다.
`raw_output` 을 유지하는 실질적 이유가 이것이다 — 단순 디버깅용이 아니다.

## 필수 지표 3개 (task-17)

- **평균 `depth`** — 1.2 면 꼬리질문이 거의 없다는 뜻이고, 그건 이 서비스의 실패다
- **`evidences.tool_name IS NULL` vs 값 있음 비율** — Tool 호출이 0이면 꼬리질문이 근거 없이
  나오고 있다는 뜻이다. Director→Tool 전환이 실제로 작동하는지 확인하는 유일한 수단
- **`selection_source='ai_removed'` 목록** — 매칭 로직 수정의 실제 근거
