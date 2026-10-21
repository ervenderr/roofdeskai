// EXPORT=1 builds a static site (Cloudflare Pages) that reads data/snapshot.json instead of the live API.
const nextConfig = process.env.EXPORT ? { output: "export", images: { unoptimized: true } } : {};
export default nextConfig;
