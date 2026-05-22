import { config } from '../app/config.js';
import { log, error } from '../utils/logger.js';

/**
 * LLMClient — streaming chat-completions client for the nodeava-orch.
 *
 * Plan #5 rewrite: parses Plan #4's dual-flavor SSE stream. The default
 * `data:`-only frames carry OpenAI chunks (token content). Named-event
 * frames (`event: tool_call_start` etc.) carry typed payloads consumed
 * by the agentic-loop UI (state machine, future Tier A panels).
 *
 * Frame format (RFC 8895-ish):
 *
 *   <event-line>\n
 *   <data-line(s)>\n
 *   \n          <- blank-line frame separator
 *
 * Where:
 *   <event-line>  ::= "event: <name>"   (optional; absence means default stream)
 *   <data-line>   ::= "data: <text>"    (one or more; concatenate values with "\n")
 */
export class LLMClient {
  constructor() {
    this.abortController = null;
  }

  /**
   * Send a streaming chat completion request.
   *
   * @param {Array} messages - OpenAI-format messages [{role, content}]
   * @param {Object} handlers
   * @param {function(string)} handlers.onToken - per content token (existing behavior)
   * @param {function(string)} handlers.onDone - called once with the full assembled text
   * @param {function(Error)} handlers.onError - network or terminal SSE error
   * @param {function({id, name, arguments})} [handlers.onToolCallStart]
   * @param {function({id, result_preview, duration_ms, error})} [handlers.onToolCallEnd]
   * @param {function({stage, duration_ms, round_num})} [handlers.onStageTiming]
   * @param {function(string)} [handlers.onThinkingToken] - per thinking delta
   * @param {Object} [opts]
   * @param {boolean} [opts.webSearch] - inject browser.* tools in agentic loop
   * @param {boolean} [opts.wiki] - inject wiki.* tools in agentic loop
   */
  async chatCompletion(messages, handlers, opts = {}) {
    this.abort();
    this.abortController = new AbortController();

    const {
      onToken,
      onDone,
      onError,
      onToolCallStart,
      onToolCallEnd,
      onStageTiming,
      onThinkingToken,
    } = handlers || {};

    const body = {
      model: config.llmModel,
      messages,
      max_tokens: config.llmMaxTokens,
      stream: true,
    };
    if (opts.webSearch) body.web_search = true;
    if (opts.wiki) body.wiki = true;

    try {
      const response = await fetch(config.llmEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: this.abortController.signal,
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const err = new Error(`LLM HTTP ${response.status}: ${response.statusText}`);
        err.status = response.status;
        throw err;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullText = '';
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Drain complete frames (separated by blank line "\n\n")
        let sepIdx;
        while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, sepIdx);
          buffer = buffer.slice(sepIdx + 2);
          const delta = this._handleFrame(frame, {
            onToken,
            onToolCallStart,
            onToolCallEnd,
            onStageTiming,
            onThinkingToken,
            onError,
          });
          if (delta) fullText += delta;
        }
      }

      // Drain any final partial buffer (unlikely but defensive)
      if (buffer.trim()) {
        const delta = this._handleFrame(buffer, {
          onToken,
          onToolCallStart,
          onToolCallEnd,
          onStageTiming,
          onThinkingToken,
          onError,
        });
        if (delta) fullText += delta;
      }

      log(`LLM response: ${fullText.length} chars`);
      if (onDone) onDone(fullText);
    } catch (err) {
      if (err.name === 'AbortError') {
        log('LLM request aborted');
        return;
      }
      const classified = this._classifyError(err);
      error('LLM error:', classified.message);
      if (onError) onError(classified);
    } finally {
      this.abortController = null;
    }
  }

  /**
   * Parse a single SSE frame and dispatch to the right handler.
   * Returns the content delta if this was a default-stream token frame
   * (so chatCompletion can accumulate fullText). Otherwise returns null.
   */
  _handleFrame(frame, handlers) {
    let eventType = null;
    const dataLines = [];
    for (const line of frame.split('\n')) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        dataLines.push(line.slice(6));
      }
    }
    if (dataLines.length === 0) return null;
    const dataStr = dataLines.join('\n');
    if (dataStr === '[DONE]') return null;

    // Default stream (no event:) → OpenAI chunk shape
    if (eventType === null) {
      try {
        const parsed = JSON.parse(dataStr);
        const delta = parsed.choices?.[0]?.delta?.content;
        if (delta && handlers.onToken) handlers.onToken(delta);
        return delta || null;
      } catch {
        // Malformed JSON on the default stream — skip
        return null;
      }
    }

    // Named event → typed payload, dispatch by event type
    let payload;
    try {
      payload = JSON.parse(dataStr);
    } catch {
      // Malformed payload — skip
      return null;
    }

    switch (eventType) {
      case 'thinking_token':
        if (handlers.onThinkingToken) handlers.onThinkingToken(payload.delta || '');
        break;
      case 'tool_call_start':
        if (handlers.onToolCallStart) {
          handlers.onToolCallStart({
            id: payload.id,
            name: payload.name,
            arguments: payload.arguments || {},
          });
        }
        break;
      case 'tool_call_end':
        if (handlers.onToolCallEnd) {
          handlers.onToolCallEnd({
            id: payload.id,
            result_preview: payload.result_preview || '',
            duration_ms: payload.duration_ms || 0,
            error: payload.error || null,
          });
        }
        break;
      case 'stage_timing':
        if (handlers.onStageTiming) {
          handlers.onStageTiming({
            stage: payload.stage,
            duration_ms: payload.duration_ms || 0,
            round_num: payload.round_num || null,
          });
        }
        break;
      case 'error':
        // SSE-channel error (not a network error). Surface it via onError.
        if (handlers.onError) {
          handlers.onError(new Error(payload.message || 'orchestrator error'));
        }
        break;
      default:
        // Unknown event type — log but don't fail
        log(`LLMClient: ignoring unknown SSE event '${eventType}'`);
    }
    return null;
  }

  _classifyError(err) {
    if (err.status === 503) {
      return new Error('LLM service is busy — try again shortly');
    }
    if (err.status === 404) {
      return new Error('LLM model not found — check model configuration');
    }
    if (err.status >= 500) {
      return new Error(`LLM server error (${err.status}) — check service logs`);
    }
    if (err.status >= 400) {
      return new Error(`LLM request error (${err.status}) — ${err.message}`);
    }
    if (err.message?.includes('Failed to fetch') || err.message?.includes('NetworkError')) {
      return new Error('Cannot reach LLM service — check if container is running');
    }
    return err;
  }

  abort() {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
  }
}
