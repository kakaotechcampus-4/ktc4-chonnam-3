# task-09 — analysis 구현

> 필요: task-07 (`shared/api.ts`, 인증 가드, 재연동 배너)
> 근거: `spec/frontend/features/analysis.md`

## 목표

공고·문서 입력 → 분석 진행 → 레포 확정까지의 화면을 구현한다.

## 작업

- 공고 입력 폼 + URL 유효성 검사 (Wanted URL만 허용)
- 파일 업로더 (드래그앤드롭, 형식·용량 검증) — 선택 즉시 `POST /documents/preview` 호출
- 401 재시도용 `FormData` 복제 처리는 `/documents/preview`에 적용한다 (`fetch`의 body는 1회 소비되므로 인터셉터가 복제 보관)
- `POST /analysis-runs` JSON 호출 (`postingUrl`, `documentId?`)
- `status: 'failed'` 시 "문서 없이 계속 진행" 확인 흐름 — 진행 시 `documentId` 생략
- 4-2-v2 체크리스트 + SSE 구독 — `EventSource` URL에 `/api` 프리픽스 직접 포함 (`shared/api.ts` 래퍼를 안 거침, `spec/frontend/architecture.md` "`/api` 프리픽스" 참고)
- `onerror` 시 `GET /analysis-runs/{runId}` 폴백 조회
- 4-3-v2 `failureReason` 9종 분기
- 5a-v2 레포 카드 컴포넌트
- 레포 카드 실패 상태 (회색 + `errorCode`)
- 공고 요구사항 리스트 (category 그룹핑)
- 포트폴리오 매칭 안내 문구
- `내 레포 더 보기` — `GET /analysis-runs/{runId}/candidates?page=N`. `202 analyzing`이면 `retryAfter` 간격 폴링 후 카드 추가
- 선택 5개 상한 처리
- `selectedRepoIds`는 `result` 쿼리 응답 도착 후 1회만 초기화한다. 리렌더마다 재설정하면 사용자 선택이 덮어써진다
- `POST /interviews` 확정 호출

## 완료 조건

- [ ] 공고 입력 폼 + URL 유효성 검사
- [ ] 파일 업로더 (드래그앤드롭, 형식·용량 검증)
- [ ] `POST /documents/preview` 호출 + 401 재시도용 FormData 복제 처리
- [ ] `status: 'failed'` 계속 진행 확인 흐름
- [ ] `POST /analysis-runs` JSON 호출
- [ ] 4-2-v2 체크리스트 + SSE 구독
- [ ] `onerror` 시 상태 폴백 조회
- [ ] 4-3-v2 `failureReason` 9종 분기
- [ ] 5a-v2 레포 카드 컴포넌트
- [ ] 레포 카드 실패 상태 (회색 + errorCode)
- [ ] 공고 요구사항 리스트 (category 그룹핑)
- [ ] 포트폴리오 매칭 안내 문구
- [ ] `내 레포 더 보기` — candidates 페이지네이션 + 202 폴링
- [ ] 선택 5개 상한 처리
- [ ] `POST /interviews` 확정 호출
- [ ] `npm run build` 통과
- [ ] `npm run lint` 통과

## 커밋

```
feat: add job analysis and repository selection flow
```
