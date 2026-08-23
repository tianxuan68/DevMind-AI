# internal_kb_qa（企业版知识库问答核心包）

本目录为「企业内部技术知识库智能问答系统」的核心实现目录，任务分工映射：

| 任务 | 目录/文件 |
|------|-----------|
| T1 文档采集/脱敏/FAQ | `data/`、`scripts/collect_docs.py`、`scripts/build_faq.py`、`scripts/desensitize.py` |
| T2 多格式文档解析 | `document_loaders/`，统一入口 `load(file_path) -> list[Document]` |
| T3 切分与向量化 | `text_splitters/`、`core/vector_store.py`、`scripts/ingest_documents.py` |
| T4 混合检索 | `core/hybrid_search.py`，接口 `search(query, top_k, filter)` |
| T5 FAQ 精确匹配 | `mysql_qa/` 与 `core/faq_matcher.py` |
| T6 意图分类 | `core/intent_classifier.py`，接口 `classify(query)` |
| T7 重排与生成 | `core/reranker.py`、`core/rag_generator.py`、`core/prompts.py` |
| T8 问答服务 API | `api/`、根目录 `app.py` |
| T10 评估 | `rag_assesment/`（`eval_set.json`、RAGAS 脚本） |
| T12 客户端后端 | 根目录 `backend/` |
| T13 检索策略 | `core/query_rewrite.py`、`core/search_strategy.py` |
| T14 通用日志/审计 | `core/audit_logger.py` |

权限/脱敏/审计是硬约束：检索过滤、敏感信息脱敏、审计留痕在实现中不可绕过。

## PDF OCR

PDF 加载器优先读取页面文本层。页面含图片且文本为空、有效字符过少或文本过短时，
会将页面渲染为 PNG，并通过阿里云 DashScope 的千问视觉模型识别文字；OCR 不可用时
记录警告并保留已有文本，不会使整个文档加载失败。

使用 OCR 前配置环境变量 `DASHSCOPE_API_KEY`，或者在项目根目录 `config.ini` 的 `[llm]`
段配置 `dashscope_api_key`。OCR 模型在同一段的 `ocr_model` 中配置，默认值为
`qwen-vl-plus`；也可以通过环境变量 `OCR_MODEL` 临时覆盖。OCR 结果的 `Document.metadata` 会标记
`extraction_method="llm_ocr"` 和 `ocr_used=True`；普通文本页面标记为
`extraction_method="text"` 和 `ocr_used=False`。

## 查看真实 OCR 结果

配置好 `DASHSCOPE_API_KEY` 后，可以使用普通脚本查看图片、PDF、Word、HTML 或 Markdown
的实际识别结果：

```powershell
uv run python -m scripts.qwen_ocr_demo "E:\path\to\scanned.pdf"
uv run python -m scripts.qwen_ocr_demo "E:\path\to\page.png"
uv run python -m scripts.qwen_ocr_demo "E:\path\to\guide.docx"
uv run python -m scripts.qwen_ocr_demo "E:\path\to\wiki.html"
uv run python -m scripts.qwen_ocr_demo "E:\path\to\guide.md"
```

脚本位置为 `scripts/qwen_ocr_demo.py`。图片会直接调用千问；文档会通过统一的
`load(file_path)` 入口处理，并打印页码、提取方式、OCR 标记和识别文本。
