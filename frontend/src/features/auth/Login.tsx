import { useSearchParams } from 'react-router-dom';

import { BASE } from '@/shared/api';
import Footer from '@/shared/components/Footer';

const ERROR_MESSAGES: Record<string, string> = {
  denied: 'GitHub 로그인이 취소됐어요. 다시 시도해주세요.',
  invalid_state: '로그인 요청이 만료되었거나 올바르지 않아요. 다시 로그인해주세요.',
  invalid_code: 'GitHub 인증을 완료하지 못했어요. 다시 시도해주세요.',
  provider_unavailable: 'GitHub에 연결하지 못했어요. 잠시 후 다시 시도해주세요.',
  provider_configuration: 'GitHub 로그인 설정이 서비스와 맞지 않아요. 관리자에게 문의해주세요.',
  github_already_linked:
    '현재 GitHub 계정이 연결된 계정과 달라요. 기존에 연결한 GitHub 계정으로 다시 시도해주세요.',
  account_suspended: '이용이 정지된 계정이에요.',
  account_withdrawn: '탈퇴한 계정으로는 다시 가입할 수 없어요.',
};

function GithubMark() {
  return (
    <svg width="17" height="17" viewBox="0 0 17 17" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M8.50003 0C3.8062 0 0 3.90185 0 8.71517C0 12.5658 2.43551 15.8326 5.81286 16.985C6.23765 17.0657 6.39364 16.796 6.39364 16.5658C6.39364 16.358 6.38571 15.6714 6.38211 14.9432C4.01733 15.4704 3.51834 13.9149 3.51834 13.9149C3.13169 12.9075 2.57458 12.6397 2.57458 12.6397C1.8034 12.0988 2.63271 12.1099 2.63271 12.1099C3.48628 12.1714 3.93573 13.008 3.93573 13.008C4.69383 14.3404 5.92419 13.9551 6.40924 13.7325C6.4855 13.1692 6.70583 12.7848 6.94889 12.5671C5.06095 12.3467 3.07622 11.5994 3.07622 8.26002C3.07622 7.30856 3.40828 6.53106 3.95206 5.92075C3.8638 5.70121 3.57287 4.81482 4.03439 3.61436C4.03439 3.61436 4.74817 3.38012 6.37251 4.50772C7.05048 4.31456 7.77766 4.21777 8.50003 4.21449C9.22241 4.21777 9.95012 4.31456 10.6294 4.50772C12.2518 3.38012 12.9646 3.61436 12.9646 3.61436C13.4273 4.81482 13.1362 5.70121 13.0479 5.92075C13.5929 6.53106 13.9227 7.30849 13.9227 8.26002C13.9227 11.6073 11.9342 12.3444 10.0415 12.5602C10.3464 12.8306 10.618 13.361 10.618 14.1741C10.618 15.3401 10.6082 16.2787 10.6082 16.5658C10.6082 16.7977 10.7612 17.0694 11.1921 16.9839C14.5676 15.8302 17 12.5645 17 8.71517C17 3.90185 13.1943 0 8.50003 0Z"
        fill="white"
      />
    </svg>
  );
}

export default function Login() {
  const [searchParams] = useSearchParams();
  const error = searchParams.get('error') ?? '';
  // URL의 임의 값이나 상속된 속성을 오류 문구로 사용하지 않는다.
  const errorMessage = Object.hasOwn(ERROR_MESSAGES, error) ? ERROR_MESSAGES[error] : undefined;
  // 쿼리값을 이동 주소로 사용하지 않고 허용된 오류에만 고정 재연동 경로를 쓴다.
  const isLinkRetry =
    searchParams.get('flow') === 'link' &&
    [
      'denied',
      'invalid_code',
      'provider_unavailable',
      'provider_configuration',
      'github_already_linked',
    ].includes(error);

  return (
    <div className="flex min-h-screen flex-col bg-surface text-ink">
      <header className="flex items-center border-b border-line-soft px-7 py-3.5">
        <span className="text-[15px] font-bold">DEVON</span>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-7">
        <div className="flex w-[480px] max-w-full flex-col items-center gap-5 text-center">
          <p className="text-2xl font-bold">DEVON</p>
          <p className="text-base text-muted">
            {isLinkRetry
              ? '기존에 연결한 GitHub 계정으로 다시 연동해주세요.'
              : '회원가입 없이 GitHub 계정으로 바로 시작하세요'}
          </p>

          {errorMessage && (
            <p
              role="alert"
              className="w-full rounded-md border border-error-soft bg-error-soft px-4 py-3 text-sm text-error"
            >
              {isLinkRetry && error === 'denied'
                ? 'GitHub 재연동이 취소됐어요. 다시 시도해주세요.'
                : errorMessage}
            </p>
          )}

          <a
            href={`${BASE}/auth/github/${isLinkRetry ? 'link' : 'login'}`}
            className="flex h-12 w-full items-center justify-center gap-2.5 rounded-md bg-ink text-base font-bold text-white"
          >
            <GithubMark />
            {isLinkRetry ? 'GitHub 재연동하기' : 'GitHub로 계속하기'}
          </a>
        </div>
      </main>

      <Footer />
    </div>
  );
}
