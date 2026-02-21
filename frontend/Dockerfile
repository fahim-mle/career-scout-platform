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
FROM nginx:alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
# TODO: Add custom nginx config for SPA routing if needed
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
