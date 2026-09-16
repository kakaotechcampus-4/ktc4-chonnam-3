import { useSearchParams } from 'react-router-dom';

import { BASE } from '@/shared/api';

export default function Login() {
  const [searchParams] = useSearchParams();
  const denied = searchParams.get('error') === 'denied';

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-paper px-6 text-ink">
      <div className="flex w-[360px] max-w-full flex-col items-center gap-6 text-center">
        <div className="flex flex-col gap-2">
          <p className="text-lg font-bold">DEVON</p>
          <p className="text-sm text-muted">
            GitHub 프로젝트 기반으로 진행하는 AI 모의면접 서비스예요.
          </p>
        </div>

        {denied && (
          <p className="w-full rounded-card border border-error-soft bg-error-soft px-4 py-3 text-sm text-error">
            GitHub 로그인이 취소됐어요. 다시 시도해주세요.
          </p>
        )}

        <a
          href={`${BASE}/auth/github/login`}
          className="flex w-full items-center justify-center gap-2 rounded-card bg-accent py-3 text-sm font-bold text-white"
        >
          GitHub으로 로그인
        </a>
      </div>
    </div>
  );
}
