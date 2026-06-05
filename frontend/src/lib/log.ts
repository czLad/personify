// Lightweight debug logger.
//
// Why this exists: scattered console.log calls leak internal state, data
// shapes, and user data into the browser console — visible to screen shares,
// support tooling, and other extensions. This gates that noise so it only
// appears during development.
//
// Two things to keep straight:
//   1. This is NOT a security boundary. Client code ships to the browser and
//      can always be read. The flag reduces information disclosure by default;
//      it does not hide anything from a determined reader.
//   2. The real rule lives below this flag: NEVER log secrets — auth tokens,
//      passwords, full document contents, or PII — at any level. Log
//      identifiers and shapes, not payloads.
//
// Gating: NODE_ENV is set to "production" automatically by `next build` /
// `next start`, so debug/warn are no-ops in any production deployment. Set
// NEXT_PUBLIC_DEBUG="true" to force logs on (e.g. to debug a prod build), or
// "false" to force them off in dev.

const DEBUG =
  process.env.NEXT_PUBLIC_DEBUG === "true" ||
  (process.env.NEXT_PUBLIC_DEBUG !== "false" &&
    process.env.NODE_ENV !== "production");

export const log = {
  debug: (...args: unknown[]) => {
    if (DEBUG) console.log(...args);
  },
  warn: (...args: unknown[]) => {
    if (DEBUG) console.warn(...args);
  },
  // Errors always surface: they aren't noise, and you want them when
  // diagnosing a production issue. Still: don't pass secrets into them.
  error: (...args: unknown[]) => {
    console.error(...args);
  },
};