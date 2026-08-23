import React, { useRef, useState } from "react";
import { Upload, X } from "lucide-react";
import { knowledgeApi } from "../api/qa";

export default function UploadModal({ open, kbId, onClose, onDone }) {
  const inputRef = useRef(null);
  const [queue, setQueue] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);

  if (!open) return null;

  function addFiles(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setQueue((prev) => [
      ...prev,
      ...files.map((file) => ({ id: `${file.name}-${file.size}-${Date.now()}`, file, progress: 0, status: "pending", error: "" })),
    ]);
  }

  async function startUpload() {
    if (!kbId || !queue.length || uploading) return;
    setUploading(true);
    let hasError = false;
    for (const item of queue) {
      if (item.status === "done") continue;
      setQueue((prev) => prev.map((row) => (row.id === item.id ? { ...row, status: "uploading", progress: 0 } : row)));
      try {
        await knowledgeApi.uploadDoc(kbId, item.file, (progress) => {
          setQueue((prev) => prev.map((row) => (row.id === item.id ? { ...row, progress } : row)));
        });
        setQueue((prev) => prev.map((row) => (row.id === item.id ? { ...row, status: "done", progress: 100 } : row)));
      } catch (error) {
        hasError = true;
        setQueue((prev) => prev.map((row) => (row.id === item.id ? { ...row, status: "error", error: error.message } : row)));
      }
    }
    setUploading(false);
    if (!hasError) {
      onDone?.();
      setQueue([]);
      onClose?.();
    }
  }

  function handleClose() {
    if (uploading) return;
    setQueue([]);
    onClose?.();
  }

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
          <p>拖拽文件到此处，或 <span>点击上传</span></p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".pdf,.md,.doc,.docx,.txt"
            hidden
            onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
          />
        </div>
        <p className="upload-modal-hint">支持 PDF、Markdown、Word、TXT，单次可多选上传</p>

        {queue.length > 0 && (
          <ul className="upload-file-list">
            {queue.map((item) => (
              <li key={item.id}>
                <div className="upload-file-row">
                  <span className="upload-file-name">{item.file.name}</span>
                  <span className="upload-file-status">
                    {item.status === "done" ? "完成" : item.status === "error" ? "失败" : `${item.progress}%`}
                  </span>
                </div>
                <div className="upload-progress-track">
                  <i style={{ width: `${item.progress}%` }} />
                </div>
                {item.error ? <small className="upload-file-error">{item.error}</small> : null}
              </li>
            ))}
          </ul>
        )}

        <footer className="upload-modal-actions">
          <button type="button" onClick={handleClose} disabled={uploading}>取消</button>
          <button type="button" className="feature-primary" disabled={!queue.length || uploading} onClick={startUpload}>
            {uploading ? "上传中…" : "开始上传"}
          </button>
        </footer>
      </div>
    </div>
  );
}
