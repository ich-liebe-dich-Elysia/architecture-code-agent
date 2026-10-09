FROM node:22-alpine

WORKDIR /app

ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=3000

COPY package.json ./
RUN npm install --omit=dev --ignore-scripts

COPY src ./src
COPY public ./public

EXPOSE 3000

CMD ["node", "src/app.js"]
