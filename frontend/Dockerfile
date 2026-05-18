# Stage 1: Build frontend
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build
# TalkingHead dynamically imports lipsync modules at runtime (path constructed
# from language code, invisible to Vite's bundler). Copy them into dist/assets/
# so they resolve alongside the main bundle chunk.
RUN cp node_modules/@met4citizen/talkinghead/modules/lipsync-*.mjs dist/assets/

# Stage 2: Serve with nginx
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
