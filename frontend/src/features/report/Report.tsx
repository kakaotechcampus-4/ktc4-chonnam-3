import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';

import { api } from '@/shared/api';
import { queryKeys } from '@/shared/queryKeys';
import Header from '@/shared/components/Header';
import type { AgentFeedback, AgentRole, ApiError } from '@/types/api';

const ROLE_LABELS: Record<AgentRole, string> = {
  tech_lead: 'Tech Lead',
  senior_developer: 'Senior Developer',
  manager: 'Manager',
};

const ROLE_INITIALS: Record<AgentRole, string> = {
  tech_lead: 'TL',
  senior_developer: 'SD',
  manager: 'MG',
};

export default function Report() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const reportQuery = useQuery({
    queryKey: queryKeys.report(id),
    queryFn: () => api.getInterviewReport(id),
    enabled: !!id,
  });

  const retryMutation = useMutation({
    mutationFn: () => api.retryInterview(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['interviews'] });
      navigate(`/interview/${data.interviewId}/prepare`);
    },
  });

  const report = reportQuery.data;
  const errorReason = (reportQuery.error as unknown as ApiError | undefined)?.error.reason;
  const reportUnavailable = errorReason === 'report_unavailable';

  return (
    <div className="flex min-h-screen flex-col bg-surface text-ink">
      <Header active="interview" />

      <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-7 px-7 py-6">
        {reportQuery.isLoading && <p className="text-sm text-muted">불러오는 중...</p>}
        {reportQuery.isError && !reportUnavailable && (
          <p className="text-sm text-error">리포트를 불러오지 못했어요.</p>
        )}
        {reportUnavailable && (
          <p className="text-sm text-muted">진행된 면접이 없어서 리포트를 만들 수 없어요.</p>
        )}

        {report && (
          <>
            <div className="flex flex-col gap-3">
              <p className="text-[11px] font-bold text-muted">면접 리포트</p>
              <h1 className="text-xl font-bold">{report.headline}</h1>
              <p className="text-xs text-muted">지원 포지션 · {report.position}</p>
            </div>

            <section className="flex flex-col gap-4">
              <SectionTitle>종합리포트</SectionTitle>
              <div className="flex items-center gap-6">
                <div
                  className="relative h-32 w-32 shrink-0 rounded-full"
                  style={{
                    background: `conic-gradient(var(--color-accent) ${report.totalScore * 3.6}deg, var(--color-line-soft) 0deg)`,
                  }}
                >
                  <div className="absolute inset-[10px] flex items-center justify-center rounded-full bg-surface">
                    <span className="text-3xl font-bold">{report.totalScore}</span>
                  </div>
                </div>
                <p className="flex-1 text-xs">{report.summary}</p>
              </div>
              <div className="flex flex-col gap-2">
                {report.scores.map((score) => (
                  <div key={score.key} className="flex items-center gap-3">
                    <span className="w-[150px] shrink-0 text-xs text-muted">{score.label}</span>
                    <div className="h-2 flex-1 rounded-full bg-line-soft">
                      <div
                        className="h-2 rounded-full bg-accent"
                        style={{ width: `${score.score}%` }}
                      />
                    </div>
                    <span className="w-7 shrink-0 text-right text-xs font-bold">{score.score}</span>
                  </div>
                ))}
              </div>
            </section>

            <hr className="border-line-soft" />

            <section className="flex flex-col gap-3.5">
              <SectionTitle>면접관별 피드백</SectionTitle>
              {report.agentFeedbacks.map((feedback) => (
                <FeedbackCard key={feedback.role} feedback={feedback} reportId={id} />
              ))}
            </section>

            <hr className="border-line-soft" />

            <section className="flex flex-col gap-3.5">
              <SectionTitle>면접 기록</SectionTitle>
              {report.turns.map((turn) => (
                <div
                  key={turn.turn}
                  className="flex flex-col gap-3 rounded-[10px] border border-line-soft p-4"
                >
                  <div className="flex gap-2.5">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[11px] font-bold text-accent">
                      {ROLE_INITIALS[turn.role]}
                    </span>
                    <div className="flex-1">
                      <p className="text-[11.5px] font-bold text-accent">
                        {ROLE_LABELS[turn.role]}
                      </p>
                      <p className="text-xs">{turn.question}</p>
                    </div>
                  </div>
                  <div className="flex gap-2.5">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-paper text-[11px] font-bold text-muted">
                      김
                    </span>
                    <div className="flex-1 rounded-lg border border-line-soft px-2.5 py-2">
                      <p className="text-xs text-muted">{turn.answer ?? '-'}</p>
                    </div>
                  </div>
                </div>
              ))}
            </section>

            <div className="flex justify-between gap-3">
              <button
                type="button"
                onClick={() => navigate('/home')}
                className="flex-1 rounded-md border border-line py-2.5 text-sm font-bold"
              >
                홈으로 가기
              </button>
              <button
                type="button"
                disabled={retryMutation.isPending}
                onClick={() => retryMutation.mutate()}
                className="flex-[3] rounded-md bg-accent py-2.5 text-sm font-bold text-white disabled:opacity-50"
              >
                {retryMutation.isPending ? '준비 중...' : '새 모의면접 시작하기'}
              </button>
            </div>
          </>
        )}
      </main>

      <footer className="flex items-center border-t border-line-soft px-5 py-2.5 text-[10.5px] text-muted">
        <span>© 2026 DEVON</span>
        <span className="flex-1" />
        <span>이용약관 · 개인정보처리방침</span>
      </footer>
    </div>
  );
}

function SectionTitle({ children }: { children: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="h-4 w-1 rounded-full bg-accent" />
      <h2 className="text-[15px] font-bold">{children}</h2>
    </div>
  );
}

function FeedbackCard({ feedback, reportId }: { feedback: AgentFeedback; reportId: string }) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () =>
      api.submitFeedbackDisagreement(reportId, {
        agentRole: feedback.role,
        reasonType: 'other',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.report(reportId) });
    },
  });

  return (
    <div className="flex gap-3 rounded-lg border border-line-soft p-3.5">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[11.5px] font-bold text-accent">
        {ROLE_INITIALS[feedback.role]}
      </span>
      <div className="flex flex-1 flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <p className="text-[13.5px] font-bold">{ROLE_LABELS[feedback.role]}</p>
          <span className="rounded-full bg-paper px-2.5 py-0.5 text-[10.5px] font-bold text-muted">
            {feedback.tags.join(' · ')}
          </span>
        </div>
        <div className="flex flex-col gap-1">
          {feedback.strengths.map((s, i) => (
            <p key={`s-${i}`} className="flex gap-1.5 text-xs">
              <span className="font-bold text-accent">✓</span>
              <span>{s}</span>
            </p>
          ))}
          {feedback.improvements.map((s, i) => (
            <p key={`i-${i}`} className="flex gap-1.5 text-xs">
              <span className="font-bold text-muted">△</span>
              <span>{s}</span>
            </p>
          ))}
        </div>
        {feedback.disagreementSubmitted ? (
          <p className="text-[11px] text-muted">의견 제출됨</p>
        ) : (
          <button
            type="button"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
            className="self-start text-[11px] text-muted hover:underline"
          >
            이 평가에 동의하지 않아요
          </button>
        )}
        {mutation.isError && <p className="text-[11px] text-error">제출에 실패했어요.</p>}
      </div>
    </div>
  );
}
