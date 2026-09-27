// 화면 개발용 상태로, 실제 세션 쿠키나 GitHub 토큰을 저장하지 않는다.
// OAuth 없이 기존 목업 화면을 볼 수 있도록 기본값은 로그인 상태다.
const KEY = 'msw.session';

export function hasMockSession() {
  return localStorage.getItem(KEY) !== 'expired';
}

export function setMockSession(state: 'authenticated' | 'expired') {
  localStorage.setItem(KEY, state);
}
