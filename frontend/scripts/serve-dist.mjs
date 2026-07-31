/**
 * Serve `dist/` with Brotli, falling back to gzip, falling back to identity.
 *
 * `vite preview` sends everything uncompressed, so the built bundle could not
 * be measured — or scored — the way it would actually ship. Node's stdlib has
 * both codecs and an HTTP server, so this needs no dependency.
 *
 * ponytail: compresses on first request and caches in memory. Fine for a dist
 * of a few dozen files; precompress at build time if it ever serves real load.
 *
 * HTTP/2 and HTTP/3 are deliberately absent: both require a certificate, and
 * Node cannot mint one from the standard library. Terminate them at whatever
 * proxy or CDN fronts this in production — the compression and cache headers
 * below are the part that belongs in the app.
 *
 *   node scripts/serve-dist.mjs [port]
 */
import { createReadStream, existsSync, statSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";
import { brotliCompressSync, constants, gzipSync } from "node:zlib";

const ROOT = resolve(import.meta.dirname, "..", "dist");
const PORT = Number(process.argv[2] || 4173);

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".json": "application/json; charset=utf-8",
  ".ico": "image/x-icon",
  ".png": "image/png",
  ".webp": "image/webp",
  ".avif": "image/avif",
  ".woff2": "font/woff2",
};

// Already-compressed formats gain nothing and cost CPU.
const COMPRESSIBLE = /^(text\/|application\/json|image\/svg)/;

const cache = new Map();

const encode = async (path, encoding) => {
  const key = `${path}|${encoding}`;
  if (cache.has(key)) return cache.get(key);

  const raw = await readFile(path);
  const body =
    encoding === "br"
      ? brotliCompressSync(raw, {
          params: { [constants.BROTLI_PARAM_QUALITY]: 11 },
        })
      : encoding === "gzip"
        ? gzipSync(raw, { level: 9 })
        : raw;

  cache.set(key, body);
  return body;
};

createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`);
    // normalize() collapses `..` before the prefix check, so a crafted path
    // cannot escape dist/.
    const requested = join(ROOT, normalize(decodeURIComponent(url.pathname)));
    const path =
      requested.startsWith(ROOT) && existsSync(requested) && statSync(requested).isFile()
        ? requested
        : join(ROOT, "index.html"); // SPA fallback

    const type = TYPES[extname(path)] ?? "application/octet-stream";
    const accepted = req.headers["accept-encoding"] ?? "";
    const encoding = !COMPRESSIBLE.test(type)
      ? null
      : accepted.includes("br")
        ? "br"
        : accepted.includes("gzip")
          ? "gzip"
          : null;

    res.setHeader("Content-Type", type);
    res.setHeader("Vary", "Accept-Encoding");
    // Vite fingerprints everything under /assets/, so it is immutable; the
    // HTML entry point must never be cached or a deploy would not land.
    res.setHeader(
      "Cache-Control",
      path.includes(`${join("dist", "assets")}`) || /\.[0-9a-f]{8}\./.test(path)
        ? "public, max-age=31536000, immutable"
        : "no-cache",
    );

    if (!encoding) {
      res.writeHead(200);
      createReadStream(path).pipe(res);
      return;
    }

    const body = await encode(path, encoding);
    res.setHeader("Content-Encoding", encoding);
    res.setHeader("Content-Length", body.length);
    res.writeHead(200);
    res.end(req.method === "HEAD" ? undefined : body);
  } catch (error) {
    res.writeHead(500, { "Content-Type": "text/plain" });
    res.end(`500 ${error.message}`);
  }
}).listen(PORT, "127.0.0.1", () => {
  console.log(`dist served with brotli/gzip on http://127.0.0.1:${PORT}`);
});
