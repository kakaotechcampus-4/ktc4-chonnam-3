export const queryKeys = {
  me: ['me'] as const,
  profile: ['me', 'profile'] as const,
  home: ['home'] as const,
  interviews: (page: number) => ['interviews', { page }] as const,
  analysisRun: (runId: string) => ['analysis-run', runId] as const,
  analysisResult: (runId: string) => ['analysis-run', runId, 'result'] as const,
  interview: (id: string) => ['interview', id] as const,
  report: (id: string) => ['interview', id, 'report'] as const,
};
