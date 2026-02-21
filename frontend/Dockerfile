# Build stage
FROM node:20-alpine AS build

WORKDIR /app
RUN chown -R node:node /app

# Install dependencies first (better caching)
COPY --chown=node:node package.json package-lock.json ./
USER node
RUN npm ci

# Copy source and build
COPY --chown=node:node . .
RUN npm run build

# Development stage
FROM node:20-alpine AS dev
WORKDIR /app
RUN chown -R node:node /app
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --chown=node:node . .
USER node
EXPOSE 5173
CMD ["npm", "run", "dev"]

# Production stage
FROM nginxinc/nginx-unprivileged:1.27-alpine AS prod
COPY --from=build --chown=101:101 /app/dist /usr/share/nginx/html
COPY --chown=101:101 nginx.conf /etc/nginx/conf.d/default.conf
USER 101
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
