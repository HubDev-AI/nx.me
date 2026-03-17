/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '*.supabase.co' },
      { protocol: 'https', hostname: '*.fal.ai' },
      { protocol: 'https', hostname: 'fal.media' },
    ],
  },
};

export default nextConfig;
