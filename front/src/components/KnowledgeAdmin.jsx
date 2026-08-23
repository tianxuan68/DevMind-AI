import React, { useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Search, Trash2, Upload } from "lucide-react";
import { knowledgeApi } from "../api/qa";
import UploadModal from "./UploadModal";

function GlassButton({ className = "", children, ...props }) {
  return <button className={`glass-button ${className}`} {...props}>{children}</button>;
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

export default function KnowledgeAdmin() {
  const [kbs, setKbs] = useState([]);
  const [docs, setDocs] = useState([]);
  const [selectedKbId, setSelectedKbId] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [docForm, setDocForm] = useState(null);
  const [kbForm, setKbForm] = useState(null);
  const [uploadOpen, setUploadOpen] = useState(false);

  const selectedKb = kbs.find((kb) => kb.id === selectedKbId) || kbs[0];

  const loadBases = useCallback(async () => {
    const data = await knowledgeApi.listBases();
    const items = data.items || [];
    setKbs(items);
    setSelectedKbId((prev) => prev || items[0]?.id || "");
    return items;
  }, []);

  const loadDocs = useCallback(async (kbId, keyword = "") => {
    if (!kbId) {
      setDocs([]);
      return;
    }
    const data = await knowledgeApi.listDocs({
      knowledge_base_id: kbId,
      keyword: keyword.trim() || undefined,
      page_size: 100,
    });
    setDocs(data.items || []);
  }, []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setMessage("");
      try {
        const items = await loadBases();
        if (items[0]?.id) await loadDocs(items[0].id);
      } catch (error) {
        setMessage(error.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [loadBases, loadDocs]);

  useEffect(() => {
    if (!selectedKb?.id) return;
    const timer = setTimeout(() => {
      loadDocs(selectedKb.id, query).catch((error) => setMessage(error.message));
    }, query ? 300 : 0);
    return () => clearTimeout(timer);
  }, [selectedKb?.id, query, loadDocs]);

  async function saveKb() {
    if (!kbForm?.name?.trim()) return;
    try {
      if (kbForm.id) {
        await knowledgeApi.updateBase(kbForm.id, {
          name: kbForm.name.trim(),
          description: kbForm.description?.trim() || null,
          owner_team: kbForm.owner?.trim() || null,
        });
      } else {
        await knowledgeApi.createBase({
          name: kbForm.name.trim(),
          description: kbForm.description?.trim() || null,
          owner_team: kbForm.owner?.trim() || null,
        });
      }
      setKbForm(null);
      await loadBases();
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function deleteKb(id) {
    try {
      await knowledgeApi.deleteBase(id);
      const items = await loadBases();
      const nextId = items[0]?.id || "";
      setSelectedKbId(nextId);
      if (nextId) await loadDocs(nextId);
      else setDocs([]);
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function saveDoc() {
    if (!docForm?.name?.trim()) return;
    try {
      await knowledgeApi.updateDoc(docForm.id, { file_name: docForm.name.trim() });
      setDocForm(null);
      await loadDocs(selectedKb.id, query);
      await loadBases();
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function deleteDoc(id) {
    try {
      await knowledgeApi.deleteDoc(id);
      await loadDocs(selectedKb.id, query);
      await loadBases();
    } catch (error) {
      setMessage(error.message);
    }
  }

  return (
    <AdminPageShell
      title="知识库管理"
      desc="按知识库上传与管理文档，支持检索、编辑元信息与删除。上传后自动进入切片与索引流程。"
      className="kb-page-shell"
    >
      {message ? <p className="kb-page-message">{message}</p> : null}
      <div className="kb-workspace">
        <aside className="kb-side admin-card">
          <div className="kb-side-head-row">
            <h2>知识库</h2>
            <button type="button" className="kb-add-btn" onClick={() => setKbForm({ name: "", description: "", owner: "" })} aria-label="新建知识库">
              <Plus size={16} />
            </button>
          </div>
          <p className="kb-side-note">选择目标知识库后上传或管理文档。</p>
          <div className="kb-list">
            {kbs.map((kb) => (
              <div key={kb.id} className={`kb-list-item-wrap ${selectedKb?.id === kb.id ? "active" : ""}`}>
                <button
                  type="button"
                  className="kb-list-item"
                  onClick={() => { setSelectedKbId(kb.id); setQuery(""); }}
                >
                  <span className="kb-list-name">{kb.name}</span>
                  <span className="kb-list-meta">{kb.docCount} 篇 · {kb.owner}</span>
                </button>
                <div className="kb-list-actions">
                  <button type="button" onClick={() => setKbForm({ id: kb.id, name: kb.name, description: kb.description, owner: kb.owner })} aria-label="编辑"><Pencil size={14} /></button>
                  <button type="button" onClick={() => deleteKb(kb.id)} aria-label="删除"><Trash2 size={14} /></button>
                </div>
              </div>
            ))}
          </div>
        </aside>

        <section className="kb-main admin-card">
          <header className="kb-main-head">
            <div>
              <h2>{selectedKb?.name || "请选择知识库"}</h2>
              <p>共 {docs.length} 篇文档{query ? "（已筛选）" : ""}</p>
            </div>
            <div className="kb-toolbar">
              <div className="kb-search">
                <Search size={16} />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索文档名称或上传人…"
                  aria-label="搜索文档"
                />
              </div>
              <GlassButton className="feature-primary" disabled={!selectedKb?.id} onClick={() => setUploadOpen(true)}>
                <Upload size={17} /> 上传文档
              </GlassButton>
            </div>
          </header>

          <div className="admin-table-wrap flat kb-table-wrap">
            <table className="admin-table kb-table">
              <thead>
                <tr>
                  <th>文档名称</th>
                  <th>类型</th>
                  <th>大小</th>
                  <th>状态</th>
                  <th>上传人</th>
                  <th>更新时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={7} className="empty-cell">加载中…</td></tr>
                ) : docs.length ? docs.map((doc) => (
                  <tr key={doc.id}>
                    <td>
                      <div className="doc-name-cell">
                        <span className={`file-icon ${doc.type.toLowerCase()}`}>{doc.type}</span>
                        <strong>{doc.name}</strong>
                      </div>
                    </td>
                    <td>{doc.type}</td>
                    <td>{doc.size}</td>
                    <td>
                      <span className={`doc-status ${doc.status === "已索引" ? "is-indexed" : doc.status === "处理中" ? "is-pending" : ""}`}>
                        {doc.status}
                      </span>
                    </td>
                    <td>{doc.uploader}</td>
                    <td>{doc.updatedAt}</td>
                    <td className="row-actions">
                      <button type="button" onClick={() => setDocForm({ id: doc.id, name: doc.name })} aria-label="编辑"><Pencil size={15} /></button>
                      <button type="button" onClick={() => deleteDoc(doc.id)} aria-label="删除"><Trash2 size={15} /></button>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={7} className="empty-cell">
                      {query ? "未找到匹配的文档" : "暂无文档，点击「上传文档」添加"}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <UploadModal
        open={uploadOpen}
        kbId={selectedKb?.id}
        onClose={() => setUploadOpen(false)}
        onDone={async () => {
          await loadDocs(selectedKb.id, query);
          await loadBases();
        }}
      />

      {docForm && (
        <div className="admin-modal">
          <div className="admin-modal-box">
            <h3>编辑文档</h3>
            <label>文档名称<input value={docForm.name} onChange={(e) => setDocForm({ ...docForm, name: e.target.value })} /></label>
            <div className="admin-modal-actions">
              <button type="button" onClick={() => setDocForm(null)}>取消</button>
              <GlassButton className="feature-primary" onClick={saveDoc}>保存</GlassButton>
            </div>
          </div>
        </div>
      )}

      {kbForm && (
        <div className="admin-modal">
          <div className="admin-modal-box">
            <h3>{kbForm.id ? "编辑知识库" : "新建知识库"}</h3>
            <label>名称<input value={kbForm.name} onChange={(e) => setKbForm({ ...kbForm, name: e.target.value })} /></label>
            <label>描述<input value={kbForm.description || ""} onChange={(e) => setKbForm({ ...kbForm, description: e.target.value })} /></label>
            <label>负责团队<input value={kbForm.owner || ""} onChange={(e) => setKbForm({ ...kbForm, owner: e.target.value })} /></label>
            <div className="admin-modal-actions">
              <button type="button" onClick={() => setKbForm(null)}>取消</button>
              <GlassButton className="feature-primary" onClick={saveKb}>保存</GlassButton>
            </div>
          </div>
        </div>
      )}
    </AdminPageShell>
  );
}
