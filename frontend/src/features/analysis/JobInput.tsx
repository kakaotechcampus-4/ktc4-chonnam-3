import { useState } from 'react';
import type { DragEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

import { api } from '@/shared/api';
import AppHeader from '@/shared/components/AppHeader';
import type { ApiError } from '@/types/api';

const MB = 1024 * 1024;

type FileFieldConfig = {
  label: string;
  accept: string;
  hint: string;
  maxBytes: number;
};

const COVER_LETTER: FileFieldConfig = {
  label: '자기소개서',
  accept: '.pdf,.docx',
  hint: 'PDF, DOCX · 최대 10MB',
  maxBytes: 10 * MB,
};

const PORTFOLIO: FileFieldConfig = {
  label: '포트폴리오',
  accept: '.pdf',
  hint: 'PDF · 최대 20MB',
  maxBytes: 20 * MB,
};

function isValidJobUrl(value: string) {
  return /^https?:\/\/.+/.test(value.trim());
}

function validateFile(file: File, config: FileFieldConfig): string | null {
  const ext = `.${file.name.split('.').pop()?.toLowerCase()}`;
  if (!config.accept.split(',').includes(ext)) return '지원하지 않는 파일 형식이에요.';
  if (file.size > config.maxBytes) return '파일 용량이 너무 커요.';
  return null;
}

function Dropzone({
  config,
  file,
  error,
  onSelect,
}: {
  config: FileFieldConfig;
  file: File | null;
  error: string | null;
  onSelect: (file: File | null) => void;
}) {
  const [dragOver, setDragOver] = useState(false);

  function pickFile(fileList: FileList | null) {
    const picked = fileList?.[0] ?? null;
    if (!picked) return;
    onSelect(picked);
  }

  function handleDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setDragOver(false);
    pickFile(e.dataTransfer.files);
  }

  return (
    <div className="mb-6">
      <label className="mb-2 block text-sm text-ink">
        {config.label} <span className="text-muted">(선택)</span>
      </label>
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-card border border-dashed px-4 py-8 text-center ${
          dragOver ? 'border-accent bg-accent-soft' : 'border-line'
        }`}
      >
        <input
          type="file"
          accept={config.accept}
          className="hidden"
          onChange={(e) => pickFile(e.target.files)}
        />
        <span className="mb-2 text-xl text-accent">+</span>
        <span className="text-sm text-ink">
          {file ? file.name : '파일을 드래그하거나 클릭해서 업로드'}
        </span>
        <span className="mt-1 text-xs text-muted">{config.hint}</span>
      </label>
      {error && <p className="mt-1 text-xs text-error">{error}</p>}
    </div>
  );
}

export default function JobInput() {
  const navigate = useNavigate();

  const [jobUrl, setJobUrl] = useState('');
  const [urlTouched, setUrlTouched] = useState(false);
  const [coverLetter, setCoverLetter] = useState<File | null>(null);
  const [coverLetterError, setCoverLetterError] = useState<string | null>(null);
  const [portfolioFile, setPortfolioFile] = useState<File | null>(null);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);

  const urlValid = isValidJobUrl(jobUrl);

  const mutation = useMutation({
    mutationFn: (formData: FormData) => api.createAnalysisRun(formData),
    onSuccess: ({ runId }) => navigate(`/interview/analyzing/${runId}`),
  });

  function selectCoverLetter(file: File | null) {
    if (!file) return;
    const error = validateFile(file, COVER_LETTER);
    setCoverLetterError(error);
    setCoverLetter(error ? null : file);
  }

  function selectPortfolio(file: File | null) {
    if (!file) return;
    const error = validateFile(file, PORTFOLIO);
    setPortfolioError(error);
    setPortfolioFile(error ? null : file);
  }

  function handleSubmit() {
    if (!urlValid || mutation.isPending) return;

    const formData = new FormData();
    formData.set('jobUrl', jobUrl.trim());
    if (coverLetter) formData.set('coverLetter', coverLetter);
    if (portfolioFile) formData.set('portfolioFile', portfolioFile);

    mutation.mutate(formData);
  }

  const errorMessage = mutation.error
    ? ((mutation.error as ApiError)?.error?.message ?? '분석 시작에 실패했어요. 다시 시도해주세요.')
    : null;

  return (
    <div className="min-h-svh bg-paper">
      <AppHeader />

      <main className="mx-auto max-w-lg px-4 py-12">
        <p className="mb-2 text-sm text-muted">모의면접 · 1 / 3</p>
        <h1 className="mb-6 text-2xl font-bold text-ink">면접 보실 공고를 입력해주세요</h1>

        <div className="rounded-card border border-line-soft bg-surface p-6">
          <label className="mb-2 block text-sm text-ink">
            공고 URL <span className="text-error">*</span>{' '}
            <span className="ml-1 rounded-full bg-accent-soft px-2 py-0.5 text-xs text-accent">
              필수
            </span>
          </label>
          <input
            type="text"
            value={jobUrl}
            onChange={(e) => setJobUrl(e.target.value)}
            onBlur={() => setUrlTouched(true)}
            placeholder="https://careers.example.com/jobs/123"
            className="w-full rounded-card border border-line-soft px-4 py-3 text-sm text-ink outline-none focus:border-accent"
          />
          <p className={`mt-1 text-xs ${urlTouched && !urlValid ? 'text-error' : 'text-muted'}`}>
            {urlTouched && !urlValid ? 'URL을 입력해보세요' : '채용 공고 페이지 주소를 붙여넣어주세요'}
          </p>

          <div className="mt-6">
            <Dropzone
              config={COVER_LETTER}
              file={coverLetter}
              error={coverLetterError}
              onSelect={selectCoverLetter}
            />
            <Dropzone
              config={PORTFOLIO}
              file={portfolioFile}
              error={portfolioError}
              onSelect={selectPortfolio}
            />
          </div>

          {errorMessage && (
            <p className="mb-4 rounded-card bg-error-soft px-4 py-3 text-sm text-error">
              {errorMessage}
            </p>
          )}

          <button
            type="button"
            disabled={!urlValid || mutation.isPending}
            onClick={handleSubmit}
            className="w-full rounded-card bg-accent py-3 text-sm font-medium text-white disabled:bg-line disabled:text-muted"
          >
            {mutation.isPending ? '분석 시작 중...' : '분석 시작'}
          </button>
        </div>
      </main>
    </div>
  );
}
