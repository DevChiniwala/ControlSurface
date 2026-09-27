import type { NextConfig } from "next";

const api = process.env.NEXT_PUBLIC_CONTROL_API || "http://localhost:8000";
let apiOrigin = "http://localhost:8000";
try {
  const parsed = new URL(api);
  if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error();
  apiOrigin = parsed.origin;
} catch {
  throw new Error("NEXT_PUBLIC_CONTROL_API must be an absolute HTTP(S) URL");
}

const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "object-src 'none'",
  "img-src 'self' data:",
  "font-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  "script-src 'self' 'unsafe-inline'",
  `connect-src 'self' ${apiOrigin}`,
].join("; ");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  agentRules: false,
  poweredByHeader: false,
  output: "standalone",
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
