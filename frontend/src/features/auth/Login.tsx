import { useSearchParams } from 'react-router-dom';
import { useState } from 'react';

const messages: Record<string, string> = {
  denied: 'GitHub 로그인이 취소되었습니다. 다시 시도해주세요.',
  invalid_state: '로그인 요청이 만료되었습니다. 다시 시도해주세요.',
  invalid_code: 'GitHub 인증을 완료하지 못했습니다. 다시 시도해주세요.',
  provider_unavailable: 'GitHub에 연결할 수 없습니다. 잠시 후 다시 시도해주세요.',
  service_unavailable: '로그인 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해주세요.',
  internal_error: '로그인을 완료하지 못했습니다. 잠시 후 다시 시도해주세요.',
  account_suspended: '이용이 정지된 계정입니다. 관리자에게 문의해주세요.',
  account_withdrawn: '탈퇴한 계정은 다시 이용할 수 없습니다.',
};

export default function Login() {
  const [searchParams] = useSearchParams();
  const error = searchParams.get('error');
  const message = error
    ? (messages[error] ?? '로그인을 완료하지 못했습니다. 다시 시도해주세요.')
    : undefined;
  const [isLeaving, setIsLeaving] = useState(false);

  return (
    <main className="login-page">
      <section className="login-content" aria-labelledby="login-title">
        <div className="w-full max-w-sm">
          <h1 id="login-title">DEVON</h1>
          <p className="login-copy">GitHub 계정으로 로그인하세요.</p>
          {message && (
            <p className="error-banner mb-4" role="alert">
              {message}
            </p>
          )}
          <a
            className="github-login"
            href="/api/auth/github/login"
            aria-disabled={isLeaving}
            onClick={() => setIsLeaving(true)}
          >
            <svg aria-hidden="true" viewBox="0 0 19 19">
              <use href="/icons.svg#github-icon" />
            </svg>
            {isLeaving ? 'GitHub로 이동 중' : 'GitHub으로 로그인'}
          </a>
        </div>
      </section>
    </main>
  );
}
