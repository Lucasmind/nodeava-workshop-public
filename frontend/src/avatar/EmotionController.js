import { log } from '../utils/logger.js';

// Maps LLM emotion tags to TalkingHead mood names
const EMOTION_MAP = {
  neutral: 'neutral',
  happy: 'happy',
  sad: 'sad',
  angry: 'angry',
  fear: 'fear',
  scared: 'fear',
  disgust: 'disgust',
  disgusted: 'disgust',
  love: 'love',
  loving: 'love',
  sleep: 'sleep',
  sleepy: 'sleep',
  excited: 'happy',
  surprised: 'happy',
  worried: 'fear',
  anxious: 'fear',
  confused: 'neutral',
  thoughtful: 'neutral',
};

const EMOTION_TAG_RE = /^\[(\w+)\]\s*/;

export class EmotionController {
  constructor(avatarManager) {
    this.avatar = avatarManager;
    this.currentMood = 'neutral';
    this.decayTimer = null;
    this.decayDelayMs = 15000; // Return to neutral after 15s
  }

  /**
   * Parse an emotion tag from the beginning of text.
   * Returns { emotion, cleanText } where cleanText has the tag removed.
   */
  parseEmotionTag(text) {
    const match = text.match(EMOTION_TAG_RE);
    if (match) {
      const raw = match[1].toLowerCase();
      const emotion = EMOTION_MAP[raw] || 'neutral';
      const cleanText = text.slice(match[0].length);
      return { emotion, cleanText };
    }
    return { emotion: null, cleanText: text };
  }

  setMood(mood) {
    const mapped = EMOTION_MAP[mood] || mood;
    if (mapped === this.currentMood) return;

    this.currentMood = mapped;
    this.avatar.setMood(mapped);
    log(`Emotion: ${mapped}`);

    this.resetDecayTimer();
  }

  resetDecayTimer() {
    if (this.decayTimer) clearTimeout(this.decayTimer);
    if (this.currentMood !== 'neutral') {
      this.decayTimer = setTimeout(() => {
        this.setMood('neutral');
      }, this.decayDelayMs);
    }
  }

  get mood() {
    return this.currentMood;
  }
}
