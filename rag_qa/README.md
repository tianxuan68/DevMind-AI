# rag_qa（黑马课程问答系统 RAG 基线目录）

本目录用于承载/复用参考项目 `E:\study_project\Itcast_qa_system\rag_qa` 的基线能力：

- `edu_document_loaders/`：T2 复用的文档解析 loader
- `edu_text_spliter/`：T3 切分逻辑
- `core/vector_store.py`：T3/T4 Milvus 向量库参考
- `core/bert_query_classifier/`：T6 意图分类器参考
- `models/`：BGE-M3、bge-reranker-v2-m3、文档语义分段模型
- `rag_assesment/`：T10 RAGAS 评估流程

> 新企业版代码请优先实现到 `internal_kb_qa/`；模型权重等大文件不提交 Git。
