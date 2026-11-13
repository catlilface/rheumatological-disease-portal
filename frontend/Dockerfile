# syntax=docker/dockerfile:1

FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime

# Defaults; override at runtime with --env-file .env or -e
ENV NGINX_CLIENT_MAX_BODY_SIZE=100m \
    NGINX_BACKEND_URL=http://server:8000 \
    NGINX_RESOLVER=127.0.0.11

# The nginx entrypoint renders templates via envsubst on start
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
