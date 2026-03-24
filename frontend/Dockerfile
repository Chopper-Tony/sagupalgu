# ── Stage 1: 빌드 ─────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Stage 2: 서빙 (nginx) ──────────────────────────────────────
FROM nginx:alpine

# React 빌드 결과물 복사
COPY --from=builder /app/dist /usr/share/nginx/html

# nginx 설정 (SPA routing + API proxy)
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
