/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    // The installed ESLint 9 toolchain is incompatible with Next 14's built-in
    // `next lint` wrapper, which passes legacy options ESLint 9 removed. We lint
    // via `npm run lint` (ESLint flat config) instead, so skip the broken
    // build-time wrapper rather than failing the build on a tooling mismatch.
    ignoreDuringBuilds: true,
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: "http://localhost:8000/api/v1/:path*",
      },
    ];
  },
  // Extend server-side proxy timeout for slow LLM inference
  experimental: {
    proxyTimeout: 120_000,
  },
};

export default nextConfig;
