import React, { useEffect, useRef, useState } from "react";
import { Upload, X } from "lucide-react";
import { bootstrapApi, knowledgeApi, uploadToPresignedUrl } from "../api/qa";

function statusLabel(item, uploading) {
  if (item.status === "error") return "失败";
  if (item.status === "indexing") return "索引中…";
  if (item.status === "done") return "完成";
  if (item.status === "uploading") return uploading ? `上传中 ${item.progress}%` : "上传中…";
  return "待上传";
}

export default function UploadModal({ open, kbId, onClose, onDone }) {
  const inputRef = useRef(null);
  const [queue, setQueue] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [ossEnabled, setOssEnabled] = useState(false);

  useEffect(() => {
    if (!open) return;
    bootstrapApi.get()
      .then((data) => setOssEnabled(Boolean(data?.features?.ossUpload)))
      .catch(() => setOssEnabled(false));
  }, [open]);

  if (!open) return null;

  function addFiles(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setQueue((prev) => [
      ...prev,
      ...files.map((file) => ({
        id: `${file.name}-${file.size}-${Date.now()}-${Math.random()}`,
        file,
        progress: 0,
        status: "pending",
        error: "",
      })),
    ]);
  }

  async function uploadViaOss(item) {
    const init = await knowledgeApi.initOssUpload({
      knowledge_base_id: Number(kbId),
      file_name: item.file.name,
      file_size: item.file.size,
    });
    try {
      await uploadToPresignedUrl(init.uploadUrl, item.file, {
        headers: init.headers,
        onProgress: (progress) => {
          setQueue((prev) => prev.map((row) => (row.id === item.id ? { ...row, progress } : row)));
        },
      });
      await knowledgeApi.completeOssUpload(init.docId);
    } catch (error) {
      if (init.docId) {
        await knowledgeApi.deleteDoc(init.docId).catch(() => {});
      }
      throw error;
    }
  }

  async function uploadOneFile(item) {
    if (ossEnabled) {
      try {
        await uploadViaOss(item);
        return;
      } catch (error) {
        const canFallback = /OSS|CORS|网络|上传失败|超时/.test(error?.message || "");
        if (!canFallback) throw error;
      }
    }

    await knowledgeApi.uploadDoc(kbId, item.file, (progress) => {
      setQueue((prev) => prev.map((row) => (row.id === item.id ? { ...row, progress } : row)));
    });
  }

  async function startUpload() {
    if (!kbId) {
      alert("请先选择知识库");
      return;
    }
    if (!queue.length || uploading) return;

    setUploading(true);
    let hasError = false;

    for (const item of queue) {
      if (item.status === "done") continue;
      setQueue((prev) => prev.map((row) => (row.id === item.id ? { ...row, status: "uploading", progress: 1 } : row)));
      try {
        await uploadOneFile(item);
        setQueue((prev) => prev.map((row) => (row.id === item.id ? { ...row, status: "indexing", progress: 100 } : row)));
      } catch (error) {
        hasError = true;
        setQueue((prev) => prev.map((row) => (row.id === item.id ? { ...row, status: "error", error: error.message } : row)));
      }
    }

    setUploading(false);

    if (!hasError) {
      setQueue([]);
      onClose?.();
      onDone?.();
    }
  }

  function handleClose() {
    if (uploading) return;
    setQueue([]);
    onClose?.();
  }

  const pendingCount = queue.filter((item) => item.status === "pending").length;

  return (
    <div className="admin-modal" onClick={handleClose}>
      <div className="upload-modal-box" onClick={(e) => e.stopPropagation()}>
        <header className="upload-modal-head">
          <h3>上传文档</h3>
          <button type="button" className="sidebar-icon-btn" onClick={handleClose} aria-label="关闭"><X size={18} /></button>
        </header>

        <div
          className={`upload-dropzone ${dragOver ? "drag-over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files); }}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter") inputRef.current?.click(); }}
        >
          <Upload size={28} />
          <p>拖拽文件到此处，或 <span>点击选择</span></p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.md,.docx,.txt"
            hidden
            onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
          />
        </div>
        <p className="upload-modal-hint">
          支持 PDF、Markdown、Word(.docx)、TXT。
          {ossEnabled
            ? " 已启用阿里云 OSS 直传；若直传失败将自动回退本地上传。"
            : " 选择文件后请点击「开始上传」，后台将自动切块并向量化。"}
        </p>

        {queue.length > 0 && (
          <ul className="upload-file-list">
            {queue.map((item) => (
              <li key={item.id}>
                <div className="upload-file-row">
                  <span className="upload-file-name">{item.file.name}</span>
                  <span className="upload-file-status">{statusLabel(item, uploading)}</span>
                </div>
                <div className="upload-progress-track">
                  <i style={{ width: `${item.status === "pending" ? 0 : item.progress}%` }} />
                </div>
                {item.error ? <small className="upload-file-error">{item.error}</small> : null}
              </li>
            ))}
          </ul>
        )}

        <footer className="upload-modal-actions">
          <button type="button" onClick={handleClose} disabled={uploading}>取消</button>
          <button
            type="button"
            className="feature-primary"
            disabled={!queue.length || uploading || !kbId}
            onClick={startUpload}
          >
            {uploading ? "上传中…" : pendingCount ? `开始上传（${pendingCount}）` : "开始上传"}
          </button>
        </footer>
      </div>
    </div>
  );
}
