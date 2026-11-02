// The browser only ever talks to this site (/api/...). Next/Vercel forwards those calls to the backend,
// so the login cookie is first-party and works in Safari too. BACKEND_URL is read at build time.
const backend = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

/** @type {import('next').NextConfig} */
export default {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
};
