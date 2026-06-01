# Personify Frontend

Next.js 15 + React dashboard. Where users upload their resume, view autofill history, and configure preferences.

## Layout

```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx       Top nav and layout
│   │   ├── page.tsx         Home — backend connection check
│   │   ├── upload/page.tsx  Upload resume / essays
│   │   ├── history/page.tsx Past autofill sessions
│   │   └── settings/page.tsx Tone & length preferences
│   ├── components/          Shared components (TBD)
│   └── lib/api.ts           Tiny fetch client for the backend
├── next.config.mjs
├── tsconfig.json
└── package.json
```

## Quickstart

```bash
npm install
cp .env.local.example .env.local
npm run dev
```

App runs at `http://localhost:3000`. Make sure the backend is running on `localhost:8000` first.

## What's implemented vs stubbed

| Page | Status |
|---|---|
| `/` Home | ✅ Backend health check button |
| `/upload` | ✅ File upload UI calling `/upload` (which returns a stub) |
| `/history` | ✅ Renders results from `/history` (currently empty) |
| `/settings` | ⏳ Static placeholder |
| Auth flow | ⏳ Not yet wired |

See `docs/ROADMAP.md` for the build order.
