/** Inline AudioWorklet module (loaded from a blob: URL, no separate asset
 * file needed) that downsamples the mic's native sample rate down to 16kHz
 * mono PCM16 and posts each chunk back to the main thread. A plain
 * decimation, not a filtered resample -- good enough for speech at demo
 * quality, and keeps this dependency-free. */
const MIC_WORKLET_SOURCE = `
class MicCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const { inputSampleRate, targetSampleRate } = options.processorOptions;
    this._ratio = inputSampleRate / targetSampleRate;
    this._acc = 0;
  }

  process(inputs) {
    const input = inputs[0][0];
    if (!input) return true;

    const kept = [];
    for (let i = 0; i < input.length; i++) {
      this._acc += 1;
      if (this._acc >= this._ratio) {
        this._acc -= this._ratio;
        kept.push(input[i]);
      }
    }

    if (kept.length > 0) {
      const int16 = new Int16Array(kept.length);
      for (let i = 0; i < kept.length; i++) {
        const s = Math.max(-1, Math.min(1, kept[i]));
        int16[i] = s < 0 ? s * 32768 : s * 32767;
      }
      this.port.postMessage(int16.buffer, [int16.buffer]);
    }
    return true;
  }
}
registerProcessor("mic-capture-processor", MicCaptureProcessor);
`;

export function micWorkletBlobUrl(): string {
  const blob = new Blob([MIC_WORKLET_SOURCE], { type: "application/javascript" });
  return URL.createObjectURL(blob);
}

export const MIC_WORKLET_NAME = "mic-capture-processor";
