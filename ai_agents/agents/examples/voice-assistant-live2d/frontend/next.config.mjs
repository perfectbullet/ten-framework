/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: false,

  experimental: {
    allowedDevOrigins: [
      'http://localhost:3000',
      'https://localhost:3000',
      'http://192.168.8.230:3000',
      'https://192.168.8.230:3001',
      'http://192.168.8.230:3001',
      'http://192.168.8.230',
      'http://ten_agent_dev:3000',
      'https://ten_agent_dev:3000',
      'http://ten_agent_dev:3000',
      'https://ten_agent_dev:3001',
      'http://ten_agent_dev:3001',
      'http://ten_agent_dev',
    ],
  },

  webpack: (config, { webpack }) => {
    config.plugins.push(
      new webpack.ProvidePlugin({
        PIXI: 'pixi.js',
      })
    );
    return config;
  },
};

export default nextConfig;