FROM node:24-slim AS build
WORKDIR /app
COPY admin/package.json admin/package-lock.json ./
RUN npm ci
COPY admin/ ./
ARG NEXT_PUBLIC_DEFAULT_ORGANIZATION=""
ENV NEXT_PUBLIC_DEFAULT_ORGANIZATION=$NEXT_PUBLIC_DEFAULT_ORGANIZATION
RUN npm run build

FROM node:24-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
