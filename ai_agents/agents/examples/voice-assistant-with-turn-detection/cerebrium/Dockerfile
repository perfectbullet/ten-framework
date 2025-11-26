# syntax=docker/dockerfile:1. 4
# 启用 BuildKit 语法以使用缓存挂载功能

# ============================================================================
# 阶段 1: 基础环境构建（包含 Python 和系统依赖）
# ============================================================================
FROM nvidia/cuda:12.1. 1-runtime-ubuntu22.04 AS base

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_DEFAULT_TIMEOUT=100
ENV PIP_RETRIES=5

# 配置阿里云镜像源（加速下载）
RUN sed -i 's@//.*archive.ubuntu.com@//mirrors.aliyun.com@g' /etc/apt/sources.list && \
    sed -i 's@//.*security.ubuntu.com@//mirrors.aliyun. com@g' /etc/apt/sources.list

# 安装系统依赖（这层会被缓存）
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    curl \
    git \
    ca-certificates \
    wget \
    build-essential \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-dev \
    python3. 12-venv \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3

# ============================================================================
# 阶段 2: Python 依赖安装（使用缓存挂载）
# ============================================================================
FROM base AS dependencies

WORKDIR /app

# 安装 pip（使用缓存）
RUN --mount=type=cache,target=/root/.cache/pip \
    python3. 12 -m ensurepip --upgrade && \
    python3.12 -m pip install --upgrade pip setuptools wheel

# 配置 pip 使用清华镜像源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.trusted-host pypi.tuna. tsinghua.edu.cn

# 创建虚拟环境
RUN python3.12 -m venv . venv

# 【关键优化】先复制 requirements.txt，利用 Docker 层缓存
# 只有当 requirements.txt 变化时，才会重新安装依赖
COPY requirements.txt .

# 升级虚拟环境中的 pip（使用缓存）
RUN --mount=type=cache,target=/root/.cache/pip \
    . venv/bin/pip install --upgrade pip setuptools wheel

# 【关键优化】分步安装依赖，每一步都使用缓存挂载
# 1. 安装基础依赖（变化频率低，优先安装）
RUN --mount=type=cache,target=/root/.cache/pip \
    .venv/bin/pip install \
    pydantic>=2.0.0 \
    fastapi>=0.110.0 \
    uvicorn[standard]>=0.29.0 \
    httpx>=0.27.0 \
    python-dotenv>=1.0.0

# 2. 安装 torch（大文件，单独一层便于缓存）
RUN --mount=type=cache,target=/root/.cache/pip \
    .venv/bin/pip install torch>=2.0.0

# 3. 安装 transformers
RUN --mount=type=cache,target=/root/.cache/pip \
    .venv/bin/pip install transformers>=4. 40.0

# 4. 安装 vLLM（最复杂的依赖，放在最后）
RUN --mount=type=cache,target=/root/.cache/pip \
    .venv/bin/pip install vllm>=0.5. 0

# ============================================================================
# 阶段 3: 最终运行镜像（只包含必要文件）
# ============================================================================
FROM base AS runtime

WORKDIR /app

# 从依赖阶段复制虚拟环境
COPY --from=dependencies /app/.venv /app/.venv

# 复制应用代码（放在最后，因为这部分变化最频繁）
COPY cerebrium.toml .
COPY main.py .

# 创建日志目录
RUN mkdir -p /app/logs

# 暴露端口
EXPOSE 50010

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:50010/health || exit 1

# 启动命令
CMD [". venv/bin/python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "50010"]