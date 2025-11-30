# ==============================================================================
# FA CS Automator - Production Dockerfile
# ==============================================================================
# This creates a containerized version of the application.
# Testers/clients receive only the container image, not source code.
#
# Build: docker build -t fa-cs-automator .
# Run:   docker run -p 8000:8000 -p 5173:5173 fa-cs-automator
# ==============================================================================

# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy frontend source
COPY src/ ./src/
COPY public/ ./public/
COPY index.html ./
COPY vite.config.js ./
COPY tailwind.config.js ./
COPY postcss.config.js ./

# Build frontend
RUN npm run build

# Stage 2: Build Backend
FROM python:3.11-slim AS backend-builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir pyinstaller

# Copy backend source
COPY backend/ ./backend/

# Compile Python to binary (protects source code)
RUN cd backend && python -m PyInstaller \
    --onefile \
    --name api \
    --add-data "logic:logic" \
    --add-data "config:config" \
    --hidden-import uvicorn \
    --hidden-import fastapi \
    --hidden-import pandas \
    --hidden-import openpyxl \
    api.py

# Stage 3: Production Image
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled backend binary
COPY --from=backend-builder /app/backend/dist/api /app/backend/api

# Copy built frontend
COPY --from=frontend-builder /app/dist /app/frontend

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Create startup script
RUN echo '#!/bin/bash\n\
nginx &\n\
cd /app/backend && ./api\n\
' > /app/start.sh && chmod +x /app/start.sh

# Expose ports
EXPOSE 8000 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Start services
CMD ["/app/start.sh"]
