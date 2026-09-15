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
    localStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({ ...change, nonce: `${Date.now()}-${Math.random()}` }),
    );
  } catch {
    // Storage can be disabled; the current tab still receives the event.
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
      // Ignore values not written by this client.
    }
  };

  window.addEventListener(AUTH_EVENT, onLocalChange);
  window.addEventListener('storage', onStorage);
  return () => {
    window.removeEventListener(AUTH_EVENT, onLocalChange);
    window.removeEventListener('storage', onStorage);
  };
}
