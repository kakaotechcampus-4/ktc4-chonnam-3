export const AUTH_LOCK_NAME = 'devon-auth';

const AUTH_EVENT = 'devon:auth-change';
const AUTH_STORAGE_KEY = 'devon-auth-change';

export type AuthChange = {
  reason: string;
  redirect: boolean;
};

let epoch = 0;

function dispatch(change: AuthChange) {
  epoch += 1;
  window.dispatchEvent(new CustomEvent<AuthChange>(AUTH_EVENT, { detail: change }));
}

export function getAuthEpoch() {
  return epoch;
}

export function publishAuthChange(change: AuthChange) {
  dispatch(change);
  try {
    // 매번 다른 nonce를 넣어 같은 변경이 반복되어도 다른 탭에서 storage 이벤트가 발생하게 한다.
    localStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({ ...change, nonce: `${Date.now()}-${Math.random()}` }),
    );
  } catch {
    // 브라우저 저장소가 비활성화되어 있어도 현재 탭에는 이벤트가 전달된다.
  }
}

export function subscribeAuthChanges(listener: (change: AuthChange) => void) {
  const onLocalChange = (event: Event) => listener((event as CustomEvent<AuthChange>).detail);
  const onStorage = (event: StorageEvent) => {
    if (event.key !== AUTH_STORAGE_KEY || !event.newValue) return;
    try {
      const change = JSON.parse(event.newValue) as AuthChange;
      dispatch(change);
    } catch {
      // 이 클라이언트가 작성하지 않은 값은 무시한다.
    }
  };

  window.addEventListener(AUTH_EVENT, onLocalChange);
  window.addEventListener('storage', onStorage);
  return () => {
    window.removeEventListener(AUTH_EVENT, onLocalChange);
    window.removeEventListener('storage', onStorage);
  };
}
