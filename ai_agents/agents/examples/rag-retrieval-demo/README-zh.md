# RAG 本地检索演示项目

## 项目概述

这是一个基于 TEN Framework 的简单 RAG（检索增强生成）本地检索插件演示项目。

## 功能特性

- 本地文档向量化存储
- 语义检索
- 与 LLM 集成
- 支持多种文档格式

## 项目结构

```
rag-retrieval-demo/
├── tenapp/                    # TEN 应用目录
│   ├── main.go               # Go 入口文件
│   ├── manifest.json         # 应用依赖清单
│   ├── property.json         # 应用配置
│   └── ten_packages/         # 扩展包目录
│       └── extension/
│           └── rag_retrieval_python/  # RAG 检索扩展
└── scripts/                  # 启动脚本
    ├── install.sh
    ├── start.sh
    └── stop.sh
```

## 快速开始

### 安装依赖

```bash
cd scripts
./install.sh
```

### 启动服务

```bash
./start.sh
```

### 停止服务

```bash
./stop.sh
```

## 配置说明

在 `tenapp/property.json` 中配置：

- `vector_db_path`: 向量数据库存储路径
- `embedding_model`: 嵌入模型名称
- `chunk_size`: 文档分块大小
- `top_k`: 检索返回的文档数量

## 扩展使用

RAG 检索扩展支持以下命令：

- `index_documents`: 索引文档
- `search`: 语义检索
- `clear_index`: 清空索引