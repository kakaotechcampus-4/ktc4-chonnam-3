# 분석 Run

상태: Sprint 1 FIX.

## 입력

`POST /analysis-runs`

- `postingUrl`: 필수. Sprint 1은 Wanted URL만 허용한다.
- `documentId`: 선택. `POST /documents/preview`에서 생성한 문서만 허용한다.

문서 없이 공고 URL만으로 분석할 수 있다. 공고는 필수이고, Wanted fetch/extract 실패 또는 unsupported site는 hard blocker다.

## Wanted 공고 수집·분류

공고는 면접 분석의 원문으로 사용한다. 채용이 마감되었더라도 본문을 가져올 수 있으면 분석한다. Wanted의 `status`, `due_time`만으로 수집을 실패 처리하지 않는다. HTTP·네트워크 오류, 잘못된 응답, 빈 본문은 `jd_fetch_failed`, 본문은 있지만 추출 가능한 구조화 항목이 없으면 `jd_extraction_failed`로 처리한다.

API `category`는 화면의 항목 구분이고, DB·AI의 `requirement_type`은 필수·우대 여부다. 기존 [API enum](../../shared/contracts/openapi.yaml)과 [DB enum](../../../backend/docs/db-schema.md)을 각각 유지하며 다음과 같이 변환한다.

| Wanted 원문 필드 (`source_field`) | DB·AI `requirement_type` | API `category` |
| --- | --- | --- |
| `requirements` | `required` | `required` |
| `preferred_points` | `preferred` | `preferred` |
| `main_tasks` | `unknown` | `responsibility` |

주요 업무만으로 필수·우대 여부를 추측하지 않는다. `unknown`은 `responsibility`의 별칭이 아니며, 원문 출처가 `main_tasks`일 때만 API에서 주요 업무로 표시한다. 다른 출처의 `unknown`을 주요 업무로 바꾸지 않는다.

`JdRequirementDraft`는 API `category`와 함께 계산 속성 `requirement_type`, `source_field`를 제공한다. 저장 호출부는 두 속성을 명시적으로 읽고 원문 출처도 보존해야 재조회 후 같은 화면 분류를 복원할 수 있다. `category`를 DB `requirement_type`에 그대로 저장하지 않는다. 이 변환은 기존 enum을 연결하는 규칙이며 새 DB enum이나 컬럼을 추가하지 않는다.

### 공고 재조회와 이전 자료 보존

[0014 결정](../../ai/decisions/0014-minimal-change-revision.md)에 따라 normalized Wanted URL로 재사용 가능한 현재 성공 자료를 찾는다. 재사용 기간은 [현재 로컬 기준 채택 결정](../../shared/decisions/0002-local-policy-baseline.md)에 따라 `fetched_at` 기준 7일(`JD_REUSE_TTL_DAYS=7`)이다. 재조회한 내용이 같으면 기존 자료를 재사용하고, 내용이 바뀌면 새 `job_postings` ID와 그에 연결된 요구사항 ID로 저장한다.

이전 공고·요구사항을 덮어쓰거나 삭제 후 재삽입하지 않는다. 이미 확정된 run·면접·질문·리포트는 당시 자료 ID를 계속 참조하며, 새 면접도 해당 run에 확정된 자료를 사용한다. 새 분석 run은 재사용 규칙에 맞는 현재 자료를 선택한다. 별도 공고 이력 테이블이나 질문별 본문 복사본은 만들지 않는다.

이는 기존 URL 재사용 규칙에 당시 자료를 보존하는 DB 저장 동작을 보완한 결정이다. 내용 동일성의 비교 필드·정규화, 재확인 시각의 저장·갱신과 동시 수집의 중복 방지 제약은 AI-L02·AI-L03·AI-L12에서 정한다. 7일 정책의 채택은 재사용 기능 구현 완료를 뜻하지 않는다. 실제 구현은 재사용 기간, 동일 내용 재사용, 변경 내용의 새 ID, 이전 참조 보존을 검증해야 한다.

## 단계

분석 step key는 7개로 고정한다.

1. `doc_extract`: Sprint 1에서는 포트폴리오 preview 문서에서 추출한 GitHub URL을 analysis context에 반영한다. claim 추출은 하지 않는다.
2. `repo_select`: 전체 public repo에 대해 L0-a lightweight ranking과 filter를 계산한다.
3. `repo_detail`: 분석 batch repo의 README, languages, head SHA, commit count, user commit count를 수집한다.
4. `jd_fetch`: Wanted 공개 JSON을 수집한다.
5. `jd_extract`: Wanted 구조화 필드에서 JD requirement와 tech tag를 만든다.
6. `repo_analyze`: batch repo에 대해 L1 shallow LLM 분석을 수행한다.
7. `match_score`: JD와 repo analysis를 매칭해 추천 카드 정보를 만든다.

## Candidate Ranking

`analysis_repo_candidates`에 run 종속 후보 순위를 저장한다. Redis를 원본으로 쓰지 않는다.

- 전체 public repo에 대해 `base_rank`와 `ranking_score`를 계산한다.
- 첫 batch 10개는 단순 상위 10개가 아니라 혼합 전략으로 구성한다.
- 첫 batch는 JD 수집·추출보다 먼저 확정되므로 JD signal을 사용하지 않는다.
- 첫 batch는 포트폴리오 GitHub URL 언급 repo 최대 3개, base rank top 최대 5개, high contribution 최대 2개를 중복 제거해 최대 10개로 만든다.
- JD 기반 추천 이유는 `match_score` 단계와 후속 candidate page/ranking에서만 사용한다. [0017 결정](../../ai/decisions/0017-recommendation-score-deferral.md)에 따라 Sprint 1 숫자 match score는 보류한다.
- 제외 repo도 `filter_status='excluded'`, `filter_reason`으로 저장한다. 기본 응답에는 `eligible`만 노출한다.

주요 필드:

- `analysis_job_id`
- `repository_id`
- `base_rank`
- `batch_no`
- `batch_rank`
- `selection_reason`: `portfolio_mentioned`, `base_rank_top`, `high_contribution`, `other`. `jd_signal`은 첫 batch에는 사용하지 않고, JD 확보 뒤 후속 ranking 신호로만 사용할 수 있다.
- `ranking_score`
- `ranking_signals JSONB`
- `filter_status`: `eligible`, `excluded`
- `filter_reason`: `private`, `fork`, `archived`, `no_language`, `too_small`, `inaccessible`

Sprint 1 추천 카드는 기존 `recommended`, `recommendReason`, `matchedRequirementIds`와 최대 5개 추천을 유지하며 필수·nullable `matchScore`는 null을 반환한다. null만으로 실패나 추천 제외를 판단하지 않고 새 점수 정렬을 추가하지 않는다. 기존 `repo_match_scores`의 null 저장·응답 변환은 구현 시 확인한다.

[0018 결정](../../ai/decisions/0018-existing-baseline-bulk-resolution.md)에 따라 공고 기술 태그와 유효한 L1 기술 목록을 직접 비교하고, 일치 기술이 있는 선택 가능 저장소 중 기존 run 후보 순서에서 앞 5개까지 추천한다. 모든 page를 합쳐 0~5개이며, 후보 수집 순위를 JD 적합도 순위로 재해석하거나 추가 LLM 호출을 만들지 않는다. 공고 기술 정보가 없거나 일치가 없으면 정상 미추천이며 직접 선택은 유지한다.

추천 이유는 기술 관련성만 설명한다. 공고 전체 기술 태그가 각 요구사항에 복사되어 있으므로 `matchedRequirementIds`는 해당 문장에서도 일치 기술이 확인될 때만 연결하고 없으면 빈 목록을 사용한다. 경력 연수·요건 충족을 단정하지 않으며, 추천 갱신이 사용자의 기존 선택을 덮어쓰지 않는다. 이 채택은 실제 매칭·저장·응답 구현 완료를 뜻하지 않는다.

## 더 보기

`GET /analysis-runs/{runId}/candidates?page=N`

- 후보 page가 L0-b/L1 분석 완료면 `200`으로 repo card page를 반환한다.
- 미분석이면 ARQ page 분석 job을 enqueue하고 `202 { "status": "analyzing", "retryAfter": 3 }`를 반환한다.
- page 분석 상태는 `analysis_repo_candidate_pages`에 저장한다.
- 전체 `analysis_jobs.status`는 page 추가 분석 때문에 다시 `running`으로 되돌리지 않는다.

## 부분 실패

DB 상태:

- 일부 성공 + 일부 repo 실패: `analysis_jobs.status='partial'`
- 전부 실패: `analysis_jobs.status='failed'`

FE 상태 매핑:

- `queued`, `running` -> `running`
- `succeeded` -> `completed`
- `partial`, `failed`, `canceled` -> `failed`

`partial`이어도 `/analysis-runs/{runId}/result`는 조회 가능하다. 결과에는 `analyzedCount`, `failedCount`, `failedRepositories[]`를 포함한다.

## 중복 요청

중복 요청 재사용은 `POST /analysis-runs`에만 적용한다.

- fingerprint: `user_id`, normalized `posting_url`, `document_id` 또는 문서 해시/추출 GitHub URL 목록.
- 같은 fingerprint의 `queued/running` job이 있으면 새 job을 만들지 않고 `409 run_in_progress`와 공통 오류 본문의 `error.details.runId`로 기존 run ID를 반환한다. FE는 이 ID로 기존 분석 진행 화면으로 이동한다.
- 종료 상태(`succeeded`, `partial`, `failed`, `canceled`)면 새 run 생성을 허용한다.

## 선택 가능 조건

`POST /interviews`는 선택 repo가 모두 다음 조건을 만족해야 한다.

- 현재 run에 속함
- public, accessible
- candidate `eligible`
- L1 analysis `succeeded`
- 최소 1개, 최대 5개

불만족 시 `invalid_repository`, 0개면 `no_repository_selected`, 6개 이상이면 `too_many_repositories`.
