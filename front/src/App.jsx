import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight, ArrowUp, Bell, BookOpen, Bot, Building2, ChevronDown,
  Clipboard, Copy, FileText, KeyRound,
  Library, LogOut, MessageCircle, MessageSquare, PanelLeftClose, PanelRight, Pencil, Plus,
  Search, Settings, ShieldCheck, SquarePen, User,
  Wrench, X, ChevronRight,
} from "lucide-react";
import "./styles.css";
import KnowledgeAdmin from "./components/KnowledgeAdmin";
import ChunkViewer from "./components/ChunkViewer";
import SelectField from "./components/SelectField";
import LoginPage from "./components/LoginPage";
import LegalPage from "./components/LegalPage";
import {
  authApi, clearAuth, faqApi, getStoredUser, getToken, knowledgeApi, setUnauthorizedHandler,
} from "./api/qa";

const FEEDBACK_TYPE_OPTIONS = [
  { value: "issue", label: "问题反馈" },
  { value: "feature", label: "功能建议" },
  { value: "other", label: "其他" },
];

const RETRIEVAL_TOP_K_OPTIONS = [
  { value: 3, label: "3" },
  { value: 5, label: "5" },
  { value: 10, label: "10" },
  { value: 20, label: "20" },
];

const RETRIEVAL_RERANK_OPTIONS = [
  { value: "bge-reranker-v2-m3", label: "bge-reranker-v2-m3" },
  { value: "none", label: "不重排" },
];

const RETRIEVAL_MODE_OPTIONS = [
  { value: "hybrid", label: "混合检索" },
  { value: "dense", label: "稠密向量" },
  { value: "sparse", label: "稀疏向量" },
];

const INITIAL_HISTORY = [];

const QUICK_ACTIONS = [
  [MessageCircle, "技术问题", "解答架构、原理与实现等技术问题"],
  [Wrench, "问题排查", "协助定位与分析系统或业务问题"],
  [Clipboard, "文档总结", "提炼文档要点，生成结构化摘要"],
];

function buildWorkspaceUser(apiUser) {
  if (!apiUser) return null;
  const name = apiUser.nickname || apiUser.username || "用户";
  return {
    displayName: name,
    nickname: name,
    avatar: name.slice(0, 1),
    username: apiUser.username || "—",
    phone: apiUser.phone || "—",
    team: apiUser.team || "—",
    department: apiUser.team || "—",
    securityLevel: apiUser.security_level || "team",
    createdAt: apiUser.created_at || "—",
    loginMethod: "账号密码 / 短信验证码",
    status: "正常",
  };
}

function maskPhone(phone) {
  if (!phone || phone.length < 7) return phone;
  return `${phone.slice(0, 3)} **** ${phone.slice(-4)}`;
}

function Logo({ compact = false }) {
  return (
    <div className={`logo ${compact ? "compact" : ""}`} aria-label="DevMind AI">
      <svg viewBox="0 0 64 56" aria-hidden="true">
        <path d="M32 8 13 43M32 8l19 35M13 43h38" />
        <circle cx="32" cy="8" r="7" />
        <circle cx="13" cy="43" r="6" />
        <circle cx="51" cy="43" r="6" />
        <circle className="logo-dot" cx="32" cy="8" r="2.5" />
      </svg>
      <span>DevMind <b>AI</b><small>INTELLIGENT DEV PARTNER</small></span>
    </div>
  );
}

function GlassButton({ className = "", children, ...props }) {
  return <button className={`glass-button ${className}`} {...props}>{children}</button>;
}

function AnswerText({ text }) {
  if (!text) return null;
  const blocks = text.split("\n\n");
  return (
    <div className="answer-text">
      {blocks.map((block, index) => {
        const lines = block.split("\n").filter(Boolean);
        const bullets = lines.filter((line) => line.startsWith("• "));
        if (bullets.length === lines.length && bullets.length > 0) {
          return (
            <ul key={index} className="answer-list">
              {bullets.map((line) => (
                <li key={line}>{line.slice(2)}</li>
              ))}
            </ul>
          );
        }
        return lines.map((line) => <p key={`${index}-${line}`}>{line}</p>);
      })}
    </div>
  );
}

function SidebarItem({ icon: Icon, children, active, onClick, className = "" }) {
  return (
    <button type="button" onClick={onClick} className={`sidebar-item ${active ? "active" : ""} ${className}`.trim()}>
      <Icon size={18} strokeWidth={1.75} />
      <span>{children}</span>
    </button>
  );
}

function RagProgress({ stage, compact = false }) {
  const labels = ["检索", "召回", "重排", "生成"];
  const status = [
    "正在分析问题…",
    "正在检索 12 个知识库…",
    "已找到 13 个相关片段",
    "正在重新排序…",
    "已选取 5 个高相关片段",
  ];
  return (
    <div className={`rag-progress ${compact ? "compact" : ""}`}>
      <div>
        <Search size={18} />
        <span>{stage < 5 ? status[stage] : "检索完成，正在生成回答…"}</span>
      </div>
      <ol>
        {labels.map((label, index) => (
          <li className={stage >= index + 1 ? "done" : ""} key={label}>
            <b>{index === 3 && stage >= 4 ? "✓" : ""}</b>
            <span>{label}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function CitationCard({ item, index }) {
  return (
    <article className="citation-card" style={{ animationDelay: `${120 + index * 120}ms` }}>
      <div className={`file-icon ${item.type.toLowerCase()}`}>{item.type}</div>
      <div className="citation-title">{item.title}</div>
      <p className="citation-meta">
        {item.location} <i /> 相关度 <strong>{item.score}</strong>
      </p>
      <p className="citation-chunk">匹配片段 · {item.chunkId}</p>
      <p className="citation-copy">{item.matchText}</p>
    </article>
  );
}

function CitationsPanel({ open, citations, onClose }) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return citations;
    return citations.filter(
      (item) =>
        item.title.toLowerCase().includes(q) ||
        item.matchText.toLowerCase().includes(q) ||
        item.chunkId.toLowerCase().includes(q)
    );
  }, [citations, query]);

  return (
    <aside className={`citations ${open ? "shown" : ""}`}>
      <header>
        <div>
          <h2>引用来源</h2>
          <p>每个结论均可溯源至原文匹配片段</p>
        </div>
        <button className="mobile-close" onClick={onClose} aria-label="关闭引用">
          <X />
        </button>
      </header>
      <div className="citation-search">
        <Search size={16} />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索文档名或匹配内容…"
        />
      </div>
      {filtered.length ? (
        filtered.map((item, index) => <CitationCard key={item.id} item={item} index={index} />)
      ) : (
        <p className="empty-hint">未找到匹配的引用片段</p>
      )}
      <div className="trust">
        <ShieldCheck />
        <div>
          <b>回答依据 {citations.length} 个知识片段</b>
          <span>可信度　<strong>高</strong></span>
        </div>
      </div>
    </aside>
  );
}

function HeaderPopover({ label, icon: Icon, open, onToggle, onClose, children, badge }) {
  const wrapRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function handleClick(event) {
      if (wrapRef.current && !wrapRef.current.contains(event.target)) onClose();
    }
    function handleKey(event) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open, onClose]);

  return (
    <div className="header-popover-wrap" ref={wrapRef}>
      <button
        type="button"
        className={`header-icon-btn${open ? " active" : ""}`}
        onClick={onToggle}
        aria-label={label}
        aria-expanded={open}
      >
        <Icon size={20} />
        {badge ? <span className="header-icon-badge">{badge}</span> : null}
      </button>
      {open ? (
        <div className="header-popover" role="dialog" aria-label={label}>
          {children}
        </div>
      ) : null}
    </div>
  );
}

function AdminPageShell({ title, desc, action, children, className = "" }) {
  return (
    <section className={`admin-page ${className}`.trim()}>
      <header className="admin-page-header">
        <div className="admin-page-intro">
          <h1>{title}</h1>
          <p>{desc}</p>
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

function RetrievalPage() {
  const [query, setQuery] = useState("生产环境如何配置统一身份认证？");
  const [kbs, setKbs] = useState([]);
  const [selectedKbId, setSelectedKbId] = useState("");
  const [topK, setTopK] = useState(5);
  const [mode, setMode] = useState("hybrid");
  const [useRerank, setUseRerank] = useState(false);
  const [hasRun, setHasRun] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => {
    knowledgeApi.listBases()
      .then((data) => {
        const items = data.items || [];
        setKbs(items);
        setSelectedKbId((prev) => prev || items[0]?.id || "");
      })
      .catch(() => {});
  }, []);

  const selectedKb = kbs.find((item) => item.id === selectedKbId) || kbs[0];
  const kbName = result?.knowledgeBase || selectedKb?.name || "全部知识库";
  const results = result?.items || [];
  const rewrittenQuery = result?.rewrittenQuery || query;

  async function runSearch() {
    const text = query.trim();
    if (!text || loading) return;
    setLoading(true);
    setError("");
    try {
      const data = await knowledgeApi.searchRetrieval({
        question: text,
        knowledge_base_id: selectedKbId ? Number(selectedKbId) : undefined,
        top_k: topK,
        mode,
        use_rerank: useRerank,
        use_llm_rewrite: false,
      });
      setResult(data);
      setHasRun(true);
      if (data.warning) {
        setError(data.warning);
      }
    } catch (err) {
      setError(err.message);
      setHasRun(false);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AdminPageShell
      title="检索测试"
      desc="面向知识库管理员的调试工具：只跑「检索 + 重排」链路，不调用大模型，用于验证某个问题能否召回正确文档片段。"
      className="retrieval-page-shell"
    >
      <ol className="retrieval-steps" aria-label="检索流程">
        <li className={query.trim() ? "done" : ""}><b>1</b><span>输入测试问题</span></li>
        <li className={hasRun ? "done" : ""}><b>2</b><span>Query 改写</span></li>
        <li className={hasRun ? "active" : ""}><b>3</b><span>查看召回片段</span></li>
      </ol>

      <div className="retrieval-workspace">
        <aside className="retrieval-side admin-card">
          <label className="retrieval-field">
            <span>测试问题</span>
            <textarea
              value={query}
              onChange={(e) => { setQuery(e.target.value); setHasRun(false); }}
              rows={5}
              placeholder="输入你想验证的业务问题…"
            />
          </label>

          <label className="retrieval-field">
            <span>目标知识库</span>
            <SelectField
              className="retrieval-select-field"
              value={selectedKbId}
              onChange={(value) => { setSelectedKbId(value); setHasRun(false); }}
              placeholder="全部知识库"
              ariaLabel="目标知识库"
              options={[
                { value: "", label: "全部知识库" },
                ...kbs.map((item) => ({
                  value: item.id,
                  label: item.name,
                  hint: `${item.docCount} 篇 · ${item.owner || "未分组"}`,
                })),
              ]}
            />
          </label>

          <div className="retrieval-params-form">
            <label className="retrieval-field">
              <span>Top K</span>
              <SelectField
                className="retrieval-select-field"
                value={topK}
                onChange={(value) => { setTopK(Number(value)); setHasRun(false); }}
                ariaLabel="Top K"
                options={RETRIEVAL_TOP_K_OPTIONS}
              />
            </label>
            <label className="retrieval-field">
              <span>重排模型</span>
              <SelectField
                className="retrieval-select-field"
                value={useRerank ? "bge-reranker-v2-m3" : "none"}
                onChange={(value) => { setUseRerank(value !== "none"); setHasRun(false); }}
                ariaLabel="重排模型"
                options={RETRIEVAL_RERANK_OPTIONS}
              />
            </label>
            <label className="retrieval-field">
              <span>检索模式</span>
              <SelectField
                className="retrieval-select-field"
                value={mode}
                onChange={(value) => { setMode(value); setHasRun(false); }}
                ariaLabel="检索模式"
                options={RETRIEVAL_MODE_OPTIONS}
              />
            </label>
          </div>

          <GlassButton className="feature-primary retrieval-run" disabled={loading || !query.trim()} onClick={runSearch}>
            <Search size={17} /> {loading ? "检索中…" : "运行检索"}
          </GlassButton>
          {error ? <p className="kb-page-message">{error}</p> : null}
          <p className="retrieval-side-note">不会生成 AI 回答，仅展示召回片段与相关度分数。低内存环境请将重排设为「不重排」。</p>
        </aside>

        <div className="retrieval-main">
          {!hasRun ? (
            <section className="retrieval-empty admin-card">
              <Search size={28} />
              <h3>尚未运行检索</h3>
              <p>在左侧输入问题并点击「运行检索」，这里将展示 Query 改写结果与召回片段。</p>
            </section>
          ) : (
            <>
              <section className="retrieval-rewrite admin-card">
                <header>
                  <span className="retrieval-step-tag">Step 2 · Query 改写</span>
                  <p>系统将口语化问题转为更适合向量检索的表述，再进入召回阶段。</p>
                </header>
                <div className="rewrite-flow">
                  <article>
                    <small>原始问题</small>
                    <p>{query}</p>
                  </article>
                  <ArrowRight size={18} aria-hidden="true" />
                  <article className="rewritten">
                    <small>改写后检索词</small>
                    <p>{rewrittenQuery}</p>
                  </article>
                </div>
              </section>

              <section className="retrieval-results admin-card">
                <header>
                  <div>
                    <span className="retrieval-step-tag">Step 3 · 召回结果</span>
                    <h3>共召回 {results.length} 个相关片段</h3>
                    {result?.modeLabel ? (
                      <p className="retrieval-run-meta">
                        {result.modeLabel} · Top {result.topK ?? topK}
                        {result.useRerank === false ? " · 未重排" : ` · ${result.reranker}`}
                      </p>
                    ) : null}
                  </div>
                  <span className="retrieval-kb-tag">{kbName}</span>
                </header>
                <div className="retrieval-result-list">
                  {results.map((item, index) => (
                    <article className="retrieval-result-card" key={`${item.chunkId}-${index}`}>
                      <div className="result-rank">#{index + 1}</div>
                      <div className="result-body">
                        <div className="result-head">
                          <div className="result-doc">
                            <span className={`file-icon ${item.type.toLowerCase()}`}>{item.type}</span>
                            <strong>{item.doc}</strong>
                          </div>
                          <span className="score-tag">{item.score}</span>
                        </div>
                        <p className="result-meta">{item.location}</p>
                        <p className="result-snippet">{item.snippet}</p>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            </>
          )}
        </div>
      </div>
    </AdminPageShell>
  );
}

function ProfileField({ label, value, hint }) {
  return (
    <div className="profile-field">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint ? <small>{hint}</small> : null}
    </div>
  );
}

function ProfilePage({ user, onUpdateUser, onOpenSettings, stats }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ displayName: user.displayName, phone: user.phone });
  const [saved, setSaved] = useState(false);

  function saveProfile() {
    if (!form.displayName.trim()) return;
    onUpdateUser({
      displayName: form.displayName.trim(),
      phone: form.phone.trim(),
      nickname: form.displayName.trim(),
      avatar: form.displayName.trim().slice(0, 1),
    });
    setEditing(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  }

  return (
    <AdminPageShell
      title="个人信息"
      desc="查看账号资料、组织归属与使用概况。"
      action={(
        <GlassButton className="feature-primary" onClick={() => { setForm({ displayName: user.displayName, phone: user.phone }); setEditing(true); }}>
          <Pencil size={16} /> 编辑资料
        </GlassButton>
      )}
    >
      <section className="profile-hero admin-card">
        <div className="profile-hero-main">
          <div className="profile-avatar-lg">{user.avatar}</div>
          <div>
            <div className="profile-name-row">
              <h2>{user.displayName}</h2>
              <span className="status-tag ok">{user.status}</span>
            </div>
            <p className="profile-subtitle">{user.nickname} · {user.username}</p>
            <p className="profile-meta">{user.department} / 权限等级 {user.securityLevel}</p>
          </div>
        </div>
        <div className="profile-stats">
          <article><b>{stats.historyCount}</b><span>历史问答</span></article>
          <article><b>{stats.kbCount}</b><span>可访问知识库</span></article>
        </div>
      </section>

      <div className="profile-grid">
        <section className="admin-card profile-card">
          <header className="profile-card-head"><User size={18} /><h3>基本资料</h3></header>
          <div className="profile-fields">
            <ProfileField label="姓名" value={user.displayName} />
            <ProfileField label="账号" value={user.username} />
            <ProfileField label="手机号" value={maskPhone(user.phone)} />
            <ProfileField label="注册时间" value={user.createdAt} />
          </div>
        </section>

        <section className="admin-card profile-card">
          <header className="profile-card-head"><Building2 size={18} /><h3>组织信息</h3></header>
          <div className="profile-fields">
            <ProfileField label="部门/团队" value={user.team} />
            <ProfileField label="权限等级" value={user.securityLevel} />
          </div>
        </section>

        <section className="admin-card profile-card">
          <header className="profile-card-head"><KeyRound size={18} /><h3>账号与安全</h3></header>
          <div className="profile-fields">
            <ProfileField label="登录方式" value={user.loginMethod} />
            <ProfileField label="账号状态" value={user.status} />
          </div>
          <footer className="profile-card-foot">
            <button type="button" onClick={onOpenSettings}>前往系统设置 →</button>
            {saved ? <span className="profile-saved">资料已更新</span> : null}
          </footer>
        </section>
      </div>

      {editing && (
        <div className="admin-modal">
          <div className="admin-modal-box">
            <h3>编辑个人资料</h3>
            <label>姓名<input value={form.displayName} onChange={(e) => setForm((prev) => ({ ...prev, displayName: e.target.value }))} /></label>
            <label>手机号<input value={form.phone} onChange={(e) => setForm((prev) => ({ ...prev, phone: e.target.value }))} /></label>
            <p className="admin-note">昵称与手机号仅本地会话生效；完整资料修改需后端用户接口支持。</p>
            <div className="admin-modal-actions">
              <button type="button" onClick={() => setEditing(false)}>取消</button>
              <GlassButton className="feature-primary" onClick={saveProfile}>保存</GlassButton>
            </div>
          </div>
        </div>
      )}
    </AdminPageShell>
  );
}

function SettingsPage() {
  const [saved, setSaved] = useState(false);
  return (
    <AdminPageShell title="系统设置" desc="配置默认知识库、回答模式与界面偏好。">
      <div className="settings-panel admin-card flat">
        <article><b>默认知识库</b><p>安全与合规知识库、平台工程知识库</p><button type="button">编辑选择</button></article>
        <article><b>默认回答模式</b><p>技术问题</p><button type="button">技术问题　⌄</button></article>
        <article><b>界面语言</b><p>简体中文</p><button type="button">简体中文　⌄</button></article>
        <footer><GlassButton className="feature-primary" onClick={() => setSaved(true)}>{saved ? "已保存 ✓" : "保存偏好"}</GlassButton></footer>
      </div>
    </AdminPageShell>
  );
}

function Workspace({ onLanding, onLogout }) {
  const [prompt, setPrompt] = useState("");
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [stage, setStage] = useState(0);
  const [stream, setStream] = useState("");
  const [working, setWorking] = useState(false);
  const [sideOpen, setSideOpen] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [view, setView] = useState("chat");
  const [chunkNav, setChunkNav] = useState({ kbId: "", docId: "" });
  const [copied, setCopied] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarSearchOpen, setSidebarSearchOpen] = useState(false);
  const [sidebarQuery, setSidebarQuery] = useState("");
  const [user, setUser] = useState(() => buildWorkspaceUser(getStoredUser()) || {
    displayName: "用户", nickname: "用户", avatar: "用", username: "—", phone: "—",
    team: "—", department: "—", securityLevel: "team", createdAt: "—", loginMethod: "—", status: "正常",
  });
  const [activeCitations, setActiveCitations] = useState([]);
  const [kbs, setKbs] = useState([]);
  const [history, setHistory] = useState(INITIAL_HISTORY);
  const [hasConversation, setHasConversation] = useState(false);
  const [notifyOpen, setNotifyOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackType, setFeedbackType] = useState("issue");
  const [feedbackText, setFeedbackText] = useState("");
  const [feedbackContact, setFeedbackContact] = useState("");
  const [feedbackSending, setFeedbackSending] = useState(false);
  const [feedbackDone, setFeedbackDone] = useState(false);
  const composerRef = useRef(null);

  const notifications = useMemo(() => {
    const items = [];
    if (kbs.length === 0) {
      items.push({
        id: "no-kb",
        title: "尚未接入知识库",
        body: "上传企业文档后，问答才能基于真实内容检索与引用。",
        meta: "请由管理员或团队成员创建知识库并上传文档。",
        actionLabel: "前往知识库",
        onAction: () => switchView("knowledge"),
      });
    } else {
      kbs.forEach((kb) => {
        const creatorLine = `创建人：${kb.createdBy || "系统预置"}${kb.createdAt ? ` · ${kb.createdAt}` : ""}`;
        if (!kb.docCount) {
          items.push({
            id: `empty-${kb.id}`,
            title: `${kb.name} 暂无文档`,
            body: "该知识库还没有上传任何文件，检索与问答暂时无法命中相关内容。",
            meta: `${creatorLine} · 负责团队：${kb.owner || "未分配"}`,
            actionLabel: "上传文档",
            onAction: () => switchView("knowledge"),
          });
        } else if (kb.lastUploader) {
          items.push({
            id: `active-${kb.id}`,
            title: `${kb.name} · ${kb.docCount} 篇文档`,
            body: "知识库已有文档，可正常用于检索与问答。",
            meta: `${creatorLine} · 最后上传：${kb.lastUploader}${kb.lastUploadedAt ? ` · ${kb.lastUploadedAt}` : ""}`,
            actionLabel: "查看文档",
            onAction: () => switchView("knowledge"),
          });
        }
      });
    }
    if (working) {
      items.unshift({
        id: "rag-running",
        title: "正在检索知识库",
        body: "系统正在执行召回、重排与生成，完成后可在右侧查看引用来源。",
      });
    }
    if (items.length === 0) {
      items.push({
        id: "all-good",
        title: "暂无待处理事项",
        body: `已连接 ${kbs.length} 个知识库，系统运行正常。`,
      });
    }
    return items;
  }, [kbs, working]);

  function closeHeaderMenus() {
    setNotifyOpen(false);
    setFeedbackOpen(false);
  }

  async function submitFeedback(event) {
    event.preventDefault();
    if (!feedbackText.trim() || feedbackSending) return;
    setFeedbackSending(true);
    try {
      // 预留接口：POST /api/feedback
      await new Promise((resolve) => setTimeout(resolve, 500));
      setFeedbackDone(true);
      setFeedbackText("");
      setFeedbackContact("");
      setTimeout(() => {
        setFeedbackDone(false);
        closeHeaderMenus();
      }, 1400);
    } finally {
      setFeedbackSending(false);
    }
  }

  useEffect(() => {
    const el = composerRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [prompt]);

  useEffect(() => {
    authApi.me()
      .then((data) => setUser(buildWorkspaceUser(data)))
      .catch(() => {});
    knowledgeApi.listBases()
      .then((data) => setKbs(data.items || []))
      .catch(() => {});
  }, []);

  async function handleLogout() {
    try {
      await authApi.logout();
    } catch {
      // ignore logout errors
    }
    clearAuth();
    onLogout();
  }

  function switchView(next, payload) {
    if (payload?.kbId || payload?.docId) {
      setChunkNav({ kbId: payload.kbId || "", docId: payload.docId || "" });
    }
    setView(next);
    setSourceOpen(false);
    setSideOpen(false);
  }

  async function ask(questionText) {
    const text = (questionText ?? prompt).trim();
    if (!text || working) return;
    setPrompt(text);
    setCurrentQuestion(text);
    setHasConversation(true);
    setWorking(true);
    setStage(0);
    setStream("");
    setSourceOpen(false);
    setActiveCitations([]);
    const stageTimers = [0, 1, 2, 3, 4, 5].map((value, index) => setTimeout(() => setStage(value), index * 400));
    try {
      let data = null;
      try {
        data = await faqApi.search(text);
      } catch (faqError) {
        // FAQ 接口失败时仍尝试向量检索，避免后端瞬时抖动导致整页报错
        data = { found: false };
      }
      let answer;
      let citations = [];
      if (data.found) {
        answer = data.answer;
        if (data.source) {
          citations = [{
            id: `faq-${Date.now()}`,
            type: "FAQ",
            title: data.source,
            location: data.category || "高频问答",
            score: data.cached ? "缓存命中" : "精确匹配",
            matchText: data.answer?.slice(0, 120) || "",
            chunkId: `faq-${data.team || "default"}`,
          }];
        }
      } else {
        try {
          const retrieval = await knowledgeApi.searchRetrieval({
            question: text,
            top_k: 5,
            use_rerank: false,
            use_llm_rewrite: false,
          });
          if (retrieval.items?.length) {
            answer = `根据知识库检索到 ${retrieval.total} 个相关片段：\n\n${retrieval.items.map((item, index) => `${index + 1}. ${item.snippet}`).join("\n\n")}`;
            citations = retrieval.items.map((item, index) => ({
              id: `retrieval-${index}`,
              type: item.type,
              title: item.doc,
              location: item.location,
              score: item.score,
              matchText: item.snippet,
              chunkId: item.chunkId,
            }));
          } else {
            answer = data.message || "暂未在 FAQ 与向量库中找到匹配内容，请尝试换个问法或在知识库上传更多文档。";
          }
        } catch (retrievalError) {
          if (!data) throw retrievalError;
          answer = data.message || "暂未在 FAQ 中找到匹配内容；向量检索暂时不可用，请稍后重试。";
        }
      }
      if (!answer) {
        throw new Error("暂未找到匹配内容，请稍后重试或换个问法。");
      }
      setStream(answer);
      setActiveCitations(citations);
      setHistory((prev) => {
        const exists = prev.find((h) => h.question === text);
        const record = { id: `h${Date.now()}`, question: text, answer, time: "刚刚", citations };
        if (exists) return prev.map((h) => (h.question === text ? { ...h, answer, time: "刚刚", citations } : h));
        return [record, ...prev];
      });
    } catch (err) {
      setStream(`查询失败：${err.message}`);
      setActiveCitations([]);
    } finally {
      stageTimers.forEach(clearTimeout);
      setStage(5);
      setWorking(false);
    }
  }

  function openFromRecord(record) {
    setPrompt(record.question);
    setCurrentQuestion(record.question);
    setStream(record.answer);
    setHasConversation(true);
    setWorking(false);
    setActiveCitations(record.citations || []);
    setSourceOpen(false);
    switchView("chat");
  }

  async function copyAnswer() {
    try {
      await navigator.clipboard.writeText(stream);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  function startNewChat() {
    switchView("chat");
    setPrompt("");
    setStream("");
    setCurrentQuestion("");
    setHasConversation(false);
    setSourceOpen(false);
  }

  const filteredRecents = useMemo(() => {
    const q = sidebarQuery.trim().toLowerCase();
    if (!q) return history;
    return history.filter((item) => item.question.toLowerCase().includes(q));
  }, [history, sidebarQuery]);

  const sidebar = (
    <aside className={`sidebar ${sideOpen ? "shown" : ""} ${sidebarCollapsed ? "collapsed" : ""}`}>
      <div className="sidebar-head">
        <div className="sidebar-brand">
          <Logo compact />
          <span className="sidebar-brand-text">DevMind AI</span>
        </div>
        <div className="sidebar-head-actions">
          {!sidebarCollapsed && (
            <button
              type="button"
              className="sidebar-icon-btn"
              aria-label={sidebarSearchOpen ? "关闭搜索" : "搜索对话"}
              aria-pressed={sidebarSearchOpen}
              onClick={() => { setSidebarSearchOpen((v) => !v); if (sidebarSearchOpen) setSidebarQuery(""); }}
            >
              <Search size={18} />
            </button>
          )}
          <button
            type="button"
            className="sidebar-icon-btn sidebar-collapse-btn"
            aria-label={sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}
            onClick={() => { setSidebarCollapsed((v) => !v); setSidebarSearchOpen(false); setSidebarQuery(""); }}
          >
            {sidebarCollapsed ? <PanelRight size={18} /> : <PanelLeftClose size={18} />}
          </button>
          <button type="button" className="sidebar-icon-btn mobile-sidebar-close" onClick={() => setSideOpen(false)} aria-label="关闭菜单">
            <X size={18} />
          </button>
        </div>
      </div>

      <div className="sidebar-body">
        <nav className="sidebar-nav">
          <SidebarItem icon={SquarePen} onClick={startNewChat}>新建对话</SidebarItem>
          <SidebarItem icon={MessageCircle} active={view === "chat" && !hasConversation} onClick={startNewChat}>智能问答</SidebarItem>
          <SidebarItem icon={Library} active={view === "knowledge"} onClick={() => switchView("knowledge")}>知识库</SidebarItem>
          <SidebarItem icon={Search} active={view === "retrieval"} onClick={() => switchView("retrieval")}>检索测试</SidebarItem>
        </nav>

        {!sidebarCollapsed && (
          <section className="sidebar-recents">
            {sidebarSearchOpen && (
              <div className="sidebar-search">
                <Search size={16} />
                <input
                  value={sidebarQuery}
                  onChange={(e) => setSidebarQuery(e.target.value)}
                  placeholder="搜索对话…"
                  aria-label="搜索对话"
                />
              </div>
            )}
            <p className="recents-label">最近对话</p>
            <div className="recents-list">
              {filteredRecents.length ? filteredRecents.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`recent-item ${view === "chat" && currentQuestion === item.question ? "active" : ""}`}
                  onClick={() => openFromRecord(item)}
                  title={item.question}
                >
                  <span>{item.question}</span>
                </button>
              )) : (
                <p className="recents-empty">{sidebarQuery ? "未找到相关对话" : "暂无对话记录"}</p>
              )}
            </div>
          </section>
        )}
      </div>

      <div className="profile-wrap">
        <button type="button" className="profile" onClick={() => setProfileOpen((v) => !v)}>
          <div className="avatar">{user.avatar}</div>
          <div className="profile-copy">
            <b>{user.nickname}</b>
            <span>{user.department}</span>
          </div>
          {!sidebarCollapsed && <ChevronDown size={16} />}
        </button>
        {profileOpen && (
          <div className="profile-menu">
            <button type="button" className="profile-menu-user" onClick={() => { switchView("profile"); setProfileOpen(false); }}>
              <div className="avatar">{user.avatar}</div>
              <div className="profile-menu-user-copy">
                <b>{user.displayName}</b>
                <span>{user.department}</span>
              </div>
              <ChevronRight size={16} />
            </button>
            <div className="profile-menu-divider" />
            <button type="button" className="profile-menu-item" onClick={() => { switchView("settings"); setProfileOpen(false); }}>
              <Settings size={18} />
              <span>设置</span>
            </button>
            <div className="profile-menu-divider" />
            <button type="button" className="profile-menu-item" onClick={() => { setProfileOpen(false); onLanding(); }}>
              <span>返回展示页</span>
            </button>
            <button type="button" className="profile-menu-item" onClick={handleLogout}>
              <LogOut size={18} />
              <span>退出登录</span>
            </button>
          </div>
        )}
      </div>
    </aside>
  );

  return (
    <div className={`workspace-shell ${sourceOpen ? "" : "citations-hidden"} ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <button className="mobile-trigger left" onClick={() => setSideOpen(true)} aria-label="打开菜单"><PanelRight /></button>
      {sidebar}
      <main className={`workspace-main ${view !== "chat" ? "is-admin" : ""}`}>
        {view === "chat" ? (
          <>
            <header className="workspace-header">
              <div className="top-actions">
                <span className="connection"><i /> 已连接 {kbs.length} 个知识库</span>
                {hasConversation && activeCitations.length > 0 && (
                  <button className="citation-toggle" onClick={() => setSourceOpen((v) => !v)} aria-label={sourceOpen ? "隐藏引用来源" : "打开引用来源"} aria-pressed={sourceOpen}>
                    <PanelRight />
                  </button>
                )}
                <HeaderPopover
                  label="通知"
                  icon={Bell}
                  open={notifyOpen}
                  badge={notifications.filter((item) => item.actionLabel).length || undefined}
                  onToggle={() => {
                    setNotifyOpen((value) => !value);
                    setFeedbackOpen(false);
                  }}
                  onClose={closeHeaderMenus}
                >
                  <div className="header-popover-head">
                    <h3>通知</h3>
                    <span>{notifications.length} 条</span>
                  </div>
                  <ul className="notify-list">
                    {notifications.map((item) => (
                      <li key={item.id}>
                        <div>
                          <strong>{item.title}</strong>
                          <p>{item.body}</p>
                          {item.meta ? <span className="notify-meta">{item.meta}</span> : null}
                        </div>
                        {item.actionLabel ? (
                          <button
                            type="button"
                            onClick={() => {
                              item.onAction?.();
                              closeHeaderMenus();
                            }}
                          >
                            {item.actionLabel}
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </HeaderPopover>
                <HeaderPopover
                  label="反馈"
                  icon={MessageSquare}
                  open={feedbackOpen}
                  onToggle={() => {
                    setFeedbackOpen((value) => !value);
                    setNotifyOpen(false);
                  }}
                  onClose={closeHeaderMenus}
                >
                  <div className="header-popover-head">
                    <h3>意见反馈</h3>
                  </div>
                  {feedbackDone ? (
                    <p className="feedback-success">感谢反馈，我们已收到你的意见。</p>
                  ) : (
                    <form className="feedback-form" onSubmit={submitFeedback}>
                      <label>
                        反馈类型
                        <SelectField
                          value={feedbackType}
                          onChange={setFeedbackType}
                          options={FEEDBACK_TYPE_OPTIONS}
                          ariaLabel="反馈类型"
                        />
                      </label>
                      <label>
                        详细描述
                        <textarea
                          value={feedbackText}
                          onChange={(e) => setFeedbackText(e.target.value)}
                          placeholder="请描述你遇到的问题或改进建议…"
                          rows={4}
                          required
                        />
                      </label>
                      <label>
                        联系方式（选填）
                        <input
                          value={feedbackContact}
                          onChange={(e) => setFeedbackContact(e.target.value)}
                          placeholder="邮箱或手机号，便于跟进"
                        />
                      </label>
                      <button type="submit" className="feedback-submit" disabled={!feedbackText.trim() || feedbackSending}>
                        {feedbackSending ? "提交中…" : "提交反馈"}
                      </button>
                    </form>
                  )}
                </HeaderPopover>
              </div>
            </header>

            <div className="chat-panel">
              <div className="chat-scroll">
                {!hasConversation && (
                  <section className="greeting">
                    <div className="greeting-head">
                      <div className="greeting-orbit"><span /><span /><span /></div>
                      <h2>👋 晚上好，今天想了解什么？</h2>
                      <p>连接企业文档、Wiki 与代码仓库，获取带依据的技术答案。</p>
                    </div>
                    <div className="quick-actions in-greeting">
                      {QUICK_ACTIONS.map(([Icon, title, copy]) => (
                        <button key={title} type="button" onClick={() => ask(title)}>
                          <span className={`action-icon ${title}`}><Icon /></span>
                          <div className="quick-copy">
                            <b>{title}</b>
                            <p>{copy}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  </section>
                )}

                {hasConversation && (
                  <section className="conversation">
                    <div className="user-message">{currentQuestion}</div>
                    <div className="answer-row">
                      <div className="bot-avatar"><Bot size={19} /></div>
                      <article className="answer-card">
                        {working && <RagProgress stage={stage} compact />}
                        {(stream || working) && (
                          <>
                            {stream ? <AnswerText text={stream} /> : <p className="answer-text">正在为你整理企业内部知识…</p>}
                            {working && <i className="typing" />}
                          </>
                        )}
                        {!working && stream && (
                          <div className="answer-actions">
                            <GlassButton onClick={copyAnswer}><Copy />{copied ? "已复制" : "复制"}</GlassButton>
                            <GlassButton onClick={() => setPrompt(`基于「${currentQuestion}」，请继续说明企业落地时的注意事项。`)}><MessageCircle />继续追问</GlassButton>
                            {activeCitations.length > 0 && (
                              <GlassButton onClick={() => setSourceOpen(true)}><BookOpen />查看引用</GlassButton>
                            )}
                          </div>
                        )}
                      </article>
                    </div>
                  </section>
                )}
              </div>

              <div className="chat-composer">
                <div className="composer-shell">
                  <textarea
                    ref={composerRef}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        ask();
                      }
                    }}
                    placeholder={hasConversation ? "继续追问或输入新问题…" : "例如：Milvus 为什么适合企业级 RAG？"}
                    aria-label={hasConversation ? "追问" : "技术问题"}
                    rows={1}
                  />
                  <div className="composer-toolbar">
                    <button type="button" className="composer-tool" aria-label="添加附件">
                      <Plus size={18} />
                    </button>
                    <div className="composer-toolbar-right">
                      <button
                        type="button"
                        className={`composer-send${prompt.trim() && !working ? " ready" : ""}`}
                        onClick={() => ask()}
                        disabled={!prompt.trim() || working}
                        aria-label="发送"
                      >
                        <ArrowUp size={18} strokeWidth={2.5} />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </>
        ) : (
          <>
            {view === "knowledge" && (
              <KnowledgeAdmin
                onViewChunks={(kbId, docId) => switchView("chunks", { kbId, docId })}
              />
            )}
            {view === "chunks" && (
              <ChunkViewer initialKbId={chunkNav.kbId} initialDocId={chunkNav.docId} />
            )}
            {view === "retrieval" && <RetrievalPage />}
            {view === "profile" && (
              <ProfilePage
                user={user}
                onUpdateUser={(patch) => setUser((prev) => ({ ...prev, ...patch }))}
                onOpenSettings={() => switchView("settings")}
                stats={{ historyCount: history.length, kbCount: kbs.length }}
              />
            )}
            {view === "settings" && <SettingsPage />}
          </>
        )}
      </main>

      {view === "chat" && activeCitations.length > 0 && (
        <button className="mobile-trigger right" onClick={() => setSourceOpen(true)} aria-label="打开引用"><BookOpen /></button>
      )}
      {view === "chat" && <CitationsPanel open={sourceOpen} citations={activeCitations} onClose={() => setSourceOpen(false)} />}
    </div>
  );
}

function Landing({ onEnter, onLogin }) {
  return (
    <div className="landing landing-reference">
      <section className="landing-left">
        <header className="reference-brand"><Logo /><span className="deploy-tag">企业级 · 私有部署</span></header>
        <main className="reference-copy">
          <p>Enterprise AI Knowledge Workspace</p>
          <h1>让企业技术知识<br />真正可检索<br /><em>可追溯、可回答</em></h1>
          <div className="copy-detail">连接内部文档、Wiki、代码仓库与技术规范，<br />让可信检索、权限控制与引用溯源贯穿每次回答。</div>
          <div className="feature-tags"><span>私有化部署</span><span>细粒度权限</span><span>全链路溯源</span></div>
          <div className="reference-cta">
            <GlassButton className="primary" onClick={onEnter}>进入 DevMind AI <ArrowRight /></GlassButton>
            <button className="watch"><span>▶</span>观看演示</button>
          </div>
        </main>
        <footer className="reference-foot"><span>企业知识基础设施</span><div><b>SSO / RBAC</b><b>审计日志</b><b>多知识库隔离</b></div><small>PDF　WIKI　GIT　API　DATABASE</small></footer>
      </section>
      <section className="landing-right">
        <header className="reference-nav">
          <nav><a>工作空间</a><a>知识库</a><a>安全与权限</a><a>开发者</a></nav>
          <GlassButton onClick={onLogin}>登录 <ArrowRight size={15} /></GlassButton>
        </header>
        <div className="ambient-orbit" /><i className="network-dot d1" /><i className="network-dot d2" /><i className="network-dot d3" />
        <div className="preview-shell">
          <div className="preview-app">
            <header className="preview-header"><Logo compact /><span><i /> 已连接 12 个知识库</span><div className="preview-avatar">张</div></header>
            <aside className="preview-side">
              <button>＋ 新建对话</button>
              <b>◉　智能问答</b>
              <span>◫　知识库管理</span>
              <span>⌕　检索测试</span>
              <span>◷　历史记录</span>
              <span>☆　我的收藏</span>
            </aside>
            <main className="preview-main">
              <h2>企业技术知识助手</h2>
              <p>基于内部知识库回答 · 自动检索、重排并引用原文</p>
              <div className="preview-question">生产环境如何配置统一身份认证？<i>➤</i></div>
              <div className="preview-rag"><small>RAG 检索链路</small><div><b />检索 <i /> <b />召回 <i /> <b />重排 <i /> <b className="ready">✓</b>生成</div><strong>13 片段 → 5 高相关结果</strong></div>
              <article className="preview-answer"><b>DevMind AI</b><p>根据《统一身份认证接入规范》与《生产环境部署手册》，推荐采用 OIDC + 企业 SSO：</p><span>• 身份源：接入企业 IdP，并启用 MFA。</span><span>• 权限：通过 RBAC 映射部门与知识库权限。</span><span>• 审计：记录登录、检索与文档访问事件。</span><footer>复制　　继续追问　　查看引用</footer></article>
            </main>
            <aside className="preview-citations">
              <h3>引用来源</h3><small>点击可定位到原文</small>
              {[["PDF", "身份认证接入规范", "94%"], ["MD", "生产环境部署手册", "91%"], ["DOC", "研发安全基线", "88%"]].map(([type, name, score]) => (
                <article key={name}><b className={type}>{type}</b><strong>{name}</strong><span>第 18 页 · <em>{score}</em></span><p>OIDC 接入应统一使用企业 IdP，并结合 MFA 与角色…</p></article>
              ))}
              <div className="preview-trust"><ShieldCheck /><span>回答依据 <b>5</b> 个知识片段<br /><small>可信度　<strong>高</strong></small></span></div>
            </aside>
          </div>
        </div>
      </section>
    </div>
  );
}

function useRoute() {
  const [path, setPath] = useState(() => location.pathname);
  useEffect(() => {
    const change = () => setPath(location.pathname);
    addEventListener("popstate", change);
    return () => removeEventListener("popstate", change);
  }, []);
  return [path, (to) => { history.pushState({}, "", to); setPath(to); }];
}

export default function App() {
  const [path, navigate] = useRoute();
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    setUnauthorizedHandler(() => navigate("/login"));
    setAuthReady(true);
  }, [navigate]);

  useEffect(() => {
    if (!authReady) return;
    if (path === "/workspace" && !getToken()) {
      navigate("/login");
    }
  }, [path, authReady, navigate]);

  if (path === "/login") {
    return <LoginPage onSuccess={() => navigate("/workspace")} onNavigate={navigate} />;
  }
  if (path === "/terms") {
    return <LegalPage type="terms" onBack={() => navigate("/login")} />;
  }
  if (path === "/privacy") {
    return <LegalPage type="privacy" onBack={() => navigate("/login")} />;
  }
  if (path === "/workspace") {
    if (!getToken()) return null;
    return (
      <Workspace
        onLanding={() => navigate("/")}
        onLogout={() => navigate("/login")}
      />
    );
  }
  return <Landing onEnter={() => navigate("/login")} onLogin={() => navigate("/login")} />;
}
