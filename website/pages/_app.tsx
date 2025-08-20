import type { AppProps } from 'next/app';
import Head from 'next/head';
import '../styles/globals.css';

export default function App({ Component, pageProps }: AppProps) {
  return (
    <>
      <Head>
        {/* Basic meta tags */}
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        
        {/* SEO meta tags */}
        <meta name="robots" content="index, follow" />
        <meta name="author" content="SASEWaddle Team" />
        <meta name="theme-color" content="#3b82f6" />
        
        {/* Open Graph meta tags */}
        <meta property="og:site_name" content="SASEWaddle" />
        <meta property="og:locale" content="en_US" />
        <meta property="og:type" content="website" />
        <meta property="og:image" content="/images/og-image.png" />
        <meta property="og:image:width" content="1200" />
        <meta property="og:image:height" content="630" />
        
        {/* Twitter Card meta tags */}
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:site" content="@sasewaddle" />
        <meta name="twitter:creator" content="@sasewaddle" />
        <meta name="twitter:image" content="/images/twitter-card.png" />
        
        {/* Favicon and app icons */}
        <link rel="icon" href="/favicon.ico" />
        <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png" />
        <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png" />
        <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
        <link rel="manifest" href="/site.webmanifest" />
        
        {/* DNS prefetch for external resources */}
        <link rel="dns-prefetch" href="//fonts.googleapis.com" />
        <link rel="dns-prefetch" href="//api.github.com" />
        
        {/* Preconnect to important origins */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        
        {/* Canonical URL - will be overridden by individual pages */}
        <link rel="canonical" href="https://sasewaddle.com" />
        
        {/* RSS feed */}
        <link rel="alternate" type="application/rss+xml" title="SASEWaddle Blog" href="/rss.xml" />
        
        {/* Security headers */}
        <meta httpEquiv="X-Content-Type-Options" content="nosniff" />
        <meta httpEquiv="X-Frame-Options" content="DENY" />
        <meta httpEquiv="X-XSS-Protection" content="1; mode=block" />
        
        {/* PWA meta tags */}
        <meta name="application-name" content="SASEWaddle" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <meta name="apple-mobile-web-app-title" content="SASEWaddle" />
        <meta name="format-detection" content="telephone=no" />
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="msapplication-TileColor" content="#3b82f6" />
        <meta name="msapplication-tap-highlight" content="no" />
        
        {/* Structured data for search engines */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "SoftwareApplication",
              "name": "SASEWaddle",
              "description": "Open Source SASE solution implementing Zero Trust Network Architecture",
              "url": "https://sasewaddle.com",
              "applicationCategory": "SecurityApplication",
              "operatingSystem": ["Linux", "macOS", "Windows"],
              "offers": {
                "@type": "Offer",
                "price": "0",
                "priceCurrency": "USD"
              },
              "author": {
                "@type": "Organization",
                "name": "SASEWaddle Team",
                "url": "https://sasewaddle.com"
              },
              "downloadUrl": "https://sasewaddle.com/downloads",
              "featureList": [
                "Zero Trust Network Architecture",
                "WireGuard VPN",
                "Multi-platform clients",
                "Enterprise security",
                "Cloud native deployment"
              ]
            })
          }}
        />
      </Head>
      <Component {...pageProps} />
    </>
  );
}