# Build context: openshorts; for example:
# docker build -f deploy/frontend.Dockerfile -t content-fabric-frontend .
FROM node:22-bookworm-slim AS build

WORKDIR /app
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY dashboard/ ./
RUN npm run build

FROM nginx:stable-alpine

COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY LICENSE THIRD_PARTY_NOTICES.md /usr/share/licenses/content-fabric/
# Browser-side Remotion compositions request staticFile("fonts/NotoSerif-Bold.ttf").
COPY remotion/public/fonts/ /usr/share/nginx/html/fonts/

EXPOSE 80
