# Build stage
FROM node:20-alpine AS build

WORKDIR /app

# Install dependencies first (better caching)
COPY package.json ./
RUN npm install

# Copy source and build
COPY . .
RUN npm run build

# Development stage
FROM node:20-alpine AS dev
WORKDIR /app
COPY --from=build /app/node_modules ./node_modules
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]

# Production stage
FROM nginxinc/nginx-unprivileged:1.27-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
USER 101
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
