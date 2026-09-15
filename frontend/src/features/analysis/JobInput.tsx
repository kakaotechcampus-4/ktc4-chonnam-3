import { useState } from 'react';
import type { DragEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/shared/api';
import { isApiError } from '@/types/api';
import type { DocumentKind, DocumentPreviewResponse, DocumentSource } from '@/types/api';

const MB = 1024 * 1024;

type FileFieldConfig = {
  kind: DocumentKind;
  label: string;
  accept: string;
  hint: string;
  maxBytes: number;
  allowUrl: boolean;
};

const COVER_LETTER: FileFieldConfig = {
  kind: 'cover_letter',
  label: '자기소개서',
  accept: '.pdf,.docx',
  hint: 'PDF, DOCX · 최대 10MB',
  maxBytes: 10 * MB,
  allowUrl: false,
};

const PORTFOLIO: FileFieldConfig = {
  kind: 'portfolio',
  label: '포트폴리오',
  accept: '.pdf',
  hint: 'PDF · 최대 10MB',
  maxBytes: 10 * MB,
  allowUrl: true,
};

const UPLOAD_ERROR: Record<string, string> = {
  file_too_large: '파일 용량이 너무 커요.',
  unsupported_media_type: '지원하지 않는 형식이에요.',
  url_unreachable: '링크를 불러올 수 없어요.',
};

const RUN_ERROR: Record<string, string> = {
  job_url_required: '공고 URL을 입력해주세요.',
  unsupported_site: '지원하지 않는 사이트예요.',
  url_unreachable: '공고를 불러올 수 없어요.',
};

function isHttpUrl(value: string) {
  return /^https?:\/\/.+/.test(value.trim());
}

function validateFile(file: File, config: FileFieldConfig): string | null {
  const ext = `.${file.name.split('.').pop()?.toLowerCase()}`;
  if (!config.accept.split(',').includes(ext)) return '지원하지 않는 파일 형식이에요.';
  if (file.size > config.maxBytes) return '파일 용량이 너무 커요.';
  return null;
}

function messageFor(error: unknown, table: Record<string, string>, fallback: string) {
  if (!isApiError(error)) return fallback;
  return table[error.error.reason] ?? error.error.message;
}

type DocSlot = {
  file: File | null;
  sourceUrl: string | null;
  error: string | null;
  preview: DocumentPreviewResponse | null;
};

const EMPTY_SLOT: DocSlot = { file: null, sourceUrl: null, error: null, preview: null };

// status: 'failed'는 hard blocker가 아니다 — documentId만 버리고 분석은 그대로 진행한다.
function usablePreview(slot: DocSlot) {
  const { preview } = slot;
  return preview && preview.status !== 'failed' ? preview : null;
}

function slotLabel(slot: DocSlot) {
  return slot.file?.name ?? slot.sourceUrl ?? '';
}

function useDocumentSlot(config: FileFieldConfig) {
  const [slot, setSlot] = useState<DocSlot>(EMPTY_SLOT);

  const upload = useMutation({
    mutationFn: ({ source, postingUrl }: { source: DocumentSource; postingUrl?: string }) =>
      api.previewDocument(config.kind, source, postingUrl),
    onSuccess: (preview) => setSlot((prev) => ({ ...prev, preview, error: null })),
    onError: (error) =>
      setSlot((prev) => ({
        ...prev,
        preview: null,
        error: messageFor(error, UPLOAD_ERROR, '불러오지 못했어요. 잠시 후 다시 시도해주세요.'),
      })),
  });

  function clear() {
    upload.reset();
    setSlot(EMPTY_SLOT);
  }

  function selectFile(file: File | null, postingUrl?: string) {
    upload.reset();
    if (!file) {
      setSlot(EMPTY_SLOT);
      return;
    }
    const error = validateFile(file, config);
    setSlot({ ...EMPTY_SLOT, file: error ? null : file, error });
    if (!error) upload.mutate({ source: { file }, postingUrl });
  }

  function selectUrl(rawUrl: string, postingUrl?: string) {
    const sourceUrl = rawUrl.trim();
    upload.reset();
    if (!isHttpUrl(sourceUrl)) {
      setSlot({ ...EMPTY_SLOT, error: 'http(s)로 시작하는 주소를 입력해주세요.' });
      return;
    }
    setSlot({ ...EMPTY_SLOT, sourceUrl });
    upload.mutate({ source: { sourceUrl }, postingUrl });
  }

  return { slot, uploading: upload.isPending, selectFile, selectUrl, clear };
}

function Dropzone({
  config,
  slot,
  uploading,
  onSelectFile,
  onSelectUrl,
  onClear,
}: {
  config: FileFieldConfig;
  slot: DocSlot;
  uploading: boolean;
  onSelectFile: (file: File | null) => void;
  onSelectUrl: (url: string) => void;
  onClear: () => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const [urlDraft, setUrlDraft] = useState('');

  const filled = Boolean(slot.file || slot.sourceUrl);

  function pickFile(fileList: FileList | null) {
    const picked = fileList?.[0] ?? null;
    if (!picked) return;
    onSelectFile(picked);
  }

  function handleDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setDragOver(false);
    if (uploading) return;
    pickFile(e.dataTransfer.files);
  }

  function applyUrl() {
    onSelectUrl(urlDraft);
    setUrlDraft('');
  }

  return (
    <div className="mb-4">
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
        className={`flex cursor-pointer flex-col items-center justify-center rounded-card border border-dashed px-4 py-5 text-center ${
          dragOver ? 'border-accent bg-accent-soft' : 'border-line'
        }`}
      >
        <input
          type="file"
          accept={config.accept}
          disabled={uploading}
          className="hidden"
          onChange={(e) => pickFile(e.target.files)}
        />
        {filled ? (
          <div className="flex w-full items-center justify-between gap-2 px-2">
            <span className="truncate text-sm text-ink">
              {slot.file ? '📄' : '🔗'} {slotLabel(slot)}
            </span>
            {uploading ? (
              <span className="shrink-0 text-xs text-muted">읽는 중…</span>
            ) : (
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onClear();
                }}
                className="shrink-0 rounded-full bg-error-soft px-3 py-1 text-xs font-medium text-error"
              >
                취소
              </button>
            )}
          </div>
        ) : (
          <>
            <span className="mb-2 text-xl text-accent">+</span>
            <span className="text-sm text-ink">파일을 드래그하거나 클릭해서 업로드</span>
            <span className="mt-1 text-xs text-muted">{config.hint}</span>
          </>
        )}
      </label>

      {config.allowUrl && !filled && (
        <div className="mt-2 flex gap-2">
          <input
            type="text"
            value={urlDraft}
            onChange={(e) => setUrlDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && isHttpUrl(urlDraft)) applyUrl();
            }}
            placeholder="또는 포트폴리오 링크를 붙여넣어주세요"
            className="min-w-0 flex-1 rounded-card border border-line-soft px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          />
          <button
            type="button"
            disabled={!isHttpUrl(urlDraft) || uploading}
            onClick={applyUrl}
            className="shrink-0 rounded-card border border-line-soft px-3 py-2 text-sm text-ink disabled:text-muted"
          >
            확인
          </button>
        </div>
      )}

      {slot.error && <p className="mt-1 text-xs text-error">{slot.error}</p>}
      {slot.preview?.status === 'failed' && (
        <p className="mt-1 text-xs text-muted">
          내용을 읽지 못했어요. 이 문서 없이 분석을 계속 진행할게요.
        </p>
      )}
    </div>
  );
}

export default function JobInput() {
  const navigate = useNavigate();
  const [jobUrl, setJobUrl] = useState('');
  const [urlTouched, setUrlTouched] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const coverLetter = useDocumentSlot(COVER_LETTER);
  const portfolio = useDocumentSlot(PORTFOLIO);

  const urlValid = isHttpUrl(jobUrl);

  const startRun = useMutation({
    mutationFn: api.createAnalysisRun,
    onSuccess: ({ runId }) => navigate(`/interview/analyzing/${runId}`),
    onError: (error) => {
      // 409 run_in_progress는 진행 중인 run의 runId를 body 최상위로 돌려준다(공통 에러 스키마 밖).
      const inFlightRunId = (error as { runId?: unknown }).runId;
      if (
        isApiError(error) &&
        error.error.reason === 'run_in_progress' &&
        typeof inFlightRunId === 'string'
      ) {
        navigate(`/interview/analyzing/${inFlightRunId}`);
        return;
      }
      setSubmitError(
        messageFor(error, RUN_ERROR, '분석을 시작하지 못했어요. 잠시 후 다시 시도해주세요.'),
      );
    },
  });

  const uploading = coverLetter.uploading || portfolio.uploading;
  const busy = uploading || startRun.isPending;

  // JD 키워드 축약에 쓰이는 선택 필드. 공고 URL이 아직 유효하지 않으면 생략한다.
  const postingUrlForPreview = urlValid ? jobUrl.trim() : undefined;

  function handleSubmit() {
    if (!urlValid || busy) return;
    setSubmitError(null);
    // 추출 실패한 문서는 usablePreview 가 걸러내 해당 필드가 빠진다. 둘 다 없어도 진행한다.
    startRun.mutate({
      postingUrl: jobUrl.trim(),
      coverLetterDocumentId: usablePreview(coverLetter.slot)?.documentId,
      portfolioDocumentId: usablePreview(portfolio.slot)?.documentId,
    });
  }

  return (
    <div className="flex min-h-svh flex-col bg-paper">
      <main className="mx-auto flex w-full max-w-lg flex-1 flex-col justify-center px-4 py-6">
        <p className="mb-2 text-sm text-muted">모의면접 · 1 / 3</p>
        <h1 className="mb-4 text-2xl font-bold text-ink">면접 보실 공고를 입력해주세요</h1>

        <div className="rounded-card border border-line-soft bg-surface p-6">
          <label className="mb-2 block text-sm text-ink">
            공고 URL{' '}
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

          <div className="mt-4">
            <Dropzone
              config={COVER_LETTER}
              slot={coverLetter.slot}
              uploading={coverLetter.uploading}
              onSelectFile={(file) => coverLetter.selectFile(file, postingUrlForPreview)}
              onSelectUrl={(url) => coverLetter.selectUrl(url, postingUrlForPreview)}
              onClear={coverLetter.clear}
            />
            <Dropzone
              config={PORTFOLIO}
              slot={portfolio.slot}
              uploading={portfolio.uploading}
              onSelectFile={(file) => portfolio.selectFile(file, postingUrlForPreview)}
              onSelectUrl={(url) => portfolio.selectUrl(url, postingUrlForPreview)}
              onClear={portfolio.clear}
            />
          </div>

          <button
            type="button"
            disabled={!urlValid || busy}
            onClick={handleSubmit}
            className="w-full rounded-card bg-accent py-3 text-sm font-medium text-white disabled:bg-line disabled:text-muted"
          >
            {startRun.isPending ? '분석을 시작하는 중…' : '분석 시작'}
          </button>
          {submitError && <p className="mt-2 text-xs text-error">{submitError}</p>}
        </div>
      </main>

      <footer className="flex items-center justify-between border-t border-line-soft px-8 py-4 text-xs text-muted">
        <span>© 2026 DEVON</span>
        <span>이용약관 · 개인정보처리방침</span>
      </footer>
    </div>
  );
}
