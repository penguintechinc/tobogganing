/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  trailingSlash: true,
  skipTrailingSlashRedirect: true,
  distDir: 'out',
  images: {
    unoptimized: true
  },
  
  // Cloudflare Pages configuration
  
  // Environment variables for build
  env: {
    NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL || 'https://tobogganing.io',
    NEXT_PUBLIC_GITHUB_URL: process.env.NEXT_PUBLIC_GITHUB_URL || 'https://github.com/penguintechinc/Tobogganing',
    NEXT_PUBLIC_DOCS_URL: process.env.NEXT_PUBLIC_DOCS_URL || 'https://docs.tobogganing.io'
  },
  
  // Note: Redirects and headers are handled by Cloudflare Pages for static exports
  // See _redirects and _headers files in public/ directory
};

module.exports = nextConfig;