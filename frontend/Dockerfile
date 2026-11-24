# CVE-2026-123633 / CVE-2026-123007: require patched NGINX OSS (>= 1.30.7 stable)
FROM nginx:1.30.7-alpine
ARG BACKEND_URL
COPY app/static/index.html /usr/share/nginx/html/index.html
RUN echo "window.API_BASE = '${BACKEND_URL}';" > /usr/share/nginx/html/config.js
RUN sed -i 's/listen\s*80;/listen 8080;/; s/listen\s*\[::\]:80;/listen [::]:8080;/' /etc/nginx/conf.d/default.conf
# Workaround/hardening: ensure HTTP/2 is not enabled in any server block
RUN sed -i -E 's/(listen[^;]*)\shttp2/\1/; s/^\s*http2\s+on;/    http2 off;/' /etc/nginx/conf.d/default.conf
EXPOSE 8080
