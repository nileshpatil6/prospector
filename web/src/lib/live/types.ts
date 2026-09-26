/** Shape shared by the real `@google/genai` Live session and the Playwright
 * fake (fakeSession.ts) so useLiveCall.ts doesn't care which one it holds. */

/** `onmessage`'s parameter is typed `unknown`, not LiveServerMessage below,
 * so this interface stays structurally assignable to the real
 * `@google/genai` SDK's own (differently-shaped-but-compatible-at-runtime)
 * callbacks type -- callers narrow with `as LiveServerMessage` themselves. */
export interface LiveCallbacks {
  onopen: () => void;
  onmessage: (message: unknown) => void;
  onerror: (event: unknown) => void;
  onclose: (event: unknown) => void;
}

export interface LiveSessionLike {
  sendRealtimeInput: (input: { audio: { data: string; mimeType: string } }) => void;
  sendToolResponse: (input: {
    functionResponses: { id: string; name: string; response: Record<string, unknown> }[];
  }) => void;
  close: () => void;
}

/** The subset of the Live API's server message shape this app reads. */
export interface LiveServerMessage {
  serverContent?: {
    inputTranscription?: { text: string };
    outputTranscription?: { text: string };
    interrupted?: boolean;
    turnComplete?: boolean;
    modelTurn?: {
      parts?: { inlineData?: { data: string; mimeType: string } }[];
    };
  };
  toolCall?: {
    functionCalls?: {
      id: string;
      name: string;
      args: Record<string, unknown>;
    }[];
  };
}
