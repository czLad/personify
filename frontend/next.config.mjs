/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  compiler: {
    // Defense in depth: strip all console.* from production builds at compile
    // time, keeping only console.error. Even a stray console.log left in the
    // source won't reach the production bundle. In dev this is false, so the
    // gated logger in src/lib/log.ts controls what shows.
    removeConsole:
      process.env.NODE_ENV === "production" ? { exclude: ["error"] } : false,
  },
};

export default nextConfig;