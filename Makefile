.PHONY: dev backend frontend install build

# 同时启动 Django 后端 + Vite 前端（Ctrl+C 一起停止）
dev:
	@trap 'kill 0' SIGINT; \
	uv run python manage.py runserver & \
	cd frontend && npm run dev & \
	wait

backend:
	uv run python manage.py runserver

frontend:
	cd frontend && npm run dev

# 安装所有依赖
install:
	uv sync
	cd frontend && npm install

# 构建前端（生产模式）
build:
	cd frontend && npm run build
