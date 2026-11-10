import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { BASE } from '@/shared/api';
import Footer from '@/shared/components/Footer';
import { PERSONA_IMAGES, PERSONA_LABELS } from '@/shared/persona';
import type { Persona } from '@/types/api';

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

// 로그인 화면 예시. 면접관 세 명이 각자 관점에서 저장소의 한 줄을 짚어 묻는다(mock payment-service 기반).
type Scene = {
  persona: Persona;
  file: string;
  lines: [number, string][];
  marked: number;
  question: string;
  /** 문서 장면은 고정폭 대신 본문 글꼴로 보여 준다. 한글이 고정폭에서 벌어져 보여서다. */
  prose?: boolean;
};

const SCENES: Scene[] = [
  {
    persona: 'tech_lead',
    file: 'payment-service / RetryPolicy.kt',
    lines: [
      [12, 'fun nextDelay(attempt: Int): Duration {'],
      [13, '  val base = Duration.ofMillis(200)'],
      [14, '  val capped = min(attempt, MAX_ATTEMPTS)'],
      [15, '  return base.multipliedBy(1L shl capped)'],
      [16, '}'],
    ],
    marked: 15,
    question:
      '재시도 간격을 두 배씩 늘린 이유가 있나요? 같은 결제가 두 번 승인되지 않게 어떻게 막았는지도 들려주세요.',
  },
  {
    persona: 'domain_lead',
    file: 'payment-service / PaymentService.kt',
    lines: [
      [41, 'fun approve(order: Order): Payment {'],
      [42, '  if (order.amount > dailyLimit(order.userId)) {'],
      [43, '    return Payment.held(order, "LIMIT")'],
      [44, '  }'],
      [45, '  return gateway.charge(order)'],
    ],
    marked: 43,
    question:
      '한도를 넘은 결제를 바로 거절하지 않고 보류로 둔 이유가 궁금해요. 사용자에게는 이 상태를 어떻게 안내하나요?',
  },
  {
    persona: 'hr_manager',
    file: 'payment-service / README.md',
    prose: true,
    lines: [
      [8, '## 내가 맡은 부분'],
      [9, '- 결제 재시도 정책 설계와 구현'],
      [10, '- 장애 대응 문서 작성'],
      [11, '- 팀 코드 리뷰 규칙 정리'],
      [12, '- 신규 팀원 온보딩 가이드'],
    ],
    marked: 11,
    question:
      '코드 리뷰 규칙을 정할 때 팀원과 의견이 달랐던 적이 있나요? 어떻게 합의했는지 들려주세요.',
  },
];

const SCENE_MS = 4000;

/** 면접관 질문 장면을 차례로 바꾼다. 마우스를 올리거나 포커스가 있으면 멈추고, 움직임 줄이기면 돌지 않는다. */
function QuestionScenes() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    // index를 의존성에 두어 직접 고른 뒤에도 같은 간격을 다시 센다.
    const timer = setTimeout(() => setIndex((i) => (i + 1) % SCENES.length), SCENE_MS);
    return () => clearTimeout(timer);
  }, [paused, index]);

  /**
   * 카드 틀·말풍선 틀은 그대로 두고 안의 내용만 바꾼다. 나가는 내용이 먼저 사라지고,
   * 파일명·코드·질문은 같은 순간에 함께 나타난다.
   */
  const layer = (i: number, extra = '') => ({
    className: `[grid-area:1/1] transition-[opacity,transform] ease-out motion-reduce:transition-none ${extra} ${
      i === index ? 'translate-y-0 opacity-100 duration-500' : 'opacity-0 duration-200'
    }`,
    // 나가는 내용이 200ms 안에 사라진 뒤 파일명·코드·질문이 함께 나타나 두 글자가 겹쳐 보이지 않는다.
    style: { transitionDelay: i === index ? '200ms' : '0ms' },
  });

  return (
    <figure
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      className="w-full overflow-hidden rounded-[14px] border border-accent/60 bg-[#f4f6f7] text-[#3b4046]"
    >
      <figcaption className="sr-only">
        예시: 개발팀·기획팀·인사팀 면접관이 저장소의 코드와 문서 한 줄을 짚어 질문한다.
      </figcaption>
      <div aria-hidden>
        <p className="grid border-b border-line-soft px-5 py-3 text-[12px] text-[#a3a9b0]">
          {SCENES.map((scene, i) => (
            <span key={scene.persona} {...layer(i)}>
              {scene.file}
            </span>
          ))}
        </p>
        <div className="grid py-3">
          {SCENES.map((scene, i) => (
            <pre
              key={scene.persona}
              {...layer(
                i,
                `overflow-hidden text-[10.5px] leading-[1.9] sm:text-[13px] ${
                  scene.prose ? 'font-sans' : 'font-mono'
                }`,
              )}
            >
              {scene.lines.map(([no, code]) => (
                <span
                  key={no}
                  className={
                    no === scene.marked
                      ? 'block border-l-[3px] border-accent bg-accent-soft pl-[17px] pr-5'
                      : 'block pl-5 pr-5'
                  }
                >
                  <span className="inline-block w-6 select-none text-[#a3a9b0] sm:w-8">{no}</span>
                  {code}
                </span>
              ))}
            </pre>
          ))}
        </div>
        <div className="mx-4 grid rounded-[10px] border border-line-soft bg-surface p-4 text-ink">
          {SCENES.map((scene, i) => (
            <div
              key={scene.persona}
              {...layer(i, i === index ? 'flex gap-3' : 'flex translate-y-1.5 gap-3')}
            >
              <img
                src={PERSONA_IMAGES[scene.persona]}
                alt=""
                className="h-9 w-9 shrink-0 rounded-full object-cover"
              />
              <div>
                <p className="text-[13px] font-bold">
                  {PERSONA_LABELS[scene.persona]} 면접관
                  <span className="ml-2 font-normal text-muted">{scene.marked}번째 줄</span>
                </p>
                <p className="mt-1 break-keep text-[14px] leading-relaxed">{scene.question}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
      {/* 지금 묻는 면접관. 누르면 그 장면으로 바꾼다. */}
      <div className="flex gap-1.5 px-4 pb-4 pt-3">
        {SCENES.map((scene, i) => (
          <button
            key={scene.persona}
            type="button"
            aria-pressed={i === index}
            onClick={() => setIndex(i)}
            className={`rounded-full px-3 py-1 text-[12px] transition-colors duration-500 focus-visible:outline-2 focus-visible:outline-accent ${
              i === index ? 'bg-accent text-white' : 'text-muted hover:text-ink'
            }`}
          >
            {PERSONA_LABELS[scene.persona]}
          </button>
        ))}
      </div>
    </figure>
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
      <header className="px-8 py-5">
        <span className="text-[22px] font-black tracking-tight">DEVON</span>
      </header>

      <main className="flex flex-1 items-center px-6 pb-[8vh] sm:px-10">
        <div className="mx-auto grid w-full max-w-5xl items-center gap-12 lg:grid-cols-[1fr_minmax(0,500px)] lg:gap-16">
          <div className="flex flex-col items-start">
            <h1 className="break-keep text-[36px] font-black leading-[1.15] tracking-tight sm:text-[52px]">
              DEVON
            </h1>
            <p className="mt-4 max-w-[30em] break-keep text-xl font-semibold leading-snug text-ink sm:text-[24px]">
              내 저장소로 보는 모의면접
            </p>

            {errorMessage && (
              <p
                role="alert"
                className="mt-6 w-full max-w-[400px] rounded-md border border-error-soft bg-error-soft px-4 py-3 text-sm text-error"
              >
                {isLinkRetry && error === 'denied'
                  ? 'GitHub 재연동이 취소됐어요. 다시 시도해주세요.'
                  : errorMessage}
              </p>
            )}

            {/*
              디자인 확인용. 아이디·비밀번호 로그인은 없어서(spec/frontend/features/auth.md: GitHub OAuth 단일 로그인)
              입력과 버튼을 비활성으로 둔다. 실제 로그인은 아래 GitHub 버튼뿐이다.
            */}
            <form
              aria-label="아이디 로그인"
              onSubmit={(event) => event.preventDefault()}
              className="mt-8 flex w-full max-w-[400px] flex-col gap-2.5"
            >
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                아이디
                <input
                  type="text"
                  disabled
                  placeholder="아이디를 입력하세요"
                  className="h-12 rounded-md border border-line bg-surface px-4 text-base font-normal placeholder:text-muted disabled:cursor-not-allowed disabled:opacity-60"
                />
              </label>
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                비밀번호
                <input
                  type="password"
                  disabled
                  autoComplete="off"
                  placeholder="비밀번호를 입력하세요"
                  className="h-12 rounded-md border border-line bg-surface px-4 text-base font-normal placeholder:text-muted disabled:cursor-not-allowed disabled:opacity-60"
                />
              </label>
              <button
                type="submit"
                disabled
                className="mt-1 h-12 rounded-md border border-line text-base font-bold text-muted disabled:cursor-not-allowed"
              >
                로그인
              </button>
              <p className="mt-1 text-center text-sm text-muted">
                계정이 없나요?{' '}
                <button
                  type="button"
                  disabled
                  className="font-semibold text-ink disabled:cursor-not-allowed"
                >
                  회원가입
                </button>
              </p>
            </form>

            <div className="my-5 flex w-full max-w-[400px] items-center gap-3 text-xs text-muted">
              <span className="h-px flex-1 bg-line-soft" />
              또는
              <span className="h-px flex-1 bg-line-soft" />
            </div>

            <a
              href={`${BASE}/auth/github/${isLinkRetry ? 'link' : 'login'}`}
              className="flex h-12 w-full max-w-[400px] items-center justify-center gap-2.5 rounded-md bg-ink text-base font-bold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              <GithubMark />
              {isLinkRetry ? 'GitHub 재연동하기' : 'GitHub로 계속하기'}
            </a>
            <p className="mt-3 text-sm text-muted">
              {isLinkRetry
                ? '기존에 연결한 GitHub 계정으로 다시 연동해주세요.'
                : '회원가입 없이 GitHub 계정으로 바로 시작하세요'}
            </p>
          </div>

          <QuestionScenes />
        </div>
      </main>

      {/* 로그인 화면은 헤더와 푸터 경계선 없이 한 면으로 보인다. */}
      <div className="[&>footer]:border-t-0">
        <Footer />
      </div>
    </div>
  );
}
