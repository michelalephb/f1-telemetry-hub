/** @type {import('next').NextConfig} */
// Static site. On GitHub Pages the site lives under /<repo>; on a custom domain set NEXT_PUBLIC_BASE_PATH to "".
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? ''
const nextConfig = {
  output: 'export',
  trailingSlash: true,
  basePath,
  images: { unoptimized: true },
}
export default nextConfig
