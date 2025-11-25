# 使用与 Cerebrium 配置相同的基础镜像
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

# 设置工作目录
WORKDIR /app

# 使用阿里云镜像源
RUN sed -i 's@//.*archive.ubuntu.com@//mirrors.aliyun.com@g' /etc/apt/sources.list && sed -i 's@//.*security.ubuntu.com@//mirrors.aliyun.com@g' /etc/apt/sources.list

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PYTHON_VERSION=3.12

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    software-properties-common \
    curl \
    git \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y \
    python${PYTHON_VERSION} \
    python${PYTHON_VERSION}-dev \
    python${PYTHON_VERSION}-distutils \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python${PYTHON_VERSION} \
    && ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python \
    && ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv 包管理器
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:${PATH}"

# pip 代理设置, 此设置需要先安装 pip
ENV GOPROXY https://goproxy.cn,direct
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
ENV UV_INDEX_URL https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目文件
COPY cerebrium.toml .
COPY main.py .
COPY requirements.txt* ./

# 如果没有 requirements.txt，创建一个
RUN if [ ! -f requirements.txt ]; then \
    echo "vllm" > requirements.txt && \
    echo "transformers" >> requirements.txt && \
    echo "pydantic" >> requirements.txt && \
    echo "fastapi" >> requirements.txt && \
    echo "uvicorn[standard]" >> requirements.txt; \
    fi

# 使用 uv 创建虚拟环境并安装依赖
RUN uv venv .venv && \
    . .venv/bin/activate && \
    uv pip install -r requirements.txt

# 创建日志目录
RUN mkdir -p /app/logs

# 暴露端口
EXPOSE 50010

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:50010/health || exit 1

# 启动命令（使用虚拟环境中的 Python）
CMD [".venv/bin/python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "50010"]