module.exports = {
  apps: [
    {
      name: "babyclaw-env-api",
      script: "server.js",
      cwd: process.env.API_CWD || "/opt/leovee/api",
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
