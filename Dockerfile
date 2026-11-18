FROM node:22-bookworm-slim AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

FROM node:22-bookworm-slim AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run postinstall && npm run build

FROM node:22-bookworm-slim AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    JOURNAL_PYTHON=/opt/quarter-venv/bin/python

RUN apt-get update \
    && apt-get install --no-install-recommends --yes python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python3 -m venv /opt/quarter-venv \
    && /opt/quarter-venv/bin/pip install --no-cache-dir --requirement requirements.txt

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
COPY --from=builder /app/markdown_columns.py ./markdown_columns.py
COPY --from=builder /app/assets ./assets
COPY --from=builder /app/vendor ./vendor

EXPOSE 3000
CMD ["node", "server.js"]
