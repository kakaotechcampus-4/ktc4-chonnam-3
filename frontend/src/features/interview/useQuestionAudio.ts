import { useCallback, useEffect, useRef, useState } from 'react';

export type QuestionAudioState = 'loading' | 'playing' | 'ended' | 'failed';

/**
 * 질문 음성(TTS) 재생. `<audio>`가 다운로드·버퍼링을 맡는다(spec/shared/decisions/0007).
 * playKey가 바뀌면 처음부터 다시 재생한다 — 같은 턴 question이 다시 오면(다시 듣기) 화면이 올린다.
 * 주소가 없거나 재생에 실패하면 failed다. 화면은 그때 질문 텍스트를 보여 준다.
 * 자동재생 정책에 막혀도(새로고침·직접 진입) failed다. 다시 듣기는 음성 요청으로만 한다(0007 결정 5).
 */
export function useQuestionAudio(audioUrl: string | null, playKey: number) {
  const key = `${playKey}:${audioUrl}`;
  const [status, setStatus] = useState<{ key: string; state: QuestionAudioState } | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (!audioUrl) return;
    const audio = new Audio(audioUrl);
    audioRef.current = audio;
    audio.onplaying = () => setStatus({ key, state: 'playing' });
    // 실패한 재생을 답변 시작의 pause()가 ended로 덮지 않게 한다. 덮으면 텍스트가 사라진다.
    const end = () =>
      setStatus((prev) =>
        prev?.key === key && prev.state === 'failed' ? prev : { key, state: 'ended' },
      );
    audio.onpause = end;
    audio.onended = end;
    audio.onerror = () => setStatus({ key, state: 'failed' });
    let active = true;
    audio.play().catch((error: unknown) => {
      // 정리된 audio의 거절(턴 전환·다시 듣기)이나 pause()로 끊긴 재생(AbortError)은
      // 실패가 아니다. 무시하지 않으면 지금 재생 중인 질문까지 failed로 덮어 텍스트가 강제로 뜬다.
      const name = error instanceof DOMException ? error.name : '';
      if (!active || name === 'AbortError') return;
      setStatus({ key, state: 'failed' });
    });

    return () => {
      active = false;
      audio.onplaying = null;
      audio.onpause = null;
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      if (audioRef.current === audio) audioRef.current = null;
    };
  }, [audioUrl, key]);

  const stop = useCallback(() => audioRef.current?.pause(), []);

  const state: QuestionAudioState = !audioUrl
    ? 'failed'
    : status?.key === key
      ? status.state
      : 'loading';
  return { state, stop };
}
