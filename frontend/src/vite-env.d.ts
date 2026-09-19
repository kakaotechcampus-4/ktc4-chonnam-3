/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 개발 서버에서 MSW mock을 끌 때만 'false'. 기본값은 켜짐. */
  readonly VITE_USE_MSW?: 'true' | 'false';
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
