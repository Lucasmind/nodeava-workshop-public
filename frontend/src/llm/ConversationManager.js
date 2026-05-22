import { config } from '../app/config.js';
import { log } from '../utils/logger.js';

const EMOTION_TAG_RE = /^\[(\w+)\]\s*/;
const MAX_HISTORY = 20; // Keep last N messages to avoid context overflow

export class ConversationManager {
  constructor() {
    this.messages = [];
  }

  addUserMessage(text) {
    this.messages.push({ role: 'user', content: text });
    this.trim();
    log(`Conversation: +user (${this.messages.length} msgs)`);
  }

  addAssistantMessage(text) {
    this.messages.push({ role: 'assistant', content: text });
    this.trim();
  }

  getMessagesForAPI() {
    // Plan #7+: the orchestrator owns the system prompt (from the active
    // catalog personality). The frontend's old hardcoded systemPrompt is no
    // longer sent — having two system messages was confusing the model and
    // breaking wiki-tool priming for NodeAva questions.
    return [...this.messages];
  }

  /**
   * Parse emotion tag from the beginning of LLM response text.
   * Returns { emotion, cleanText }.
   */
  parseEmotionTag(text) {
    const match = text.match(EMOTION_TAG_RE);
    if (match) {
      return {
        emotion: match[1].toLowerCase(),
        cleanText: text.slice(match[0].length),
      };
    }
    return { emotion: null, cleanText: text };
  }

  trim() {
    if (this.messages.length > MAX_HISTORY) {
      this.messages = this.messages.slice(-MAX_HISTORY);
    }
  }

  clear() {
    this.messages = [];
    log('Conversation cleared');
  }
}
