import { useNavigate } from 'react-router-dom';

import { isApiError } from '@/types/api';
import type { AnalysisInputState } from '@/features/analysis/steps';

type Props = {
  error: unknown;
  onRetry: () => void;
  postingUrl: string;
};

/** 분석 진행·실패·레포 선택 화면이 run 조회에 실패했을 때의 안내. 410은 다시 불러와도 같다. */
export default function RunLoadError({ error, onRetry, postingUrl }: Props) {
  const navigate = useNavigate();
  const expired = isApiError(error) && error.error.reason === 'run_expired';

  return (
    <div className="flex flex-col gap-3">
      <p role="alert" className="text-sm text-error">
        {expired
          ? '분석 결과가 만료됐어요. 공고 입력부터 다시 시작해주세요.'
          : '분석 정보를 불러오지 못했어요.'}
      </p>
      {expired ? (
        <button
          type="button"
          onClick={() =>
            navigate('/interview/new', { state: { postingUrl } satisfies AnalysisInputState })
          }
          className="self-start rounded-md bg-accent px-4 py-2 text-sm font-bold text-white"
        >
          공고 다시 입력
        </button>
      ) : (
        <button
          type="button"
          onClick={onRetry}
          className="self-start rounded-md border border-line px-4 py-2 text-sm"
        >
          다시 시도
        </button>
      )}
    </div>
  );
}
