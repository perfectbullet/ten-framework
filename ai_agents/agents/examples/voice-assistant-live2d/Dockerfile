FROM ghcr.io/ten-framework/ten_agent_build:0.7.9 AS builder

ARG USE_AGENT=agents/examples/voice-assistant-live2d

WORKDIR /app

COPY .env.example .env
COPY server/ server/
COPY agents/scripts/ agents/scripts/
COPY agents/ten_packages/ agents/ten_packages/

# pip 代理设置, 此设置需要先安装 pip
ENV GOPROXY https://goproxy.cn,direct
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
ENV UV_INDEX_URL https://pypi.tuna.tsinghua.edu.cn/simple
# docker 代理
ENV http_proxy http://172.17.0.1:7890
ENV https_proxy http://172.17.0.1:7890
ENV all_proxy http://172.17.0.1:7891

RUN mkdir -p ~/.tman && \
    echo '{ \
  "registry": { \
    "default": { \
      "index": "https://registry-ten.rtcdeveloper.cn/api/ten-cloud-store/v1/packages" \
    } \
  } \
}' > ~/.tman/config.json


# Copy tenapp files explicitly to avoid symlink issues
COPY ${USE_AGENT}/tenapp/go.* ${USE_AGENT}/tenapp/
COPY ${USE_AGENT}/tenapp/main.go ${USE_AGENT}/tenapp/
COPY ${USE_AGENT}/tenapp/manifest* ${USE_AGENT}/tenapp/
COPY ${USE_AGENT}/tenapp/property.json ${USE_AGENT}/tenapp/
COPY ${USE_AGENT}/tenapp/scripts/ ${USE_AGENT}/tenapp/scripts/

# Copy extension directories that are actual directories (not symlinks)
COPY ${USE_AGENT}/tenapp/ten_packages/extension/main_python/ ${USE_AGENT}/tenapp/ten_packages/extension/main_python/

# Copy other example files
COPY ${USE_AGENT}/README.md ${USE_AGENT}/
COPY ${USE_AGENT}/Taskfile*.yml ${USE_AGENT}/
COPY ${USE_AGENT}/frontend/ ${USE_AGENT}/frontend/
RUN chmod +x /app/agents/scripts/*.sh
# 配置 npm 镜像源和网络参数
RUN npm config set registry https://registry.npmmirror.com && \
    npm config set fetch-retries 10 && \
    npm config set fetch-retry-mintimeout 20000 && \
    npm config set fetch-retry-maxtimeout 120000 && \
    npm config set fetch-timeout 600000 && \
    npm config set maxsockets 10 && \
    npm cache clean --force

# 安装依赖 - 带重试逻辑
RUN cd /app/${USE_AGENT} && \
    chmod +x tenapp/scripts/*.sh && \
    (task install || \
     (echo "First attempt failed, retrying..." && sleep 10 && task install) || \
     (echo "Second attempt failed, final retry..." && sleep 30 && task install))

RUN cd /app/${USE_AGENT} &&  task release

# Build frontend in builder stage (bun already done by task install)
WORKDIR /app/${USE_AGENT}/frontend
RUN NEXT_PUBLIC_EDIT_GRAPH_MODE=false bun run build
WORKDIR /app

FROM ubuntu:22.04

ARG USE_AGENT=agents/examples/voice-assistant-live2d
# docker 代理
ENV http_proxy http://172.17.0.1:7890
ENV https_proxy http://172.17.0.1:7890
ENV all_proxy http://172.17.0.1:7891

# pip 代理设置, 此设置需要先安装 pip
ENV GOPROXY https://goproxy.cn,direct

# 使用阿里云镜像源
RUN sed -i 's@//.*archive.ubuntu.com@//mirrors.aliyun.com@g' /etc/apt/sources.list && sed -i 's@//.*security.ubuntu.com@//mirrors.aliyun.com@g' /etc/apt/sources.list

RUN apt-get clean && apt-get update && apt-get install -y --no-install-recommends \
  libasound2 \
  libgstreamer1.0-dev \
  libunwind-dev \
  libc++1 \
  libssl-dev \
  python3 \
  python3-venv \
  python3-pip \
  python3-dev \
  jq vim \
  ca-certificates \
  curl \
  unzip \
  && apt-get clean && rm -rf /var/lib/apt/lists/* && rm -rf /tmp/*

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
ENV UV_INDEX_URL https://pypi.tuna.tsinghua.edu.cn/simple

# Install Node.js 20
# 使用阿里云镜像
# Install Node.js 20 from npmmirror
ARG NODE_VERSION=20.11.0
RUN apt-get update && apt-get install -y curl xz-utils \
  && curl -fsSLO https://npmmirror.com/mirrors/node/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz \
  && tar -xJf node-v${NODE_VERSION}-linux-x64.tar.xz -C /usr/local --strip-components=1 \
  && rm node-v${NODE_VERSION}-linux-x64.tar.xz \
  && rm -rf /var/lib/apt/lists/* \
  && node --version \
  && npm --version

# Install Bun using the official install script
RUN curl -fsSL https://bun.com/install | bash
# Add Bun to the PATH (if not already added by the install script)
ENV PATH="/root/.bun/bin:$PATH"

# Install Task
RUN sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d -b /usr/local/bin

WORKDIR /app

COPY --from=builder /app/${USE_AGENT}/tenapp/.release/ /app/agents/
COPY --from=builder /app/server/bin/api /app/server/bin/api
COPY --from=builder /usr/local/lib /usr/local/lib
COPY --from=builder /usr/lib/python3 /usr/lib/python3
COPY --from=builder /usr/local/bin/tman /usr/local/bin/tman

# Copy built frontend from builder stage
COPY --from=builder /app/${USE_AGENT}/frontend/ /app/frontend/

# Copy Docker Taskfile
COPY --from=builder /app/${USE_AGENT}/Taskfile.docker.yml /app/Taskfile.docker.yml

EXPOSE 8080 3000

ENTRYPOINT ["task", "-t", "Taskfile.docker.yml", "run-prod"]
