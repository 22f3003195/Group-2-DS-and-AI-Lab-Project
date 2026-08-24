---
title: MedReport AI
emoji: 💙
colorFrom: blue
colorTo: indigo
sdk: static
app_file: index.html
pinned: false
short_description: Understand your lab report in plain English
---

# MedReport AI — frontend

React + Vite. Calls the backend Space with `@gradio/client`. Holds no
credentials.

> The contents of this Space are a **pre-built** Vite bundle. Hugging Face's
> server-side `app_build_command` is a paid feature ("Static space builds
> require credits"), so `deploy/push_space.sh frontend` runs `npm run build`
> locally and uploads `dist/` instead. Plain static Spaces are free.

```bash
npm install
npm run dev      # http://localhost:5173
npm run build
npx vitest run
```

Configured in `src/services/api.ts`:

```ts
Client.connect("rajsri2609/medical-report-ai-proxy")
```
