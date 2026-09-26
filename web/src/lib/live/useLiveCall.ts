"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createLiveSession, errorMessage, postMessage } from "@/lib/api";
import type { Lead } from "@/lib/types";
import { arrayBufferToBase64, base64ToArrayBuffer, int16ToFloat32, rms } from "./pcm";
import { micWorkletBlobUrl, MIC_WORKLET_NAME } from "./micWorklet";
import { createFakeLiveSession } from "./fakeSession";
import type { LiveCallbacks, LiveServerMessage, LiveSessionLike } from "./types";

export type CallStatus = "idle" | "connecting" | "active" | "ended" | "error";
export type CallErrorKind = "mic_denied" | "token_error" | "socket_error" | null;

export interface TranscriptLine {
  id: number;
  speaker: "caller" | "receptionist";
  text: string;
}

export interface TakenMessage {
  caller_name: string;
  callback_number: string;
  reason: string;
}

export interface UseLiveCallResult {
  status: CallStatus;
  errorKind: CallErrorKind;
  errorText: string;
  elapsedMs: number;
  transcript: TranscriptLine[];
  takenMessages: TakenMessage[];
  muted: boolean;
  micLevel: number;
  outputLevel: number;
  start: () => void;
  toggleMute: () => void;
  hangUp: () => void;
}

function isFakeMode(): boolean {
  return (
    typeof window !== "undefined" &&
    Boolean((window as unknown as { __PROSPECTOR_LIVE_FAKE__?: boolean }).__PROSPECTOR_LIVE_FAKE__)
  );
}

let nextLineId = 1;

/** Owns the whole call lifecycle: minting a token, mic capture, playback
 * scheduling, transcript merging, and the take_message tool round-trip.
 * One instance per open CallPanel; every mutable handle (contexts, tracks,
 * scheduled sources, the session itself) lives in refs so hangUp/unmount
 * can always find and tear them down, even mid-connect. */
export function useLiveCall(runId: string, lead: Lead): UseLiveCallResult {
  const [status, setStatus] = useState<CallStatus>("idle");
  const [errorKind, setErrorKind] = useState<CallErrorKind>(null);
  const [errorText, setErrorText] = useState("");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [takenMessages, setTakenMessages] = useState<TakenMessage[]>([]);
  const [muted, setMuted] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [outputLevel, setOutputLevel] = useState(0);

  const sessionRef = useRef<LiveSessionLike | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const micContextRef = useRef<AudioContext | null>(null);
  const playbackContextRef = useRef<AudioContext | null>(null);
  const micAnalyserRef = useRef<AnalyserNode | null>(null);
  const outputAnalyserRef = useRef<AnalyserNode | null>(null);
  const nextPlayTimeRef = useRef(0);
  const scheduledSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const callerLineIdRef = useRef<number | null>(null);
  const receptionistLineIdRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);
  const timerIdRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const rafIdRef = useRef<number | null>(null);
  const torndownRef = useRef(false);

  const stopScheduledPlayback = useCallback(() => {
    for (const source of scheduledSourcesRef.current) {
      try {
        source.stop();
      } catch {
        // already finished playing; nothing to stop
      }
    }
    scheduledSourcesRef.current = [];
    if (playbackContextRef.current) nextPlayTimeRef.current = playbackContextRef.current.currentTime;
  }, []);

  const teardown = useCallback(() => {
    if (torndownRef.current) return;
    torndownRef.current = true;

    if (timerIdRef.current) clearInterval(timerIdRef.current);
    if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);

    stopScheduledPlayback();

    micStreamRef.current?.getTracks().forEach((track) => track.stop());
    micStreamRef.current = null;

    micContextRef.current?.close().catch(() => {});
    micContextRef.current = null;
    playbackContextRef.current?.close().catch(() => {});
    playbackContextRef.current = null;

    sessionRef.current = null;
  }, [stopScheduledPlayback]);

  useEffect(() => teardown, [teardown]);

  const appendTranscript = useCallback((speaker: "caller" | "receptionist", text: string) => {
    setTranscript((lines) => {
      const activeRef = speaker === "caller" ? callerLineIdRef : receptionistLineIdRef;
      const otherRef = speaker === "caller" ? receptionistLineIdRef : callerLineIdRef;
      otherRef.current = null; // a new turn on this side ends the other side's line

      if (activeRef.current !== null) {
        const idx = lines.findIndex((l) => l.id === activeRef.current);
        if (idx !== -1) {
          const merged = [...lines];
          merged[idx] = { ...merged[idx], text: merged[idx].text + text };
          return merged;
        }
      }
      const id = nextLineId++;
      activeRef.current = id;
      return [...lines, { id, speaker, text }];
    });
  }, []);

  const schedulePlayback = useCallback((base64Pcm: string) => {
    const ctx = playbackContextRef.current;
    const analyser = outputAnalyserRef.current;
    if (!ctx || !analyser) return;

    const int16 = new Int16Array(base64ToArrayBuffer(base64Pcm));
    const float32 = int16ToFloat32(int16);
    const buffer = ctx.createBuffer(1, float32.length, 24000);
    buffer.getChannelData(0).set(float32);

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(analyser);
    analyser.connect(ctx.destination);

    const startAt = Math.max(nextPlayTimeRef.current, ctx.currentTime);
    source.start(startAt);
    nextPlayTimeRef.current = startAt + buffer.duration;
    scheduledSourcesRef.current.push(source);
    source.onended = () => {
      scheduledSourcesRef.current = scheduledSourcesRef.current.filter((s) => s !== source);
    };
  }, []);

  const handleToolCall = useCallback(
    async (message: LiveServerMessage) => {
      const calls = message.toolCall?.functionCalls ?? [];
      for (const call of calls) {
        if (call.name !== "take_message") continue;
        const args = call.args as Partial<TakenMessage>;
        const record: TakenMessage = {
          caller_name: String(args.caller_name ?? ""),
          callback_number: String(args.callback_number ?? ""),
          reason: String(args.reason ?? ""),
        };
        try {
          await postMessage(runId, lead.id, record);
          setTakenMessages((cur) => [...cur, record]);
        } catch {
          // Best-effort: the caller-facing call keeps going even if the
          // message couldn't be persisted server-side.
        }
        sessionRef.current?.sendToolResponse({
          functionResponses: [{ id: call.id, name: call.name, response: { ok: true } }],
        });
      }
    },
    [runId, lead.id]
  );

  const handleMessage = useCallback(
    (message: LiveServerMessage) => {
      const content = message.serverContent;
      if (content?.interrupted) stopScheduledPlayback();
      if (content?.inputTranscription?.text) appendTranscript("caller", content.inputTranscription.text);
      if (content?.outputTranscription?.text) appendTranscript("receptionist", content.outputTranscription.text);
      for (const part of content?.modelTurn?.parts ?? []) {
        if (part.inlineData?.mimeType?.startsWith("audio/pcm")) schedulePlayback(part.inlineData.data);
      }
      if (message.toolCall) void handleToolCall(message);
    },
    [appendTranscript, schedulePlayback, stopScheduledPlayback, handleToolCall]
  );

  const startLevelMeter = useCallback(() => {
    const tick = () => {
      const micAnalyser = micAnalyserRef.current;
      const outputAnalyser = outputAnalyserRef.current;
      if (micAnalyser) {
        const buf = new Float32Array(micAnalyser.fftSize);
        micAnalyser.getFloatTimeDomainData(buf);
        setMicLevel(rms(buf));
      }
      if (outputAnalyser) {
        const buf = new Float32Array(outputAnalyser.fftSize);
        outputAnalyser.getFloatTimeDomainData(buf);
        setOutputLevel(rms(buf));
      }
      rafIdRef.current = requestAnimationFrame(tick);
    };
    rafIdRef.current = requestAnimationFrame(tick);
  }, []);

  const start = useCallback(() => {
    if (status === "connecting" || status === "active") return;
    torndownRef.current = false;
    setStatus("connecting");
    setErrorKind(null);
    setErrorText("");
    setTranscript([]);
    setTakenMessages([]);
    callerLineIdRef.current = null;
    receptionistLineIdRef.current = null;

    (async () => {
      const fake = isFakeMode();

      let token = "";
      let model = "";
      let config: Record<string, unknown> = {};
      if (!fake) {
        try {
          const session = await createLiveSession(runId, lead.id);
          token = session.token;
          model = session.model;
          config = session.config;
        } catch (err) {
          setStatus("error");
          setErrorKind("token_error");
          setErrorText(errorMessage(err));
          return;
        }
      }

      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
        });
      } catch {
        setStatus("error");
        setErrorKind("mic_denied");
        setErrorText("Microphone access was denied. Allow mic access and try again.");
        return;
      }
      if (torndownRef.current) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      micStreamRef.current = stream;

      const micContext = new AudioContext();
      micContextRef.current = micContext;
      const micSource = micContext.createMediaStreamSource(stream);
      const micAnalyser = micContext.createAnalyser();
      micAnalyser.fftSize = 512;
      micSource.connect(micAnalyser);
      micAnalyserRef.current = micAnalyser;

      await micContext.audioWorklet.addModule(micWorkletBlobUrl());
      const workletNode = new AudioWorkletNode(micContext, MIC_WORKLET_NAME, {
        processorOptions: { inputSampleRate: micContext.sampleRate, targetSampleRate: 16000 },
      });
      micSource.connect(workletNode);
      workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        const data = arrayBufferToBase64(event.data);
        sessionRef.current?.sendRealtimeInput({ audio: { data, mimeType: "audio/pcm;rate=16000" } });
      };

      const playbackContext = new AudioContext({ sampleRate: 24000 });
      playbackContextRef.current = playbackContext;
      nextPlayTimeRef.current = playbackContext.currentTime;
      const outputAnalyser = playbackContext.createAnalyser();
      outputAnalyser.fftSize = 512;
      outputAnalyserRef.current = outputAnalyser;

      startLevelMeter();

      const callbacks: LiveCallbacks = {
        onopen: () => {
          setStatus("active");
          startedAtRef.current = Date.now();
          timerIdRef.current = setInterval(() => setElapsedMs(Date.now() - startedAtRef.current), 250);
        },
        onmessage: (raw) => handleMessage(raw as LiveServerMessage),
        onerror: (err) => {
          setStatus("error");
          setErrorKind("socket_error");
          setErrorText(errorMessage(err));
        },
        onclose: () => {
          setStatus((cur) => (cur === "error" ? cur : "ended"));
        },
      };

      try {
        if (fake) {
          sessionRef.current = createFakeLiveSession(callbacks);
        } else {
          const { GoogleGenAI } = await import("@google/genai");
          const ai = new GoogleGenAI({ apiKey: token, httpOptions: { apiVersion: "v1alpha" } });
          sessionRef.current = (await ai.live.connect({
            model,
            config,
            callbacks,
          })) as unknown as LiveSessionLike;
        }
      } catch (err) {
        setStatus("error");
        setErrorKind("socket_error");
        setErrorText(errorMessage(err));
      }
    })();
  }, [status, runId, lead.id, handleMessage, startLevelMeter]);

  const toggleMute = useCallback(() => {
    const stream = micStreamRef.current;
    if (!stream) return;
    const nextMuted = !muted;
    stream.getAudioTracks().forEach((track) => (track.enabled = !nextMuted));
    setMuted(nextMuted);
  }, [muted]);

  const hangUp = useCallback(() => {
    sessionRef.current?.close();
    teardown();
    setStatus("ended");
  }, [teardown]);

  return {
    status,
    errorKind,
    errorText,
    elapsedMs,
    transcript,
    takenMessages,
    muted,
    micLevel,
    outputLevel,
    start,
    toggleMute,
    hangUp,
  };
}
