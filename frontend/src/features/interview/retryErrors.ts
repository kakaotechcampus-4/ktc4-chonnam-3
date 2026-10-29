// POST /interviews/{id}/retry 실패 안내 (spec/frontend/features/report.md). 리포트·마이페이지 공용.
export const RETRY_ERROR: Record<string, string> = {
  original_not_completed: '끝난 면접만 다시 시작할 수 있어요.',
  not_found: '면접을 찾을 수 없어요.',
  repository_unavailable: '선택했던 레포를 더 이상 쓸 수 없어요. 공고 입력부터 다시 시작해주세요.',
  session_limit_exceeded: '이미 진행 중인 면접이 있어요.',
  run_expired: '분석 결과가 만료됐어요. 공고 입력부터 다시 시작해주세요.',
};

// 같은 레포 조합으로는 다시 만들 수 없어 공고 입력으로 보내야 하는 reason.
export const RESTART_REASONS = new Set(['run_expired', 'repository_unavailable']);
