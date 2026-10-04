import { useCallback, useEffect, useRef, useState } from 'react';

export type MicStatus = 'checking' | 'ok' | 'denied' | 'missing' | 'busy' | 'error';
export type MicTestPhase = 'idle' | 'recording' | 'playing';

/** 레벨 미터 막대 수. 가장 최근 값이 오른쪽 끝에 붙는다. */
const BAR_COUNT = 20;
const SAMPLE_MS = 50;
/** 녹음 상한. 한 문장을 말하기에 충분한 길이다. 더 짧게 끝내려면 버튼을 다시 누른다. */
export const MAX_RECORD_MS = 5000;
/** 레벨 미터의 dB 범위. 이보다 작으면 바닥, 크면 꼭대기다. 말소리는 대개 -40~-15dB. */
const FLOOR_DB = -55;
const CEIL_DB = -10;

const SILENT = Array<number>(BAR_COUNT).fill(0);

/** 스피커 선택(setSinkId)은 지원 브라우저에서만 있다. */
type Sinkable = { setSinkId?: (id: string) => Promise<void> };

function statusFromError(error: unknown): MicStatus {
  const name = error instanceof DOMException ? error.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') return 'denied';
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'missing';
  // 장치는 있지만 다른 앱(Zoom 등)이 잡고 있어 열 수 없다.
  if (name === 'NotReadableError') return 'busy';
  return 'error';
}

/** 선택한 스피커로 보낸다. 장치가 사라졌거나 거부되면 기본 스피커로 둔다. */
async function routeTo(target: Sinkable, speakerId: string) {
  if (!speakerId || !target.setSinkId) return;
  try {
    await target.setSinkId(speakerId);
  } catch {
    /* 기본 스피커로 재생한다. */
  }
}

/** RMS를 dB로 바꿔 0~1로 편다. 선형 값은 보통 목소리에서 막대가 거의 안 움직인다. */
function levelOf(samples: Float32Array) {
  const rms = Math.sqrt(samples.reduce((sum, v) => sum + v * v, 0) / samples.length);
  const db = 20 * Math.log10(rms || 1e-8);
  return Math.min(1, Math.max(0, (db - FLOOR_DB) / (CEIL_DB - FLOOR_DB)));
}

type TestSession = {
  stream?: MediaStream;
  ctx?: AudioContext;
  recorder?: MediaRecorder;
  audio?: HTMLAudioElement;
  url?: string;
  timers: ReturnType<typeof setTimeout>[];
};

/** 마이크·분석기·타이머만 닫는다. 녹음 끝에서 재생으로 넘어갈 때도 쓴다. */
function releaseMic(session: TestSession) {
  // clearTimeout은 setInterval id도 지운다(같은 타이머 목록).
  session.timers.forEach(clearTimeout);
  session.timers = [];
  session.stream?.getTracks().forEach((track) => track.stop());
  void session.ctx?.close();
  session.stream = undefined;
  session.ctx = undefined;
}

/**
 * 면접 준비 화면의 마이크·스피커 점검.
 * 진입 시 권한만 확인하고 마이크를 바로 닫는다(장치 이름은 권한이 있어야 보인다).
 * 테스트는 녹음(최대 5초) 후 재생이다. 실시간으로 스피커에 내보내면 하울링이 나고,
 * 브라우저 에코 제거가 그 소리를 깎아 끊겨 들리기 때문이다.
 */
export function useMicCheck() {
  // http(비보안 컨텍스트)에서는 mediaDevices 자체가 없다.
  const [status, setStatus] = useState<MicStatus>(() =>
    'mediaDevices' in navigator ? 'checking' : 'error',
  );
  const [mics, setMics] = useState<MediaDeviceInfo[]>([]);
  const [speakers, setSpeakers] = useState<MediaDeviceInfo[]>([]);
  const [micId, setMicIdState] = useState('');
  const [speakerId, setSpeakerIdState] = useState('');
  const [levels, setLevels] = useState<number[]>(SILENT);
  const [phase, setPhase] = useState<MicTestPhase>('idle');
  const [secondsLeft, setSecondsLeft] = useState(0);
  /** 올리면 권한·장치 확인을 처음부터 다시 한다. 다시 확인 버튼과 권한 변경 알림이 쓴다. */
  const [probeKey, setProbeKey] = useState(0);

  const sessionRef = useRef<TestSession | null>(null);
  const speakerIdRef = useRef('');
  /** 시작·중지마다 올린다. 권한 대기 중 중지·이탈·재클릭이 나면 늦게 열린 마이크를 버린다. */
  const testSeqRef = useRef(0);

  const stopTest = useCallback(() => {
    testSeqRef.current += 1;
    const session = sessionRef.current;
    sessionRef.current = null;
    if (session) {
      // stop()이 부를 onstop의 재생을 막으려고 먼저 끊는다.
      if (session.recorder) session.recorder.onstop = null;
      if (session.recorder?.state === 'recording') session.recorder.stop();
      session.audio?.pause();
      if (session.url) URL.revokeObjectURL(session.url);
      releaseMic(session);
    }
    setLevels(SILENT);
    setPhase('idle');
  }, []);

  useEffect(() => {
    if (!('mediaDevices' in navigator)) return;
    let disposed = false;

    const refresh = async () => {
      const devices = await navigator.mediaDevices.enumerateDevices();
      if (disposed) return;
      const inputs = devices.filter((d) => d.kind === 'audioinput');
      const outputs = devices.filter((d) => d.kind === 'audiooutput');
      setMics(inputs);
      setSpeakers(outputs);
      // 고른 장치가 빠졌으면(이어폰 분리 등) 첫 장치로 돌아간다.
      setMicIdState((id) => (inputs.some((d) => d.deviceId === id) ? id : (inputs[0]?.deviceId ?? '')));
      setSpeakerIdState((id) => {
        const next = outputs.some((d) => d.deviceId === id) ? id : (outputs[0]?.deviceId ?? '');
        speakerIdRef.current = next;
        return next;
      });
    };

    /*
      사이트 설정에서 권한을 바꾸면 새로고침 없이 다시 확인한다.
      'microphone' 조회를 지원하지 않는 브라우저는 조용히 넘어간다 — 다시 확인 버튼이 남는다.
    */
    let permission: PermissionStatus | null = null;
    navigator.permissions
      ?.query({ name: 'microphone' as PermissionName })
      .then((status) => {
        if (disposed) return;
        permission = status;
        status.onchange = () => {
          setStatus('checking');
          setProbeKey((key) => key + 1);
        };
      })
      .catch(() => {});

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then(async (probe) => {
        probe.getTracks().forEach((track) => track.stop());
        if (disposed) return;
        setStatus('ok');
        await refresh();
        // 목록을 읽는 사이 다시 확인이 시작됐으면 정리가 이미 지나갔다. 리스너를 남기지 않는다.
        if (disposed) return;
        navigator.mediaDevices.addEventListener('devicechange', refresh);
      })
      .catch((error: unknown) => {
        if (!disposed) setStatus(statusFromError(error));
      });

    return () => {
      disposed = true;
      navigator.mediaDevices.removeEventListener('devicechange', refresh);
      if (permission) permission.onchange = null;
      stopTest();
    };
  }, [stopTest, probeKey]);

  /** 팝업을 그냥 닫았거나 다른 앱을 끈 뒤 다시 확인한다. 차단 상태면 그대로 거부된다. */
  const recheck = () => {
    setStatus('checking');
    setProbeKey((key) => key + 1);
  };

  /** 녹음을 끝내고 재생한다. 자동 종료와 버튼 종료가 같은 길로 온다. */
  const finishRecording = () => {
    const recorder = sessionRef.current?.recorder;
    if (recorder?.state === 'recording') recorder.stop();
  };

  const startTest = async () => {
    stopTest();
    const seq = testSeqRef.current;
    const session: TestSession = { timers: [] };
    try {
      session.stream = await navigator.mediaDevices.getUserMedia({
        audio: micId ? { deviceId: { exact: micId } } : true,
      });
      if (seq !== testSeqRef.current) {
        releaseMic(session);
        return;
      }
      sessionRef.current = session;

      session.ctx = new AudioContext();
      const analyser = session.ctx.createAnalyser();
      analyser.fftSize = 1024;
      session.ctx.createMediaStreamSource(session.stream).connect(analyser);
      const samples = new Float32Array(analyser.fftSize);

      const chunks: Blob[] = [];
      const recorder = new MediaRecorder(session.stream);
      session.recorder = recorder;
      recorder.ondataavailable = (event) => chunks.push(event.data);
      recorder.onstop = () => {
        releaseMic(session);
        setLevels(SILENT);
        session.url = URL.createObjectURL(new Blob(chunks, { type: recorder.mimeType }));
        const audio = new Audio(session.url);
        session.audio = audio;
        audio.onended = stopTest;
        setPhase('playing');
        void routeTo(audio, speakerIdRef.current)
          .then(() => audio.play())
          .catch(stopTest);
      };
      recorder.start();

      const endsAt = Date.now() + MAX_RECORD_MS;
      // ponytail: 50ms 간격 setState. 준비 화면 전체가 다시 그려지지만 막대 20개라 충분하다.
      session.timers.push(
        setInterval(() => {
          analyser.getFloatTimeDomainData(samples);
          setLevels((prev) => [...prev.slice(1), levelOf(samples)]);
          setSecondsLeft(Math.max(1, Math.ceil((endsAt - Date.now()) / 1000)));
        }, SAMPLE_MS),
        setTimeout(finishRecording, MAX_RECORD_MS),
      );

      setStatus('ok');
      setSecondsLeft(MAX_RECORD_MS / 1000);
      setPhase('recording');
    } catch (error) {
      releaseMic(session);
      if (seq === testSeqRef.current) setStatus(statusFromError(error));
    }
  };

  /** 다른 마이크를 고르면 진행 중인 테스트를 멈춘다. 다시 눌러 새 장치로 시작한다. */
  const setMicId = (id: string) => {
    stopTest();
    setMicIdState(id);
  };

  /** 스피커는 재생 중에도 바로 바꿔 끼운다. */
  const setSpeakerId = (id: string) => {
    speakerIdRef.current = id;
    setSpeakerIdState(id);
    if (sessionRef.current?.audio) void routeTo(sessionRef.current.audio, id);
  };

  return {
    status,
    mics,
    speakers,
    micId,
    speakerId,
    setMicId,
    setSpeakerId,
    canPickSpeaker: 'setSinkId' in HTMLMediaElement.prototype && speakers.length > 0,
    levels,
    phase,
    secondsLeft,
    startTest,
    finishRecording,
    recheck,
    stopTest,
  };
}

/** 스피커 테스트용 1초 비프음. 클릭 핸들러에서 불러야 자동재생 정책에 막히지 않는다. */
export async function playTestTone(speakerId: string) {
  const ctx = new AudioContext();
  await routeTo(ctx as Sinkable, speakerId);
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.frequency.value = 440;
  gain.gain.value = 0.2;
  osc.connect(gain).connect(ctx.destination);
  osc.onended = () => void ctx.close();
  osc.start();
  osc.stop(ctx.currentTime + 1);
}
