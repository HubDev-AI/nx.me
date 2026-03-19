/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: process.env.NEXT_PUBLIC_SUPABASE_HOSTNAME ?? '**.supabase.co',
        // L-17: Ideally pin to project-specific hostname via NEXT_PUBLIC_SUPABASE_HOSTNAME
      },
      { protocol: 'https', hostname: '*.fal.ai' },
      { protocol: 'https', hostname: 'fal.media' },
    ],
  },
  async headers() {
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
              // Supabase storage images + fal.ai generated images + data URIs
              "img-src 'self' https://*.supabase.co https://*.fal.ai https://fal.media data:",
              // Next.js injects inline styles at runtime
              "style-src 'self' 'unsafe-inline'",
              "font-src 'self'",
              "script-src 'self'",
            ].join('; '),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
