import { useCallback, useEffect, useRef, useState } from 'react';

/** 답변 최대 길이. 서버도 같은 값을 지킨다(spec/shared/decisions/0007). */
export const MAX_ANSWER_MS = 180_000;
/** 조각 간격. 계약으로 고정하지 않는 FE 기본값이다(0007). */
const CHUNK_MS = 250;
/**
 * 녹음 직후 이 시간 동안은 끝낼 수 없다. 답변 시작을 두 번 누르면 두 번째 클릭이
 * 같은 자리의 답변 끝내기에 떨어져 빈 답변이 제출된다.
 */
const MIN_ANSWER_MS = 1000;
const PREFERRED_MIME = 'audio/webm;codecs=opus';

type Handlers = {
  /** 녹음이 실제로 시작됐다. answerStart를 이때 보낸다. */
  onStart: (mimeType: string) => void;
  onChunk: (chunk: Blob) => void;
  /** 사용자가 끝냈거나 180초가 지났다. 마지막 조각을 넘긴 뒤에 불린다. */
  onStop: () => void;
  /** 녹음 중 마이크 트랙이 끊겼다(분리·권한 해제). */
  onMicLost: () => void;
  /** 마이크를 열지 못했다. getUserMedia의 오류가 그대로 온다. */
  onError: (error: unknown) => void;
};

type Session = {
  stream: MediaStream;
  recorder: MediaRecorder;
  timer: ReturnType<typeof setTimeout>;
  minTimer: ReturnType<typeof setTimeout>;
  stoppable: boolean;
};

function stopTracks(stream: MediaStream) {
  stream.getTracks().forEach((track) => {
    track.onended = null;
    track.stop();
  });
}

/**
 * 답변 녹음. MediaRecorder 조각을 CHUNK_MS마다 넘긴다.
 * 마이크는 녹음 중에만 열고 끝내기·취소·화면 이탈 때 닫는다.
 */
export function useAnswerRecorder(handlers: Handlers) {
  const handlersRef = useRef(handlers);
  useEffect(() => {
    handlersRef.current = handlers;
  });
  const sessionRef = useRef<Session | null>(null);
  /** 시작·취소마다 올린다. 권한 대기 중 연타·취소가 나면 늦게 열린 마이크를 버린다. */
  const seqRef = useRef(0);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [canStop, setCanStop] = useState(false);

  /** 콜백 없이 정리한다. 실패·이탈 때 쓴다. */
  const cancel = useCallback(() => {
    seqRef.current += 1;
    const session = sessionRef.current;
    sessionRef.current = null;
    if (session) {
      clearTimeout(session.timer);
      clearTimeout(session.minTimer);
      session.recorder.ondataavailable = null;
      session.recorder.onstop = null;
      session.recorder.onerror = null;
      if (session.recorder.state !== 'inactive') session.recorder.stop();
      stopTracks(session.stream);
    }
    setStartedAt(null);
    setCanStop(false);
  }, []);

  useEffect(() => cancel, [cancel]);

  /** 정상 종료. 연타해도 한 번만 onStop이 불린다. 180초 자동 종료는 최소 시간과 무관하다. */
  const finish = useCallback(() => {
    const session = sessionRef.current;
    if (!session) return;
    sessionRef.current = null;
    clearTimeout(session.timer);
    clearTimeout(session.minTimer);
    setCanStop(false);
    // 녹음기가 오류 등으로 이미 멈췄으면 stop()이 InvalidStateError를 던지고 onstop도 오지 않는다.
    // 녹음이 온전하지 않으니 마이크 끊김과 같게 실패로 돌린다.
    if (session.recorder.state === 'inactive') {
      stopTracks(session.stream);
      setStartedAt(null);
      handlersRef.current.onMicLost();
      return;
    }
    // 마지막 조각(dataavailable)이 onstop보다 먼저 온다. 그 뒤에 answerEnd를 보내게 한다.
    session.recorder.onstop = () => {
      stopTracks(session.stream);
      setStartedAt(null);
      handlersRef.current.onStop();
    };
    session.recorder.stop();
  }, []);

  /** 사용자가 끝낼 때. 최소 녹음 시간 전에는 무시한다. */
  const stop = useCallback(() => {
    if (sessionRef.current?.stoppable) finish();
  }, [finish]);

  const start = useCallback(
    async (deviceId?: string) => {
      cancel();
      const seq = seqRef.current;
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: deviceId ? { deviceId: { exact: deviceId } } : true,
        });
      } catch (error) {
        if (seq === seqRef.current) handlersRef.current.onError(error);
        return;
      }
      if (seq !== seqRef.current) {
        stopTracks(stream);
        return;
      }

      // opus를 못 쓰는 브라우저(Safari 등)는 기본 형식으로 녹음하고 그 형식을 서버에 알린다.
      // 녹음기를 만들지 못하면(미지원 형식·구형 브라우저) 마이크를 닫고 열기 실패와 같게 알린다.
      let recorder: MediaRecorder;
      try {
        recorder = new MediaRecorder(
          stream,
          MediaRecorder.isTypeSupported(PREFERRED_MIME) ? { mimeType: PREFERRED_MIME } : undefined,
        );
      } catch (error) {
        stopTracks(stream);
        handlersRef.current.onError(error);
        return;
      }
      const session: Session = {
        stream,
        recorder,
        timer: setTimeout(finish, MAX_ANSWER_MS),
        minTimer: setTimeout(() => {
          session.stoppable = true;
          setCanStop(true);
        }, MIN_ANSWER_MS),
        stoppable: false,
      };
      sessionRef.current = session;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) handlersRef.current.onChunk(event.data);
      };
      // 인코딩 오류 등으로 녹음기가 멈추면 녹음 중에 갇히지 않게 실패로 돌린다.
      recorder.onerror = () => {
        if (sessionRef.current !== session) return;
        cancel();
        handlersRef.current.onMicLost();
      };
      stream.getAudioTracks().forEach((track) => {
        track.onended = () => {
          if (sessionRef.current !== session) return;
          cancel();
          handlersRef.current.onMicLost();
        };
      });
      try {
        recorder.start(CHUNK_MS);
      } catch (error) {
        cancel();
        handlersRef.current.onError(error);
        return;
      }
      handlersRef.current.onStart(recorder.mimeType || PREFERRED_MIME);
      // onStart에서 전송에 실패해 취소됐으면 녹음 중으로 표시하지 않는다.
      if (sessionRef.current === session) setStartedAt(Date.now());
    },
    [cancel, finish],
  );

  return { recording: startedAt !== null, startedAt, canStop, start, stop, cancel };
}
