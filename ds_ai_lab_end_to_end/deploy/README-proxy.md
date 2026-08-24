---
title: Medical Report AI Proxy
emoji: 🔐
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: 5.49.1
app_file: app.py
pinned: false
short_description: Token-holding proxy between the public UI and the private backend
---

# Medical Report AI — proxy

Public Space whose only job is to keep the Hugging Face token out of the
browser. The UI calls this; this calls the private backend Space server-side.

```
browser  ──►  proxy (HF_TOKEN secret)  ──►  private backend
```

## Required secrets

- `HF_TOKEN` — must have read access to the private backend Space.

Never put a token in the frontend. A `VITE_`-prefixed variable is inlined into
the client bundle by Vite and would be readable by anyone.
