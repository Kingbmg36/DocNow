# DocNow.NG frontend — build the CRA/CRACO app, serve the static bundle.

# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json yarn.lock ./
# Non-frozen install: reconciles the removed @emergentbase/visual-edits dev dep
# against the existing lockfile (regenerate yarn.lock locally for a pinned build).
RUN yarn install --network-timeout 600000
COPY . .
# Create React App bakes REACT_APP_* at BUILD time. Railway passes the variable
# of the same name in as a build arg — set it to the backend's public URL.
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
RUN yarn build

# ---- Serve stage ----
FROM node:20-alpine
WORKDIR /app
RUN npm install -g serve
COPY --from=build /app/build ./build
ENV PORT=3000
EXPOSE 3000
# -s = SPA fallback to index.html. Shell form so ${PORT} expands.
CMD serve -s build -l ${PORT}
