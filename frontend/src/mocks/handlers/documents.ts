import { HttpResponse, delay, http, type PathParams } from 'msw';

import type { DocumentPreviewResponse } from '@/types/contract';
import { saveDocument } from '../db';
import { errorResponse, path, type Res } from '../http';

/** spec/backend/features/documents.md — 지원 형식과 크기 제한. */
const SUPPORTED = ['.pdf', '.docx', '.txt', '.md'];
const MAX_BYTES = 10 * 1024 * 1024;

/** 추출된 GitHub URL은 owner/repo 까지 정규화된 형태로 내려온다. */
const EXTRACTED_URLS = [
  'https://github.com/kimdev/payment-service',
  'https://github.com/kimdev/project-a',
  'https://github.com/kimdev/devon-frontend',
];

export const documentHandlers = [
  http.post<PathParams, never, Res<DocumentPreviewResponse>>(
    path('/documents/preview'),
    async ({ request }) => {
      const form = await request.formData();
      const file = form.get('file');

      if (!(file instanceof File)) {
        return errorResponse(400, 'internal_error', 'file 필드가 필요합니다.');
      }

      const lowered = file.name.toLowerCase();
      if (!SUPPORTED.some((ext) => lowered.endsWith(ext))) {
        return errorResponse(
          415,
          'unsupported_document_type',
          'PDF, DOCX, TXT, MD 파일만 올릴 수 있어요.',
        );
      }
      if (file.size > MAX_BYTES) {
        return errorResponse(413, 'document_too_large', '파일은 10MB까지 올릴 수 있어요.');
      }

      // 텍스트 추출을 흉내 내기 위해 크기에 비례한 지연을 준다.
      await delay(800);

      /**
       * 파일명에 따라 preview 상태를 바꿀 수 있게 해 둔다.
       * partial / failed 도 hard blocker가 아니므로 FE는 계속 진행 여부를 물어야 한다.
       */
      let status: DocumentPreviewResponse['status'] = 'succeeded';
      if (lowered.includes('partial')) status = 'partial';
      if (lowered.includes('fail')) status = 'failed';

      const preview: DocumentPreviewResponse = {
        documentId: crypto.randomUUID(),
        status,
        fileName: file.name,
        sizeBytes: file.size,
        extractedGithubUrls: status === 'failed' ? [] : EXTRACTED_URLS,
        truncated: status === 'partial',
        failureReason: status === 'failed' ? 'document_extract_failed' : null,
      };

      saveDocument(preview);
      return HttpResponse.json<DocumentPreviewResponse>(preview);
    },
  ),
];
