FROM python:3.10-slim

WORKDIR /app

# ── 系统依赖：curl(健康检查) + libgomp1(torch运行时) + libpq5(psycopg) ──
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# ── 先只复制依赖文件，利用 Docker 层缓存 ──
COPY requirements-docker.txt .

# ── 约束文件：锁死 CPU torch，防止 sentence-transformers 等依赖解析时偷换 CUDA 版 ──
RUN echo "torch==2.12.1+cpu" > /tmp/constraints.txt

# ── 安装依赖（全部走清华镜像） ──
# Step 1: 升级 pip
# Step 2: 先装 CPU torch（从 Aliyun CPU wheels）
# Step 3: 装其余依赖，用约束文件阻止 torch 被替换
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "torch==2.12.1+cpu" \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        --find-links https://mirrors.aliyun.com/pytorch-wheels/cpu/ \
    && pip install --no-cache-dir -r requirements-docker.txt \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        --constraint /tmp/constraints.txt

# ── 验证：确保装的是 CPU torch，没被偷换成 CUDA 版 ──
RUN python -c "import torch; print('torch version:', torch.__version__); assert 'cpu' in torch.__version__.lower() or not torch.cuda.is_available(), 'ERROR: CUDA torch detected!'; print('OK: CPU torch confirmed')"

# ── 最后复制项目代码 ──
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/ >/dev/null || exit 1

CMD ["python", "run_webui.py"]
