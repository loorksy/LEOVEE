FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --omit=dev
COPY server.js ./
COPY lib ./lib
COPY restart-agent.sh ./restart-agent.sh
ENV NODE_ENV=production
EXPOSE 3000
CMD ["node", "server.js"]
