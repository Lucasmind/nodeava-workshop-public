// Emoji unicode ranges (covers most common emoji)
const EMOJI_RE = /[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F1E0}-\u{1F1FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{FE00}-\u{FE0F}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}\u{200D}\u{20E3}\u{E0020}-\u{E007F}]+/gu;

function cleanDisplayText(text) {
  // Strip emojis
  text = text.replace(EMOJI_RE, '');
  // Strip markdown formatting
  text = text.replace(/\*\*(.+?)\*\*/g, '$1');  // **bold**
  text = text.replace(/\*(.+?)\*/g, '$1');       // *italic*
  text = text.replace(/^#{1,6}\s+/gm, '');       // ### headings
  text = text.replace(/^---+$/gm, '');            // --- rules
  text = text.replace(/^[-*+]\s+/gm, '');         // - bullets
  text = text.replace(/^\d+\.\s+/gm, '');         // 1. numbered lists
  text = text.replace(/`([^`]+)`/g, '$1');         // `code`
  // Normalize spaces before punctuation: " !" → "!"
  text = text.replace(/\s+([.,!?;:)])/g, '$1');
  // Normalize spaces after opening parens: "( " → "("
  text = text.replace(/([(])\s+/g, '$1');
  // Trim leading punctuation left after emotion tag stripping
  text = text.replace(/^[,;:\s]+/, '');
  // Collapse multiple spaces
  text = text.replace(/\s{2,}/g, ' ');
  return text.trim();
}

export class SubtitleOverlay {
  constructor(containerEl) {
    this.container = containerEl;
    this.currentLine = null;
    this.fadeTimer = null;
  }

  showUser(text) {
    this.finalizeCurrent();
    const line = document.createElement('div');
    line.className = 'subtitle-text user';
    line.textContent = text;
    this.container.appendChild(line);
    this.scheduleCleanup();
  }

  startAssistant() {
    if (this.currentLine) return; // already have an active line for this response
    this.currentLine = document.createElement('div');
    this.currentLine.className = 'subtitle-text assistant';
    this.container.appendChild(this.currentLine);
  }

  appendSentence(text) {
    if (!this.currentLine) this.startAssistant();
    const clean = cleanDisplayText(text);
    if (!clean) return;
    const existing = this.currentLine.textContent;
    this.currentLine.textContent = existing ? existing + ' ' + clean : clean;
  }

  replaceAssistant(text) {
    if (!this.currentLine) return;
    const clean = cleanDisplayText(text);
    if (clean) this.currentLine.textContent = clean;
  }

  finalizeCurrent() {
    this.currentLine = null;
  }

  clear() {
    this.currentLine = null;
    while (this.container.firstChild) {
      this.container.removeChild(this.container.firstChild);
    }
  }

  scheduleCleanup() {
    if (this.fadeTimer) clearTimeout(this.fadeTimer);
    this.fadeTimer = setTimeout(() => {
      // Remove old lines, keep last 3
      while (this.container.children.length > 3) {
        this.container.removeChild(this.container.firstChild);
      }
    }, 10000);
  }
}
