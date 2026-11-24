# ============================================================
# Stage 1: 构建 Vue 3 前端静态产物
# ============================================================
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend-vue

COPY frontend-vue/package.json frontend-vue/package-lock.json* ./
RUN npm ci --registry=https://registry.npmmirror.com || npm install --registry=https://registry.npmmirror.com

COPY frontend-vue/ ./
RUN npm run build

# ============================================================
# Stage 2: FastAPI 后端 + 托管静态前端（支持 SQLite / MySQL）
# ============================================================
FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    -r ./backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend-vue/dist ./frontend-vue/dist

WORKDIR /app/backend
EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
