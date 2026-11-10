import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';

import { api } from '@/shared/api';
import { PERSONA_LABELS } from '@/shared/persona';
import { isApiError, type AgentFeedback, type ReasonType } from '@/types/api';

const REASONS = [
  { value: 'factual_error', label: '사실과 다른 내용이 있어요' },
  { value: 'insufficient_basis', label: '평가 근거가 부족해요' },
  { value: 'overly_harsh', label: '평가가 지나치게 엄격해요' },
  { value: 'unclear_intent', label: '평가 의도를 이해하기 어려워요' },
  { value: 'other', label: '기타 의견이 있어요' },
] satisfies { value: ReasonType; label: string }[];

type Props = {
  interviewId: string;
  revision: number;
  feedback: AgentFeedback;
  onRefresh: () => void;
};

export default function FeedbackDisagreement({
  interviewId,
  revision,
  feedback,
  onRefresh,
}: Props) {
  const [open, setOpen] = useState(false);
  const [reasonType, setReasonType] = useState<ReasonType>('factual_error');
  const [comment, setComment] = useState('');
  const submission = useMutation({
    // 보고 있던 리포트가 바뀌면 기존 평가에 대한 의견을 새 평가로 옮기지 않는다.
    mutationFn: () =>
      api.submitFeedbackDisagreement(interviewId, {
        persona: feedback.persona,
        reasonType,
        expectedRevision: revision,
        ...(comment.trim() ? { comment: comment.trim() } : {}),
      }),
    onSuccess: () => {
      setOpen(false);
      onRefresh();
    },
  });
  const errorReason = isApiError(submission.error) ? submission.error.error.reason : null;
  const duplicate = errorReason === 'already_submitted';
  const stale = errorReason === 'report_unavailable';
  const submitted = feedback.disagreementSubmitted || submission.isSuccess || duplicate;

  if (submitted) {
    return (
      <p role="status" className="text-[11px] text-muted">
        {duplicate ? '이미 이 평가에 대한 의견이 접수됐어요.' : '의견이 접수됐어요.'}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="self-start text-[11px] text-muted underline"
        >
          이 평가에 동의하지 않아요
        </button>
      ) : (
        <form
          aria-label={`${PERSONA_LABELS[feedback.persona]} 평가 이의 제기`}
          className="flex flex-col gap-2 rounded-md bg-paper p-3"
          onSubmit={(event) => {
            event.preventDefault();
            submission.mutate();
          }}
        >
          <label className="flex flex-col gap-1 text-xs">
            의견 유형
            <select
              value={reasonType}
              disabled={submission.isPending || stale}
              className="rounded-md border border-line bg-surface p-2"
              onChange={(event) => {
                const reason = REASONS.find((item) => item.value === event.target.value);
                if (reason) setReasonType(reason.value);
              }}
            >
              {REASONS.map((reason) => (
                <option key={reason.value} value={reason.value}>
                  {reason.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs">
            추가 의견 (선택, 최대 500자)
            <textarea
              value={comment}
              maxLength={500}
              rows={3}
              disabled={submission.isPending || stale}
              onChange={(event) => setComment(event.target.value)}
              className="rounded-md border border-line bg-surface p-2"
            />
          </label>
          <p className="text-[11px] text-muted">
            의견을 접수해 검토해요. 제출만으로 점수가 바뀌지는 않아요.
          </p>
          {submission.isError && (
            <div className="flex flex-col items-start gap-2">
              <p role="alert" className="text-xs text-error">
                {stale
                  ? '리포트가 변경됐거나 현재 의견을 접수할 수 없어요. 최신 리포트를 확인한 뒤 다시 제출해주세요.'
                  : '의견을 접수하지 못했어요. 잠시 후 다시 시도해주세요.'}
              </p>
              {stale && (
                <button type="button" onClick={onRefresh} className="text-xs underline">
                  최신 리포트 불러오기
                </button>
              )}
            </div>
          )}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={submission.isPending || stale}
              className="rounded-md bg-accent px-3 py-2 text-xs font-bold text-white disabled:opacity-50"
            >
              {submission.isPending ? '접수 중...' : '의견 보내기'}
            </button>
            <button
              type="button"
              disabled={submission.isPending}
              onClick={() => setOpen(false)}
              className="rounded-md border border-line px-3 py-2 text-xs"
            >
              취소
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
