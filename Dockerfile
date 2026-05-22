# Build frontend
FROM node:20-alpine AS frontend-builder
ARG CACHEBUST=1
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Build backend and serve
FROM python:3.11-slim
WORKDIR /app/backend

# Install dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./

# Copy built frontend from previous stage
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Copy examples directory
COPY examples/ /app/examples/

# Copy prompts directory
COPY prompts/ /app/prompts/

EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
