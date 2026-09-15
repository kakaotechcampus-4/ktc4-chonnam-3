import type { StepKey } from '@/types/api';

// Figma(3-2 · GitHub 분석 중, 3-3 · GitHub 분석 중 오류)의 체크리스트 순서 그대로 — StepKey와의
// 정확한 1:1 대응은 미확인, 개수(4개)와 위치로만 맞춤
export const STEP_ORDER: StepKey[] = ['fetch_repos', 'extract_jd', 'match_score', 'prepare_result'];

export const STEP_LABELS: Record<StepKey, string> = {
  fetch_repos: 'Repository 구조 확인',
  extract_jd: 'README · 설정 파일 읽기',
  match_score: '주요 기술 스택 감지 중',
  prepare_result: 'JD 요구사항과 매칭',
};
