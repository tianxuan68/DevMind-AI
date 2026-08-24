import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Eye, FileText, Layers, Search } from "lucide-react";
import { knowledgeApi } from "../api/qa";

const PAGE_SIZE = 15;
const PREVIEW_LEN = 160;

function formatPreview(text, max = PREVIEW_LEN) {
  if (!text) return "（空内容）";
  const value = text
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
  if (!value) return "（空内容）";
  if (value.length <= max) return value;
  return `${value.slice(0, max)}…`;
}

function formatParentLabel(parentId) {
  const match = String(parentId || "").match(/_parent_(\d+)$/);
  if (match) return `父块 ${Number(match[1]) + 1}`;
  return parentId || "—";
}

function shortenId(id, max = 18) {
  const value = String(id || "");
  if (value.length <= max) return value;
  return `${value.slice(0, max)}…`;
}

function AdminPageShell({ title, desc, children, className = "" }) {
  return (
    <section className={`admin-page ${className}`.trim()}>
      <header className="admin-page-header">
        <div className="admin-page-intro">
          <h1>{title}</h1>
          <p>{desc}</p>
        </div>
      </header>
      {children}
    </section>
  );
}

function TablePagination({ page, totalPages, total, onChange }) {
  return (
    <div className="kb-table-footer">
      <span className="kb-table-total">共 {total} 条</span>
      {totalPages > 1 ? (
        <div className="pagination">
          <button type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}>上一页</button>
          <span>{page} / {totalPages}</span>
          <button type="button" disabled={page >= totalPages} onClick={() => onChange(page + 1)}>下一页</button>
        </div>
      ) : null}
    </div>
  );
}

function truncateText(text, max = PREVIEW_LEN) {
  return formatPreview(text, max);
}

function ChunkDetailModal({ item, onClose }) {
  if (!item) return null;

  return (
    <div className="admin-modal" onClick={onClose}>
      <div className="admin-modal-box chunk-detail-modal" onClick={(e) => e.stopPropagation()}>
        <h3>父块 {item.index}/{item.total}</h3>
        <div className="chunk-detail-meta">
          <code>{item.parentId}</code>
          <span>{item.chunks.length} 个子块</span>
        </div>
        {item.parentContent ? (
          <details className="chunk-parent-preview" open>
            <summary>父块完整上下文</summary>
            <pre className="chunk-parent-full">{item.parentContent}</pre>
          </details>
        ) : null}
        <div className="admin-table-wrap flat kb-table-wrap chunk-modal-table-wrap">
          <table className="admin-table kb-table chunk-table chunk-table-modal">
            <thead>
              <tr>
                <th>内容摘要</th>
              </tr>
            </thead>
            <tbody>
              {item.chunks.map((chunk, childIndex) => (
                <tr key={chunk.id || `${item.parentId}-${childIndex}`}>
                  <td className="chunk-text-cell">{truncateText(chunk.text)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="admin-modal-actions">
          <button type="button" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  );
}

export default function ChunkViewer({ initialKbId = "", initialDocId = "" }) {
  const [kbs, setKbs] = useState([]);
  const [docs, setDocs] = useState([]);
  const [selectedKbId, setSelectedKbId] = useState(initialKbId || "");
  const [selectedDocId, setSelectedDocId] = useState(initialDocId || "");
  const [docQuery, setDocQuery] = useState("");
  const [chunkQuery, setChunkQuery] = useState("");
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [loadingChunks, setLoadingChunks] = useState(false);
  const [chunkData, setChunkData] = useState(null);
  const [message, setMessage] = useState("");
  const [page, setPage] = useState(1);
  const [detailItem, setDetailItem] = useState(null);

  const loadBases = useCallback(async () => {
    const data = await knowledgeApi.listBases();
    const items = data.items || [];
    setKbs(items);
    return items;
  }, []);

  const loadDocs = useCallback(async (kbId) => {
    if (!kbId) {
      setDocs([]);
      return [];
    }
    const data = await knowledgeApi.listDocs({ knowledge_base_id: kbId, page_size: 100 });
    const items = data.items || [];
    setDocs(items);
    return items;
  }, []);

  const loadChunks = useCallback(async (docId) => {
    if (!docId) {
      setChunkData(null);
      return;
    }
    setLoadingChunks(true);
    setMessage("");
    try {
      const data = await knowledgeApi.listChunks(docId);
      setChunkData(data);
      setPage(1);
    } catch (error) {
      setChunkData(null);
      setMessage(error.message);
    } finally {
      setLoadingChunks(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!initialKbId) {
        setKbs([]);
        setDocs([]);
        setSelectedKbId("");
        setSelectedDocId("");
        setChunkData(null);
        setLoadingDocs(false);
        return;
      }

      setLoadingDocs(true);
      setMessage("");
      try {
        const items = await loadBases();
        if (cancelled) return;
        setSelectedKbId(initialKbId);
        const docItems = await loadDocs(initialKbId);
        if (cancelled) return;
        const docId = initialDocId || docItems[0]?.id || "";
        setSelectedDocId(docId);
        if (docId) await loadChunks(docId);
        else setChunkData(null);
      } catch (error) {
        if (!cancelled) setMessage(error.message);
      } finally {
        if (!cancelled) setLoadingDocs(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [initialKbId, initialDocId, loadBases, loadDocs, loadChunks]);

  async function handleSelectDoc(docId) {
    setSelectedDocId(docId);
    setChunkQuery("");
    await loadChunks(docId);
  }

  const filteredDocs = useMemo(() => {
    const q = docQuery.trim().toLowerCase();
    if (!q) return docs;
    return docs.filter((doc) => doc.name.toLowerCase().includes(q));
  }, [docs, docQuery]);

  const filteredParents = useMemo(() => {
    if (!chunkData?.parents) return [];
    const q = chunkQuery.trim().toLowerCase();
    if (!q) return chunkData.parents;
    return chunkData.parents
      .map((parent) => ({
        ...parent,
        chunks: parent.chunks.filter(
          (chunk) =>
            (chunk.text || "").toLowerCase().includes(q) ||
            (chunk.id || "").toLowerCase().includes(q) ||
            (parent.parentId || "").toLowerCase().includes(q),
        ),
      }))
      .filter((parent) => parent.chunks.length > 0 || (parent.parentContent || "").toLowerCase().includes(q));
  }, [chunkData, chunkQuery]);

  const totalRows = filteredParents.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / PAGE_SIZE));
  const pageRows = filteredParents.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const selectedKb = kbs.find((kb) => kb.id === selectedKbId);
  const selectedDoc = docs.find((doc) => doc.id === selectedDocId);

  function openParentDetail(group, index) {
    setDetailItem({
      ...group,
      index: (page - 1) * PAGE_SIZE + index + 1,
      total: filteredParents.length,
    });
  }

  return (
    <AdminPageShell
      title="切块浏览"
      desc="Milvus 存子块用于向量检索；父块是更大上下文。按父块分组展示，点击操作可查看子块详情。"
      className="chunk-page-shell kb-page-shell"
    >
      {message ? <p className="kb-page-message">{message}</p> : null}
      <div className="kb-workspace chunk-workspace">
        <aside className="kb-side admin-card chunk-side">
          <header className="chunk-side-head">
            <h2><Layers size={17} /> 文档选择</h2>
            {selectedKb ? <p className="kb-side-note">{selectedKb.name}</p> : null}
          </header>

          {!initialKbId ? (
            <p className="chunk-empty">请从知识库管理页点击「查看切块」进入</p>
          ) : (
            <>
              <div className="kb-search chunk-doc-search">
                <Search size={16} />
                <input
                  value={docQuery}
                  onChange={(e) => setDocQuery(e.target.value)}
                  placeholder="筛选文档名称…"
                  aria-label="筛选文档"
                />
              </div>

              <div className="chunk-doc-list">
                {loadingDocs ? (
                  <p className="chunk-empty">加载文档…</p>
                ) : filteredDocs.length ? filteredDocs.map((doc) => (
                  <button
                    key={doc.id}
                    type="button"
                    className={`chunk-doc-item${selectedDocId === doc.id ? " active" : ""}`}
                    onClick={() => handleSelectDoc(doc.id)}
                  >
                    <FileText size={15} />
                    <div>
                      <strong>{doc.name}</strong>
                      <span>{doc.chunkCount ?? 0} 子块 · {doc.status}</span>
                    </div>
                  </button>
                )) : (
                  <p className="chunk-empty">该知识库暂无文档</p>
                )}
              </div>
            </>
          )}
        </aside>

        <section className="kb-main admin-card chunk-main">
          <header className="kb-main-head">
            <div className="kb-main-title">
              <h2>{selectedDoc?.name || "请选择文档"}</h2>
              <span className="kb-doc-count">
                {selectedKb?.name || "—"}
                {chunkData ? ` · ${chunkData.milvusCount} 子块 / ${chunkData.parentCount} 父块` : ""}
                {chunkQuery ? ` · 命中 ${filteredParents.length} 父块` : ""}
              </span>
            </div>
            <div className="kb-toolbar">
              <div className="kb-search">
                <Search size={16} />
                <input
                  value={chunkQuery}
                  onChange={(e) => { setChunkQuery(e.target.value); setPage(1); }}
                  placeholder="搜索父块或子块内容…"
                  aria-label="搜索切块"
                />
              </div>
            </div>
          </header>

          {loadingChunks ? (
            <div className="admin-table-wrap flat kb-table-wrap">
              <table className="admin-table kb-table chunk-table">
                <tbody>
                  <tr><td className="empty-cell">正在从 Milvus 加载切块…</td></tr>
                </tbody>
              </table>
            </div>
          ) : !chunkData ? (
            <div className="admin-table-wrap flat kb-table-wrap">
              <table className="admin-table kb-table chunk-table">
                <tbody>
                  <tr><td className="empty-cell">选择左侧文档以查看切块</td></tr>
                </tbody>
              </table>
            </div>
          ) : chunkData.milvusCount === 0 ? (
            <div className="chunk-empty-panel">
              <p>未在 Milvus 中找到该文档的切块。</p>
              <small>请确认已执行 ingest，且文档路径与入库时一致。</small>
              <code>{chunkData.storagePath}</code>
            </div>
          ) : totalRows === 0 ? (
            <div className="admin-table-wrap flat kb-table-wrap">
              <table className="admin-table kb-table chunk-table">
                <tbody>
                  <tr><td className="empty-cell">没有匹配的切块</td></tr>
                </tbody>
              </table>
            </div>
          ) : (
            <>
              <div className="admin-table-wrap flat kb-table-wrap">
                <table className="admin-table kb-table chunk-table chunk-table-grouped">
                  <thead>
                    <tr>
                      <th className="chunk-col-parent">父块</th>
                      <th className="chunk-col-preview">内容预览</th>
                      <th className="chunk-col-action">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageRows.map((group, index) => {
                      const previewSource = group.parentContent || group.chunks.map((c) => c.text).join(" ");
                      return (
                        <tr key={group.parentId}>
                          <td className="chunk-col-parent">
                            <span className="chunk-parent-label">{formatParentLabel(group.parentId)}</span>
                            <code className="chunk-id-cell" title={group.parentId}>{shortenId(group.parentId)}</code>
                          </td>
                          <td className="chunk-preview-cell">
                            <p className="chunk-preview-text chunk-preview-ellipsis" title={formatPreview(previewSource, 500)}>
                              {formatPreview(previewSource, 80)}
                            </p>
                          </td>
                          <td className="row-actions chunk-col-action">
                            <button type="button" onClick={() => openParentDetail(group, index)} aria-label="查看子块" title="查看子块">
                              <Eye size={15} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <TablePagination page={page} totalPages={totalPages} total={totalRows} onChange={setPage} />
            </>
          )}
        </section>
      </div>

      <ChunkDetailModal item={detailItem} onClose={() => setDetailItem(null)} />
    </AdminPageShell>
  );
}
