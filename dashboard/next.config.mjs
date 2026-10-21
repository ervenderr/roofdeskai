import path from "node:path"

// EXPORT=1 builds a static site (Cloudflare Pages) that reads data/snapshot.json instead of the live API.
// Server Actions (the Approve/Reject buttons) are not allowed in a static export, so that module is stubbed.
const nextConfig = process.env.EXPORT
  ? {
      output: "export",
      images: { unoptimized: true },
      webpack(config, { webpack }) {
        config.plugins.push(new webpack.NormalModuleReplacementPlugin(/review-actions$/, path.resolve("lib/review-actions.stub.ts")))
        return config
      },
    }
  : {}
export default nextConfig
