import { log } from '../utils/logger.js';

export const States = {
  IDLE: 'idle',
  LISTENING: 'listening',
  TRANSCRIBING: 'transcribing',
  THINKING: 'thinking',
  TOOL_CALLING: 'tool_calling',   // Plan #5: tool execution in progress
  WIKI_QUERY: 'wiki_query',       // Plan #5: wiki tool specifically (distinct UI affordance)
  SPEAKING: 'speaking',
};

export class StateMachine {
  constructor() {
    this.state = States.IDLE;
    this.onChange = null; // callback(newState, oldState)
  }

  transition(newState) {
    if (newState === this.state) return;
    const old = this.state;
    this.state = newState;
    log(`State: ${old} → ${newState}`);
    if (this.onChange) this.onChange(newState, old);
  }

  is(state) {
    return this.state === state;
  }

  /** True for any state where an agentic tool round is active. */
  isToolingActive() {
    return this.state === States.TOOL_CALLING || this.state === States.WIKI_QUERY;
  }

  get current() {
    return this.state;
  }
}
