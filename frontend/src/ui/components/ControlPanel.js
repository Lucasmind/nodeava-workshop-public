export class ControlPanel {
  constructor(containerEl) {
    this.container = containerEl;
    this.onSpeak = null;       // callback(text)
    this.onMicToggle = null;   // callback(active)
    // Plan #10: voice is selected from the dashboard drawer (configs/catalog.yml).
    // onVoiceChange retained for backward-compat with UIManager but never fires.
    this.onVoiceChange = null;
    this.micActive = false;
    this.build();
  }

  build() {
    // Text input row
    const row = document.createElement('div');
    row.className = 'text-input-row';

    this.textInput = document.createElement('input');
    this.textInput.id = 'text-input';
    this.textInput.type = 'text';
    this.textInput.placeholder = 'Type a message...';
    this.textInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && this.textInput.value.trim()) {
        this.handleSpeak();
      }
    });

    this.speakBtn = document.createElement('button');
    this.speakBtn.id = 'nv-send-btn';
    this.speakBtn.className = 'control-btn';
    this.speakBtn.textContent = 'Send';
    this.speakBtn.addEventListener('click', () => this.handleSpeak());

    row.appendChild(this.textInput);
    row.appendChild(this.speakBtn);

    // Mic button
    this.micBtn = document.createElement('button');
    this.micBtn.id = 'nv-mic-btn';
    this.micBtn.className = 'control-btn';
    this.micBtn.textContent = '🎤 Mic';
    this.micBtn.addEventListener('click', () => this.toggleMic());

    this.container.appendChild(row);
    this.container.appendChild(this.micBtn);
  }

  handleSpeak() {
    const text = this.textInput.value.trim();
    if (!text) return;
    if (this.onSpeak) this.onSpeak(text);
    this.textInput.value = '';
  }

  toggleMic() {
    this.micActive = !this.micActive;
    this.micBtn.textContent = this.micActive ? '🎤 Listening…' : '🎤 Mic';
    this.micBtn.classList.toggle('active', this.micActive);
    if (this.onMicToggle) this.onMicToggle(this.micActive);
  }

  setMicState(active) {
    this.micActive = active;
    this.micBtn.textContent = active ? '🎤 Listening…' : '🎤 Mic';
    this.micBtn.classList.toggle('active', active);
  }

  setSpeakEnabled(enabled) {
    this.speakBtn.disabled = !enabled;
    this.textInput.disabled = !enabled;
  }

  setMicEnabled(enabled) {
    this.micBtn.disabled = !enabled;
  }

}
