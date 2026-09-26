/** Playwright test double for a live Gemini session. Only ever constructed
 * when `window.__PROSPECTOR_LIVE_FAKE__` is set -- which only Playwright's
 * addInitScript does -- so this code path never runs for a real caller. It
 * drives the exact same callbacks a real `ai.live.connect(...)` session
 * would, so useLiveCall doesn't need to know which one it's talking to. */
import type { LiveCallbacks, LiveSessionLike } from "./types";

export function createFakeLiveSession(callbacks: LiveCallbacks): LiveSessionLike {
  let closed = false;
  const timers: ReturnType<typeof setTimeout>[] = [];
  const schedule = (fn: () => void, ms: number) => {
    timers.push(
      setTimeout(() => {
        if (!closed) fn();
      }, ms)
    );
  };

  schedule(() => callbacks.onopen(), 50);
  schedule(
    () =>
      callbacks.onmessage({
        serverContent: { inputTranscription: { text: "Hi, is this Sunrise Dental Care?" }, turnComplete: true },
      }),
    300
  );
  schedule(
    () =>
      callbacks.onmessage({
        serverContent: {
          outputTranscription: {
            text: "Hello! This is a demo AI receptionist for Sunrise Dental Care. How can I help?",
          },
          turnComplete: true,
        },
      }),
    750
  );
  schedule(
    () =>
      callbacks.onmessage({
        toolCall: {
          functionCalls: [
            {
              id: "fake-call-1",
              name: "take_message",
              args: {
                caller_name: "Asha Kulkarni",
                callback_number: "+91 98220 00000",
                reason: "Wants to book a check-up next week.",
              },
            },
          ],
        },
      }),
    1200
  );

  return {
    sendRealtimeInput: () => {},
    sendToolResponse: () => {},
    close: () => {
      closed = true;
      timers.forEach(clearTimeout);
      callbacks.onclose({ reason: "fake session closed" });
    },
  };
}
