/** @type {import('next').NextConfig} */
const nextConfig = {
  // hyparquet ships ESM and wasm decompressors; keep them out of the server bundle
  serverExternalPackages: ['hyparquet', 'hyparquet-compressors'],
  async headers() {
    // Test build: keep it out of search engines
    return [{ source: '/:path*', headers: [{ key: 'X-Robots-Tag', value: 'noindex, nofollow' }] }]
  },
}
export default nextConfig
