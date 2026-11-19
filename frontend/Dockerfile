FROM nginx:alpine
ARG BACKEND_URL
COPY app/static/index.html /usr/share/nginx/html/index.html
RUN echo "window.API_BASE = '${BACKEND_URL}';" > /usr/share/nginx/html/config.js
RUN sed -i 's/listen\s*80;/listen 8080;/; s/listen\s*\[::\]:80;/listen [::]:8080;/' /etc/nginx/conf.d/default.conf
EXPOSE 8080
