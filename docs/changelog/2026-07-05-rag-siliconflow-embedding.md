# 2026-07-05 RAG Embedding 轻量化：SiliconFlow BGE

## 背景

原 RAG embedding 方案在容器内加载本地 `data/models/bge-small-zh-v1.5`，并依赖
`sentence-transformers` / `torch`。这会显著增加 Docker 镜像体积和构建时间，也让部署环境必须包含本地模型文件。

## 评估结论

改为 SiliconFlow 云端 BGE embedding 更适合当前部署目标：

- 不再在容器里安装 PyTorch。
- 不再挂载本地 BGE 模型目录。
- embedding 能力通过 HTTP API 提供，镜像更轻。
- Milvus Lite 继续作为本地向量库，已有检索、BM25、融合排序逻辑可以复用。
- 保留 `local` 后端作为手动回退路径，避免彻底删除本地模型能力。

权衡：

- 云端 embedding 需要 `HOMMEY_EMBEDDING_API_KEY` 或 `SILICONFLOW_API_KEY`。
- 首次 ingestion / query 需要访问 SiliconFlow 网络。
- 已用本地 embedding 生成的旧 Milvus 向量和新模型维度/分布不一致时，需要 rebuild 知识库。

## 改动

- 新增 `rag.embedder.SiliconFlowEmbedder`，调用 OpenAI-compatible `/embeddings` 接口。
- 新增 `create_text_embedder()`，通过 `HOMMEY_RAG_EMBEDDING_BACKEND` 选择：
  - `siliconflow`：默认，云端 BGE。
  - `local`：可选，惰性导入 `sentence-transformers`。
- `MilvusKnowledgeStore` 改为依赖 `TextEmbedder` 抽象，不再直接调用 `SentenceTransformer.encode()`。
- `settings.RAG_CONFIG` 新增：
  - `embedding_backend`
  - `embedding_api_key`
  - `embedding_base_url`
  - `embedding_dimension`
  - `embedding_batch_size`
  - `embedding_timeout_sec`
- Docker 镜像移除：
  - `torch` 预安装步骤
  - `sentence-transformers`
  - `libgomp1`
  - `data/models` 挂载
- README 和 `.env.example` 更新为 SiliconFlow 默认配置。
- readiness check 从“本地模型路径可读”改为：
  - `siliconflow`：检查 API key/base URL。
  - `local`：检查本地模型路径。

## 配置

默认云端配置：

```bash
HOMMEY_RAG_EMBEDDING_BACKEND=siliconflow
HOMMEY_EMBEDDING_MODEL=BAAI/bge-m3
HOMMEY_EMBEDDING_API_KEY=<siliconflow-api-key>
HOMMEY_EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
HOMMEY_EMBEDDING_DIMENSION=1024
HOMMEY_EMBEDDING_BATCH_SIZE=32
HOMMEY_EMBEDDING_TIMEOUT_SEC=30
```

本地模型回退：

```bash
HOMMEY_RAG_EMBEDDING_BACKEND=local
HOMMEY_EMBEDDING_MODEL=data/models/bge-small-zh-v1.5
```

本地回退需要自行安装：

```bash
python -m pip install sentence-transformers==5.2.3
```

## 部署注意

切换 embedding 模型或维度后，需要重建 RAG 知识库，否则旧向量库可能与新 embedding 不兼容：

```bash
python -m rag.ingestion --rebuild
```

如果没有现成 ingestion CLI，可通过现有 RAG pipeline 入口调用 `RAGPipeline().ingest(..., rebuild=True)`。

## 验证

- 新增 SiliconFlow embedder 单元测试，验证请求 URL、headers、payload、timeout 和响应维度。
- 更新 preflight 测试，验证云端 embedding 配置缺失时能给出组件化错误。
