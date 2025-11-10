
FROM node:18-alpine

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev

COPY server.js ./
COPY views ./views

# Static dashboard mounted at runtime
VOLUME ["/app/public"]

ENV PORT=3000
EXPOSE 3000

CMD ["npm", "start"]
