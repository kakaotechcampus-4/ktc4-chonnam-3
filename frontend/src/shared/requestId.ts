/** 복구 요청 하나의 ID를 만들며, 호출자는 결과 확인 동안 같은 값을 재사용한다. */
export function createRequestId(): string {
  const cryptoApi = globalThis.crypto;
  if (typeof cryptoApi.randomUUID === 'function') return cryptoApi.randomUUID();
  // randomUUID가 없는 비보안 컨텍스트도 Web Crypto의 난수 생성은 사용할 수 있다.
  const bytes = cryptoApi.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
