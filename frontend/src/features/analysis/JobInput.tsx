import { useState } from 'react';
import type { DragEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api } from '@/shared/api';
import { isApiError } from '@/types/api';
import type { DocumentPreviewResponse } from '@/types/api';

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

const UPLOAD_ERROR: Record<string, string> = {
  file_too_large: '파일 용량이 너무 커요.',
  unsupported_media_type: '지원하지 않는 형식이에요.',
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
  error: string | null;
  preview: DocumentPreviewResponse | null;
  // 추출 실패를 사용자가 확인하고 "문서 없이 계속 진행"을 고른 상태.
  dismissed: boolean;
};

const EMPTY_SLOT: DocSlot = { file: null, error: null, preview: null, dismissed: false };

// extractStatus: 'failed'는 hard blocker가 아니다 — documentId만 버리고 분석은 진행한다.
function usablePreview(slot: DocSlot) {
  const { preview } = slot;
  return preview && preview.extractStatus !== 'failed' ? preview : null;
}

// 추출 실패를 아직 사용자가 확인하지 않은 상태. 확인 전에는 제출을 막는다.
function needsDecision(slot: DocSlot) {
  return slot.preview?.extractStatus === 'failed' && !slot.dismissed;
}

function useDocumentSlot(config: FileFieldConfig) {
  const [slot, setSlot] = useState<DocSlot>(EMPTY_SLOT);

  const upload = useMutation({
    mutationFn: (file: File) => api.previewDocument(file),
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

  function selectFile(file: File | null) {
    upload.reset();
    if (!file) {
      setSlot(EMPTY_SLOT);
      return;
    }
    const error = validateFile(file, config);
    setSlot({ ...EMPTY_SLOT, file: error ? null : file, error });
    if (!error) upload.mutate(file);
  }

  function dismiss() {
    setSlot((prev) => ({ ...prev, dismissed: true }));
  }

  return { slot, uploading: upload.isPending, selectFile, clear, dismiss };
}

function Dropzone({
  config,
  slot,
  uploading,
  onSelectFile,
  onClear,
  onDismiss,
}: {
  config: FileFieldConfig;
  slot: DocSlot;
  uploading: boolean;
  onSelectFile: (file: File | null) => void;
  onClear: () => void;
  onDismiss: () => void;
}) {
  const [dragOver, setDragOver] = useState(false);

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
        {slot.file ? (
          <div className="flex w-full items-center justify-between gap-2 px-2">
            <span className="truncate text-sm text-ink">📄 {slot.file.name}</span>
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

      {slot.error && <p className="mt-1 text-xs text-error">{slot.error}</p>}

      {needsDecision(slot) && (
        <div className="mt-2 rounded-card bg-error-soft px-3 py-2">
          <p className="text-xs text-error">
            내용을 읽지 못했어요. 텍스트 레이어가 없는 PDF일 수 있어요.
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={onDismiss}
              className="rounded-card bg-surface px-3 py-1 text-xs text-ink"
            >
              문서 없이 계속 진행
            </button>
            <button
              type="button"
              onClick={onClear}
              className="rounded-card bg-surface px-3 py-1 text-xs text-ink"
            >
              다른 파일 올리기
            </button>
          </div>
        </div>
      )}

      {slot.dismissed && (
        <p className="mt-1 text-xs text-muted">이 문서 없이 분석을 진행해요.</p>
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
  // 추출 실패를 확인하지 않은 문서가 있으면 제출을 막는다.
  const pendingDecision = needsDecision(coverLetter.slot) || needsDecision(portfolio.slot);
  const busy = uploading || pendingDecision || startRun.isPending;

  // JD 키워드 축약에 쓰이는 선택 필드. 공고 URL이 아직 유효하지 않으면 생략한다.

  function handleSubmit() {
    if (!urlValid || busy) return;
    setSubmitError(null);
    // Sprint 1 은 포트폴리오만 분석에 반영한다(BE 협의). 추출 실패면 usablePreview 가 걸러
    // documentId 가 빠지고, 서버는 문서 없이 분석한다.
    startRun.mutate({
      postingUrl: jobUrl.trim(),
      documentId: usablePreview(portfolio.slot)?.documentId,
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
              onSelectFile={(file) => coverLetter.selectFile(file)}
              onClear={coverLetter.clear}
              onDismiss={coverLetter.dismiss}
            />
            <Dropzone
              config={PORTFOLIO}
              slot={portfolio.slot}
              uploading={portfolio.uploading}
              onSelectFile={(file) => portfolio.selectFile(file)}
              onClear={portfolio.clear}
              onDismiss={portfolio.dismiss}
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
