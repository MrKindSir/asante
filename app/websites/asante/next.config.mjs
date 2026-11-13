/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  basePath: "/asante",
  trailingSlash: true,
  // Keep Vitest files such as app/page.test.ts out of the App Router page scan.
  pageExtensions: ["tsx", "jsx"]
};

export default nextConfig;
