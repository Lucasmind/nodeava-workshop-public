import { AvatarManager } from '../avatar/AvatarManager.js';
import { TTSManager } from '../tts/TTSManager.js';
import { STTManager } from '../stt/STTManager.js';
import { LLMClient } from '../llm/LLMClient.js';
import { ConversationManager } from '../llm/ConversationManager.js';
import { EmotionController } from '../avatar/EmotionController.js';
import { StateMachine, States } from '../app/state.js';
import { config } from '../app/config.js';
import { log, error, warn } from '../utils/logger.js';
import { pickPhrase } from '../utils/pickPhrase.js';

// Sentence boundary: period/exclamation/question after a word character (avoids "1. ")
const SENTENCE_END_RE = /(?<=[a-zA-Z,\])"'])[.!?]\s+/;
const MAX_RETRIES = 2;
const RETRY_DELAY_MS = 1000;
const SPEAKING_TIMEOUT_MS = 30000;

// Qwen3 thinking tags: <think>...</think> followed by the actual response
const THINK_OPEN = '<think>';
const THINK_CLOSE = '</think>';
// Regex to strip <think>...</think> blocks from full text (for history cleanup)
const THINK_BLOCK_RE = /<think>[\s\S]*?<\/think>\s*/g;
// Strip emojis so TTS doesn't read them aloud as descriptions
const EMOJI_RE = /[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F1E0}-\u{1F1FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{FE00}-\u{FE0F}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}\u{200D}\u{20E3}\u{E0020}-\u{E007F}]+/gu;

// Clean text for TTS: strip markdown and emojis so they aren't read aloud
function cleanForTTS(text) {
  return text
    .replace(EMOJI_RE, '')             // emojis
    .replace(/\*\*(.+?)\*\*/g, '$1')  // **bold** → bold
    .replace(/\*(.+?)\*/g, '$1')      // *italic* → italic
    .replace(/^#{1,6}\s+/gm, '')      // ### headings
    .replace(/^---+$/gm, '')          // --- horizontal rules
    .replace(/^[-*+]\s+/gm, '')       // - bullet points
    .replace(/^\d+\.\s+/gm, '')       // 1. numbered lists
    .replace(/`([^`]+)`/g, '$1')      // `code` → code
    .replace(/\s{2,}/g, ' ')          // collapse whitespace
    .trim();
}

export class Orchestrator {
  constructor({ dashboardState = null } = {}) {
    this._dashboardState = dashboardState;
    this.avatar = new AvatarManager({ dashboardState });
    this.tts = new TTSManager({ dashboardState });
    this.stt = new STTManager({ dashboardState });
    this.llm = new LLMClient();
    this.conversation = new ConversationManager();
    this.emotion = null;
    this.state = new StateMachine();

    // Callbacks for UI updates
    this.onStateChange = null;
    this.onUserSpeech = null;
    this.onAssistantToken = null;
    this.onAssistantSentence = null;
    this.onAssistantDone = null;
    this.onError = null;

    // Streaming state
    this._rawBuffer = '';        // accumulates all tokens for thinking detection
    this._tokenBuffer = '';      // holds filtered text for sentence splitting
    this._isThinking = false;    // true while inside <think>...</think>
    this._thinkingDone = false;  // true once thinking phase resolved (detected or skipped)
    this._emotionParsed = false;
    this._currentEmotion = null;
    this._pendingSentences = 0;
    this._llmDone = false;
    this._speakingTimer = null;

    // Plan #5: agentic-tool state
    this._webSearchEnabled = false;
    this._wikiEnabled = false;
    this._fillerTimer = null;
    this._fillerPlayedThisTurn = false;
    this._activeToolName = null;

    // Plan #8: dashboard event tracking
    this._tokensEmittedThisRound = false;
    this._currentRound = 1;
    this._speakPhaseStart = null; // wall-clock start for avatar_speak stage_timing

    // Plan #5: optional UI callbacks (UIManager wires these)
    this.onToolCallStart = null;  // ({id, name, arguments})
    this.onToolCallEnd = null;    // ({id, result_preview, duration_ms, error})
    this.onThinkingToken = null;  // (delta:string)
    this.onStageTiming = null;    // ({stage, duration_ms, round_num})
  }

  async init(containerEl, onProgress = null) {
    this.state.onChange = (newState, oldState) => {
      if (this.onStateChange) this.onStateChange(newState, oldState);
    };

    // 1. Avatar
    if (onProgress) onProgress('Initializing avatar...', 5);
    await this.avatar.init(containerEl);

    if (onProgress) onProgress('Loading avatar model...', 15);
    await this.avatar.loadAvatar(config.avatarUrl, (ev) => {
      if (ev.lengthComputable && onProgress) {
        const pct = 15 + Math.round((ev.loaded / ev.total) * 30);
        onProgress('Loading avatar model...', pct);
      }
    });

    this.emotion = new EmotionController(this.avatar);

    // 2. TTS
    if (onProgress) onProgress('Loading TTS engine...', 50);
    await this.tts.init((progress) => {
      if (progress?.progress != null && onProgress) {
        const pct = 50 + Math.round(progress.progress * 30);
        onProgress('Loading TTS model...', pct);
      }
    });

    // Wire TTS audio output → avatar lip sync
    this.tts.onAudioReady = (audioData) => {
      if (audioData) {
        // Start avatar_speak timing on first successful audio chunk
        if (this._speakPhaseStart == null) {
          this._speakPhaseStart = performance.now();
        }
        this.avatar.speakAudio(audioData, {}, (word) => {
          if (this.onAssistantToken) this.onAssistantToken(word);
        });
      } else {
        warn('TTS failed for a sentence, skipping');
        if (this.onError) this.onError('Speech synthesis failed for a sentence');
      }

      // Track when sentences finish (null = TTS failed, still count it)
      this._pendingSentences--;
      if (this._pendingSentences <= 0 && this._llmDone) {
        this._finishSpeaking();
      }
    };

    // 3. STT (VAD) — initialized lazily on first mic enable to avoid
    // prompting for mic permission on page load
    this.stt.onSpeechStart = () => {
      // Barge-in: interrupt avatar if speaking
      if (this.state.is(States.SPEAKING) || this.state.is(States.THINKING)) {
        this.interrupt();
      }
      this.state.transition(States.LISTENING);
    };

    this.stt.onSpeechEnd = () => {
      this.state.transition(States.TRANSCRIBING);
    };

    this.stt.onTranscription = (text) => {
      this.handleUserInput(text);
    };

    this.stt.onError = (err) => {
      error('STT error:', err);
      this.state.transition(States.IDLE);
      if (this.onError) this.onError(`STT error: ${err.message}`);
    };

    if (onProgress) onProgress('Ready!', 100);
    log('Orchestrator initialized');
  }

  async handleUserInput(text) {
    if (!text?.trim()) return;

    log(`User: "${text}"`);
    if (this.onUserSpeech) this.onUserSpeech(text);

    // Interrupt any in-progress response
    if (!this.state.is(States.IDLE) && !this.state.is(States.LISTENING)) {
      this.interrupt();
    }

    this.conversation.addUserMessage(text);
    this.state.transition(States.THINKING);

    this._rawBuffer = '';
    this._tokenBuffer = '';
    this._isThinking = false;
    this._thinkingDone = false;
    this._emotionParsed = false;
    this._currentEmotion = null;
    this._pendingSentences = 0;
    this._llmDone = false;
    this._speakPhaseStart = null;

    await this._callLLMWithRetry(MAX_RETRIES);
  }

  async _callLLMWithRetry(retriesLeft) {
    const messages = this.conversation.getMessagesForAPI();

    try {
      this._fillerPlayedThisTurn = false;  // reset per user turn
      this._activeToolName = null;

      this._tokensEmittedThisRound = false;
      await this.llm.chatCompletion(
        messages,
        {
          onToken: (token) => {
            if (!this._tokensEmittedThisRound) {
              this._dashboardState?.emit('llm.first_token', { round: this._currentRound });
              this._tokensEmittedThisRound = true;
            }
            if (this.onAssistantToken) this.onAssistantToken(token);
            this._handleStreamToken(token);
          },
          onDone: (fullText) => {
            this._dashboardState?.emit('done', {});
            this._cancelFillerTimer();
            this._handleStreamDone(fullText);
          },
          onError: (err) => {
            this._dashboardState?.emit('error', { message: err?.message || String(err) });
            this._cancelFillerTimer();
            throw err;
          },
          onThinkingToken: (delta) => {
            this._dashboardState?.emit('thinking_token', { delta });
            if (this.onThinkingToken) this.onThinkingToken(delta);
          },
          onToolCallStart: ({ id, name, arguments: args }) => {
            log(`Tool call start: ${name}(${JSON.stringify(args).substring(0, 80)})`);
            this._dashboardState?.emit('tool_call_start', { id, name, arguments: args });
            this._activeToolName = name;
            this.state.transition(this._stateForTool(name));
            // Plan #10 — deterministic verbal filler tied to the tool family.
            // Replaces the timer-based "let me think" with a phrase that signals
            // *which* tool is firing. The model is forbidden (via personality
            // system prompt) from narrating tool use; this fills that gap.
            const phrase = pickPhrase(name);
            if (phrase && this.tts) {
              this.tts.synthesizeFiller(phrase);
            }
            if (!phrase) {
              this._armFillerTimer();
            }
            if (this.onToolCallStart) this.onToolCallStart({ id, name, arguments: args });
          },
          onToolCallEnd: ({ id, result_preview, duration_ms, error: toolErr }) => {
            log(`Tool call end: ${id} (${duration_ms.toFixed(0)}ms${toolErr ? ', error: ' + toolErr : ''})`);
            this._dashboardState?.emit('tool_call_end', { id, name: this._activeToolName, result_preview, duration_ms, error: toolErr });
            this._cancelFillerTimer();
            this.state.transition(States.THINKING);
            this._activeToolName = null;
            if (this.onToolCallEnd) {
              this.onToolCallEnd({ id, result_preview, duration_ms, error: toolErr });
            }
          },
          onStageTiming: (timing) => {
            this._dashboardState?.emit('stage_timing', timing);
            if (timing?.stage === 'round_start' && timing?.round_num != null) {
              this._currentRound = timing.round_num;
              this._tokensEmittedThisRound = false;
            }
            if (this.onStageTiming) this.onStageTiming(timing);
          },
        },
        {
          // Plan #7: server-side state is canonical; these are sent for
          // backwards compatibility but the orchestrator strips them and
          // reads from state.tools instead.
          webSearch: this._webSearchEnabled,
          wiki: this._wikiEnabled,
        },
      );
    } catch (err) {
      if (err?.name === 'AbortError') return;

      if (retriesLeft > 0) {
        warn(`LLM error, retrying (${retriesLeft} left)...`, err.message);
        await this._sleep(RETRY_DELAY_MS);
        if (!this.state.is(States.THINKING)) return; // User may have interrupted
        return this._callLLMWithRetry(retriesLeft - 1);
      }

      error('LLM failed after retries:', err);
      this.state.transition(States.IDLE);
      if (this.onError) this.onError(`LLM error: ${err.message}`);
    }
  }

  _handleStreamToken(token) {
    this._rawBuffer += token;

    // Phase 1: Detect if this is a thinking model response
    //
    // The active brain's `thinks` flag (from /v1/catalog) tells us whether to
    // expect a <think>...</think> reasoning block. Non-thinking models stream
    // tokens through immediately. Thinking models buffer until </think> arrives
    // (Ollama qwen3 thinking finetune omits the opening <think> tag — see
    // research findings in commit 8f01012).
    if (!this._thinkingDone) {
      const brain = this._activeBrainEntry();
      if (!brain?.thinks) {
        // Non-thinking model — flush buffer and stream from here
        this._thinkingDone = true;
        this._tokenBuffer = this._rawBuffer;
        log('Non-thinking model — streaming tokens directly');
      } else {
        const closeIdx = this._rawBuffer.indexOf(THINK_CLOSE);
        if (closeIdx !== -1) {
          this._isThinking = true;
          this._thinkingDone = true;
          this._tokenBuffer = this._rawBuffer.slice(closeIdx + THINK_CLOSE.length).replace(/^\s+/, '');
          this._cancelFillerTimer();
          log('Thinking done (</think> detected), streaming final response');
        } else {
          // Still inside the thinking phase — keep buffering for </think>
          this._isThinking = true;
          return;
        }
      }
    } else {
      // Past detection/thinking — append new tokens directly
      this._tokenBuffer += token;
    }

    // Phase 2: Parse emotion tag from the beginning of response (once)
    if (!this._emotionParsed) {
      const { emotion, cleanText } = this.conversation.parseEmotionTag(this._tokenBuffer);
      if (emotion) {
        this._currentEmotion = emotion;
        this._emotionParsed = true;
        this.emotion.setMood(emotion);
        this._tokenBuffer = cleanText;
      } else if (this._tokenBuffer.length > 20) {
        this._emotionParsed = true;
      }
    }

    this._flushSentences();
  }

  _flushSentences() {
    let match;
    while ((match = this._tokenBuffer.match(SENTENCE_END_RE))) {
      const endIdx = match.index + match[0].length;
      const sentence = this._tokenBuffer.slice(0, endIdx).trim();
      this._tokenBuffer = this._tokenBuffer.slice(endIdx);
      if (sentence) this._enqueueTTS(sentence);
    }
  }

  _enqueueTTS(text) {
    const clean = cleanForTTS(text);
    if (!clean) return;
    this.state.transition(States.SPEAKING);
    this._pendingSentences++;
    this._resetSpeakingTimeout();
    if (this.onAssistantSentence) this.onAssistantSentence(clean);
    this.tts.synthesize(clean);
  }

  _handleStreamDone(fullText) {
    // If thinking detection didn't finish during streaming, resolve it now
    if (!this._thinkingDone) {
      const closeIdx = this._rawBuffer.indexOf(THINK_CLOSE);
      if (closeIdx !== -1) {
        this._tokenBuffer = this._rawBuffer.slice(closeIdx + THINK_CLOSE.length).replace(/^\s+/, '');
      } else {
        // No thinking tags at all — use entire raw buffer
        this._tokenBuffer = this._rawBuffer;
      }
      this._thinkingDone = true;

      // Parse emotion tag if not done yet
      if (!this._emotionParsed) {
        const { emotion, cleanText } = this.conversation.parseEmotionTag(this._tokenBuffer);
        if (emotion) {
          this._currentEmotion = emotion;
          this._emotionParsed = true;
          this.emotion.setMood(emotion);
          this._tokenBuffer = cleanText;
        }
      }
    }

    // Flush remaining text through the same cleanup path
    const remaining = this._tokenBuffer.trim();
    if (remaining) {
      this._enqueueTTS(remaining);
    }
    this._tokenBuffer = '';
    this._llmDone = true;

    // Strip thinking content from full text for conversation history + subtitle.
    // Handles both patterns:
    //   (a) <think>...</think> blocks (llama.cpp era — both tags present)
    //   (b) "...thinking content...</think>\n[answer]" (Ollama qwen3 — only close tag)
    // The LAST </think> in the string marks the boundary between any prior
    // thinking and the actual final answer.
    let responseText = fullText.replace(THINK_BLOCK_RE, '');
    const lastClose = responseText.lastIndexOf(THINK_CLOSE);
    if (lastClose !== -1) {
      responseText = responseText.slice(lastClose + THINK_CLOSE.length);
    }
    responseText = responseText.trim();
    const { cleanText } = this.conversation.parseEmotionTag(responseText);
    this.conversation.addAssistantMessage(cleanText);

    if (this.onAssistantDone) this.onAssistantDone(cleanText);

    // If no sentences were queued, go idle immediately
    if (this._pendingSentences <= 0) {
      this._finishSpeaking();
    }
  }

  _finishSpeaking() {
    this._clearSpeakingTimeout();
    // Emit avatar_speak stage_timing if we tracked a speaking phase
    if (this._speakPhaseStart != null) {
      const duration_ms = Math.round(performance.now() - this._speakPhaseStart);
      this._dashboardState?.emit('stage_timing', { stage: 'avatar_speak', duration_ms });
      this._speakPhaseStart = null;
    }
    // Brief pause after last audio before transitioning to idle
    setTimeout(() => {
      if (this.state.is(States.SPEAKING)) {
        this.state.transition(States.IDLE);
      }
    }, 200);
  }

  _resetSpeakingTimeout() {
    this._clearSpeakingTimeout();
    this._speakingTimer = setTimeout(() => {
      if (this.state.is(States.SPEAKING)) {
        warn('Speaking timeout — forcing transition to IDLE');
        this.tts.clear();
        this.avatar.stopSpeaking();
        this._pendingSentences = 0;
        this.state.transition(States.IDLE);
        if (this.onError) this.onError('Speech timed out');
      }
    }, SPEAKING_TIMEOUT_MS);
  }

  _clearSpeakingTimeout() {
    if (this._speakingTimer) {
      clearTimeout(this._speakingTimer);
      this._speakingTimer = null;
    }
  }

  interrupt() {
    log('Interrupting...');
    this._clearSpeakingTimeout();
    this._cancelFillerTimer();
    this.llm.abort();
    this.tts.clear();
    this.avatar.stopSpeaking();
    this._rawBuffer = '';
    this._tokenBuffer = '';
    this._pendingSentences = 0;
    this._llmDone = false;
    this._fillerPlayedThisTurn = false;
    this._speakPhaseStart = null;
  }

  startListening() {
    this.stt.start();
    this.state.transition(States.LISTENING);
  }

  stopListening() {
    this.stt.pause();
    if (this.state.is(States.LISTENING)) {
      this.state.transition(States.IDLE);
    }
  }

  setVoice(voice) {
    this.tts.setVoice(voice);
  }

  handleVisibility(visible) {
    if (visible) {
      this.avatar.start();
    } else {
      this.avatar.stop();
    }
  }

  _sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /** Plan #5: toggle for browser.* tool family. Set by UIManager. */
  setWebSearch(enabled) {
    this._webSearchEnabled = !!enabled;
    log(`web_search toggle = ${this._webSearchEnabled}`);
  }

  /** Plan #5: toggle for wiki.* tool family. Set by UIManager. */
  setWiki(enabled) {
    this._wikiEnabled = !!enabled;
    log(`wiki toggle = ${this._wikiEnabled}`);
  }

  /**
   * Plan #5: classify a tool name into the right state.
   * Tool name starting with "wiki." → WIKI_QUERY; otherwise TOOL_CALLING.
   */
  _stateForTool(toolName) {
    return toolName && toolName.startsWith('wiki.')
      ? States.WIKI_QUERY
      : States.TOOL_CALLING;
  }

  /**
   * Plan #5: arm an 800ms filler timer when a tool round starts. If the
   * tool finishes before 800ms, cancel. If 800ms elapses, queue ONE
   * filler phrase and don't fire again for this user turn.
   */
  _armFillerTimer() {
    if (this._fillerPlayedThisTurn || this._fillerTimer !== null) return;
    this._fillerTimer = setTimeout(() => {
      if (this.state.isToolingActive() && !this._fillerPlayedThisTurn) {
        const phrase = this._activeToolName?.startsWith('wiki.')
          ? 'Let me check the wiki.'
          : 'Let me look that up.';
        this.tts.synthesizeFiller(phrase);
        this._fillerPlayedThisTurn = true;
      }
      this._fillerTimer = null;
    }, 800);
  }

  _cancelFillerTimer() {
    if (this._fillerTimer !== null) {
      clearTimeout(this._fillerTimer);
      this._fillerTimer = null;
    }
  }

  /**
   * Returns the catalog entry for the currently-active brain, or null if the
   * dashboard state isn't loaded yet. Used by token-streaming logic to gate
   * thinking-detection: if brain.thinks is false, tokens stream immediately;
   * if true, buffer until </think> arrives.
   */
  _activeBrainEntry() {
    const ds = this._dashboardState;
    if (!ds || !ds.catalog || !ds.serverState) return null;
    const activeId = ds.serverState?.active?.brain;
    if (!activeId) return null;
    return ds.getBrain ? ds.getBrain(activeId) : (ds.catalog.brains || []).find((b) => b.id === activeId) || null;
  }
}
