# The web image: the SPA built once, then served by nginx.
#
# nginx is also the deployment's single origin. ADR-0020 splits the HTTP surface into two processes,
# and `frontend/vite.config.ts` is what puts them behind one origin during development; the
# configuration copied below is the same routing rule for a deployment, so the browser keeps talking
# to one host and the API needs no CORS policy.
#
# Build context is the repository root so the nginx configuration travels with the image:
#
#   docker build -f frontend/Dockerfile -t clauserag-web .
FROM node:24-alpine AS build

WORKDIR /app

# pnpm is pinned to the version `package.json` declares (`packageManager`), so the image resolves the
# same tree the lockfile was reviewed against. `--frozen-lockfile` refuses to resolve anything new.
RUN npm install --global pnpm@12.8.1
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/pnpm-store pnpm install --frozen-lockfile --store-dir=/pnpm-store

COPY frontend/ ./
RUN pnpm run build

FROM nginx:1.29-alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
