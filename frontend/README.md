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
here is not arbitrary: the backend's CORS allow-list names 3000, so moving it
gives you a blank page and a console full of CORS errors.

```bash
npm test             # 111 tests, jsdom, no network
npm run lint
npm run build && npm run serve   # the real bundle, on :4173
```

`npm run serve` is a small stdlib Node server (`scripts/serve-dist.mjs`) that
negotiates Brotli and gzip and sets immutable cache headers. It exists because
`vite preview` sends everything uncompressed, which makes the bundle impossible
to measure honestly. **Run Lighthouse against 4173, never the dev server.** Dev
serves unminified ES modules and scores meaninglessly low.

## Configuration

One variable, and you only need it if the backend isn't on localhost:

```bash
cp .env.example .env
# VITE_API_URL=http://127.0.0.1:5000
```

It's read in `src/config/api.ts`, and also substituted into `index.html` for the
preconnect and preload hints. Both have to agree, or you warm the wrong socket.
An undefined `%VITE_API_URL%` makes the build warn on every run, which is why
the file is worth having even at its default value.

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

**No component library.** Radix supplies the dialog primitive, the one piece
with real focus-trap and accessibility work behind it, and the rest is Tailwind
against the design tokens in `index.css`.

**No theme provider.** The palette is a single FT-style warm paper tone. A dark
mode nobody asked for is a class toggle plus a second set of tokens to keep in
sync forever.

## Live updates

`useLiveUpdates` holds a WebSocket to the backend's `/ws`, which pushes one
message whenever anything was committed: a scheduler refresh, or a watchlist
edit in another tab. Every query is then stale and React Query refetches
whatever is on screen over REST. The socket reconnects with capped backoff, so a
backend restart heals itself.

## The AI toggles

Two optional backend features are switchable from the ticker strip: grading new
articles for impact during a scrape, and summaries on demand. `useAppConfig`
reads and writes them through `/config`, and the dialog says out loud when a
flag is on but inert because the key is missing or was rejected, which is the
difference between "this switch is broken" and "you need a key".

The masthead doubles as the indicator. It flickers RGB while grading is actually
running and sits flat black when it is not, driven by the effective state rather
than the flag, so it cannot claim to be spending tokens it has no usable key
for. Per-letter timings are picked once at mount and then left to CSS, because
re-rolling colours from JS on a timer would re-render the top of the page
several times a second forever.

Toasts report what the server confirmed, never what was clicked. While the
settings dialog is open it renders the toast inside its own portal, since a
modal Radix dialog puts `aria-hidden="true"` on every other body child and would
silently neuter an `aria-live` region sitting outside it.

## Why the first paint is fast

`index.html` fires the four above-the-fold requests (watchlist, trending,
latest, movers) during HTML parse, before the bundle has even booted, and
`takeBoot()` in `src/services/api.ts` claims each one exactly once. That buys
roughly 200 to 400ms over waiting for React. If a preload failed, or the app is
pointed at a different origin than the one `index.html` warmed, the hook just
makes a normal request and nobody notices.

The three dialogs (article reader, watchlist editor, AI settings) are
`React.lazy`, so they stay out of the initial bundle entirely. They're behind a
click.

React Grab is imported in `src/main.tsx` behind `import.meta.env.DEV`. Vite
replaces that with a literal `false` in a build, so the bundler drops the
dynamic import as dead code rather than shipping a 386kB overlay to production.

## License

MIT. See [LICENSE](../LICENSE).
