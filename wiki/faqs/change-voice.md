# How do I change the avatar's voice?

The avatar's voice is controlled by a dropdown in the Control Panel UI, which passes the selected value to [[text-to-speech]] at runtime with no restart required.

To change the voice:

1. Open the NodeAva interface in the browser.
2. Locate the voice selector in the Control Panel.
3. Choose one of the eight available voices from the dropdown.

The available voices are:

| Value | Label |
|---|---|
| `af_bella` | Bella (F, US) |
| `af_nova` | Nova (F, US) |
| `af_sarah` | Sarah (F, US) |
| `am_fenrir` | Fenrir (M, US) |
| `am_adam` | Adam (M, US) |
| `am_michael` | Michael (M, US) |
| `bf_emma` | Emma (F, UK) |
| `bm_george` | George (M, UK) |

To change the default voice that loads on startup, update `ttsDefaultVoice` in `frontend/src/app/config.js` to any of the values in the left column above.

The selected voice is sent with every synthesis request to the Kokoro-FastAPI backend via `TTSManager.setVoice()`. Sentences already queued when the selection changes will use the previous voice; only subsequent synthesis calls pick up the new value.

See also: [[text-to-speech]], [[control-panel]].
