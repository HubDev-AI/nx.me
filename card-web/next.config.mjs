/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    unoptimized: true,
    remotePatterns: [
      {
        protocol: 'https',
        hostname: process.env.NEXT_PUBLIC_SUPABASE_HOSTNAME ?? 'CONFIGURE_SUPABASE_HOSTNAME.supabase.co',
      },
      { protocol: 'https', hostname: '*.fal.ai' },
      { protocol: 'https', hostname: '*.fal.run' },
      { protocol: 'https', hostname: 'fal.media' },
    ],
  },
  headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          // Disabled per OWASP — modern browsers handle XSS natively
          { key: 'X-XSS-Protection', value: '0' },
          { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              // Supabase storage images + fal.ai/fal.run generated images + data URIs
              "img-src 'self' https://*.supabase.co https://*.fal.ai https://*.fal.run https://fal.media data:",
              // Next.js injects inline styles at runtime
              "style-src 'self' 'unsafe-inline'",
              "font-src 'self'",
              // Next.js requires unsafe-inline for inline scripts (nonce-based CSP preferred long-term)
              "script-src 'self' 'unsafe-inline'",
            ].join('; '),
          },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=(), payment=()' },
        ],
      },
    ];
  },
};

export default nextConfig;
