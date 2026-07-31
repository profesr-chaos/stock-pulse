# Stocky frontend

One page. A ticker strip, your watchlist, and a river of news ranked by how far
the price moved. Everything comes from the [backend](../backend/) over HTTP;
this app stores nothing and knows nothing about accounts, because there aren't
any.

## Getting started

```bash
npm install
npm run dev          # http://127.0.0.1:3000
```

The backend needs to be running on port 5000 for anything to appear. The port
here is not arbitrary — the backend's CORS allow-list names 3000, so moving it
gives you a blank page and a console full of CORS errors.

```bash
npm test             # 69 tests, jsdom, no network
npm run lint
npm run build && npm run serve   # the real bundle, on :4173
```

`npm run serve` is a small stdlib Node server (`scripts/serve-dist.mjs`) that
negotiates Brotli and gzip and sets immutable cache headers. It exists because
`vite preview` sends everything uncompressed, which makes the bundle impossible
to measure honestly. **Run Lighthouse against 4173, never the dev server** —
dev serves unminified ES modules and scores meaninglessly low.

## Configuration

One variable, and you only need it if the backend isn't on localhost:

```bash
VITE_API_URL=http://127.0.0.1:5000
```

It's read in `src/config/api.ts`, and also substituted into `index.html` for the
preconnect and preload hints. Both have to agree, or you warm the wrong socket.

## How it's put together

```
src/
├── pages/Home.tsx      # the whole screen
├── components/         # ticker strip, news river, watchlist, dialogs
├── hooks/              # one per data concern, all React Query
├── services/           # api.ts (the fetch wrapper) + one module per route group
├── config/api.ts       # base URL and per-query stale times
├── lib/format.ts       # money, percentages, relative dates
└── types/stock.ts      # the shapes the API returns
```

React Query owns all server state, so there is no store, no context, no reducer.
Components read hooks; hooks read services; services do fetch. That's the whole
data path.

A few deliberate absences:

**No router.** There is one view. React Router was shipping a path matcher and a
history stack to choose between `/` and a 404.

**No component library.** Radix supplies the dialog primitive — the one piece
with real focus-trap and accessibility work behind it — and the rest is Tailwind
against the design tokens in `index.css`.

**No theme provider.** The palette is a single FT-style warm paper tone. A dark
mode nobody asked for is a class toggle plus a second set of tokens to keep in
sync forever.

## Why the first paint is fast

`index.html` fires the four above-the-fold requests — watchlist, trending,
latest, movers — during HTML parse, before the bundle has even booted, and
`takeBoot()` in `src/services/api.ts` claims each one exactly once. That buys
roughly 200–400ms over waiting for React. If a preload failed, or the app is
pointed at a different origin than the one `index.html` warmed, the hook just
makes a normal request and nobody notices.

The two dialogs (article reader, watchlist editor) are `React.lazy`, so they
stay out of the initial bundle entirely — they're behind a click.

## License

Private — all rights reserved.
