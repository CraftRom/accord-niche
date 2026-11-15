FROM node:24-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG WEBSITE_BASE=/site/
ENV WEBSITE_BASE=${WEBSITE_BASE}
RUN npm run build
FROM nginx:1.30.5-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
