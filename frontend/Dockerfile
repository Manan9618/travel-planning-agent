# Frontend Dockerfile (Week 18) — multi-stage: node builds the static
# Vite bundle, nginx serves it. Build context is this frontend/ directory
# (see docker-compose.yml's `build: { context: ./frontend }`).

FROM node:20-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# Vite bakes VITE_-prefixed env vars into the JS bundle AT BUILD TIME, not
# read at container start - there's no such thing as "the same image,
# reconfigured for a different backend URL" for a Vite SPA without a
# rebuild. ARG (not a runtime ENV) makes that explicit: pass
# --build-arg VITE_API_BASE_URL=... to point a build at a different
# backend. docker-compose.yml passes the in-compose backend service URL.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build


FROM nginx:1.27-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# 127.0.0.1, not localhost: this image's /etc/hosts resolves "localhost" to
# ::1 (IPv6) before 127.0.0.1, but nginx's `listen 80;` (nginx.conf) only
# binds IPv4 - wget then tried the IPv6 loopback first and got connection
# refused, marking a genuinely healthy, correctly-serving container
# "unhealthy". Found live-testing a real docker-compose up - curl against
# the actual mapped host port worked the whole time, so this only ever
# affected Docker's own health status, never real traffic.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/health || exit 1
