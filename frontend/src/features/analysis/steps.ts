import type { StepKey, StepStatus } from '@/types/api';

// api spec은 7단계(doc_extract~match_score)지만 Figma 체크리스트(3-2 · GitHub 분석 중,
// 3-3 · GitHub 분석 중 오류)는 4줄 — 파이프라인 순서를 유지한 채 인접 단계를 묶어 4그룹으로 표시.
// 그룹 경계는 임의 판단이라 디자인·기획 쪽 확인 필요
// (ponytail: 그룹 매핑은 가정, 명세에 그룹 개념이 생기면 그걸 따를 것)
export const STEP_GROUPS: { label: string; keys: StepKey[] }[] = [
  { label: '공고 문서 확인', keys: ['doc_extract'] },
  { label: 'Repository 구조 확인', keys: ['repo_select', 'repo_detail'] },
  { label: '공고 요구사항 분석', keys: ['jd_fetch', 'jd_extract'] },
  { label: '기술 스택 매칭', keys: ['repo_analyze', 'match_score'] },
];

export function groupStatus(
  keys: StepKey[],
  steps: Partial<Record<StepKey, StepStatus>>,
): StepStatus {
  if (keys.some((key) => steps[key] === 'failed')) return 'failed';
  if (keys.every((key) => steps[key] === 'completed')) return 'completed';
  if (keys.some((key) => steps[key] === 'running')) return 'running';
  return 'pending';
}
