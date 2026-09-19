import { HttpResponse, delay, http, type PathParams } from 'msw';

import type { DocumentPreviewResponse, DocumentStatus } from '@/types/api';
import { saveDocument } from '../db';
import { errorResponse, path, type Res } from '../http';

/** spec/backend/features/documents.md — 지원 형식과 크기 제한. */
const SUPPORTED = ['.pdf', '.docx', '.txt', '.md'];
const MAX_BYTES = 10 * 1024 * 1024;

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
       * 파일명에 따라 추출 상태를 바꿀 수 있게 해 둔다.
       * partial / failed 도 hard blocker가 아니므로 FE는 계속 진행 여부를 물어야 한다.
       */
      let extractStatus: DocumentStatus = 'succeeded';
      if (lowered.includes('partial')) extractStatus = 'partial';
      if (lowered.includes('fail')) extractStatus = 'failed';

      /**
       * 계약의 DocumentPreviewResponse는 documentId·extractStatus 두 필드뿐이다.
       * fileName·sizeBytes·extractedGithubUrls는 계약에 없어 내려주지 않는다.
       */
      const preview: DocumentPreviewResponse = {
        documentId: crypto.randomUUID(),
        extractStatus,
      };

      saveDocument(preview);
      return HttpResponse.json<DocumentPreviewResponse>(preview);
    },
  ),
];
