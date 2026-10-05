/**
 * 질문 음성(TTS) mock. 8kHz mono 16bit PCM WAV 사인파를 코드로 만든다.
 * 저장소에 오디오 파일을 두지 않으려는 것이다(spec/frontend/designs/2026-10-05-voice-interview.md).
 */
export function toneWav(seconds: number, frequency = 440): ArrayBuffer {
  const sampleRate = 8000;
  const samples = Math.floor(seconds * sampleRate);
  const buffer = new ArrayBuffer(44 + samples * 2);
  const view = new DataView(buffer);
  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };

  ascii(0, 'RIFF');
  view.setUint32(4, 36 + samples * 2, true);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  view.setUint32(16, 16, true); // fmt 청크 크기
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  ascii(36, 'data');
  view.setUint32(40, samples * 2, true);
  for (let i = 0; i < samples; i++) {
    const value = Math.sin((2 * Math.PI * frequency * i) / sampleRate) * 0.2;
    view.setInt16(44 + i * 2, Math.round(value * 0x7fff), true);
  }
  return buffer;
}
