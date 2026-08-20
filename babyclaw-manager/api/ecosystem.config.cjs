module.exports = {
  apps: [
    {
      name: "babyclaw-env-api",
      script: "server.js",
      cwd: "/home/babyclaw/env-api",
      interpreter: "node",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "150M",
      env: {
        NODE_ENV: "production",
        PORT: 3000,
      },
    },
  ],
};
