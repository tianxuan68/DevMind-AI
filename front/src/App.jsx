import React, { useEffect, useMemo, useState } from "react";
import {
  ArrowRight, Bell, BookOpen, Bot, Building2, ChevronDown, CircleHelp,
  Clipboard, Copy, Eye, EyeOff, FileText, KeyRound,
  Library, LogOut, MessageCircle, PanelLeftClose, PanelRight, Pencil,
  Search, Send, Settings, ShieldCheck, SquarePen, User,
  Wrench, X, ChevronRight,
} from "lucide-react";
import "./styles.css";
import KnowledgeAdmin from "./components/KnowledgeAdmin";
import {
  authApi, clearAuth, getStoredUser, getToken, knowledgeApi, setAuth, setUnauthorizedHandler,
} from "./api/qa";

const DEMO_ANSWER =
  "Milvus 非常适合企业级 RAG 场景，主要体现在以下三点：\n\n• 分布式架构：基于云原生设计，支持弹性扩展与高可用部署，轻松应对大规模数据与并发场景。\n• 高性能向量检索：支持多种索引算法，在亿级向量规模下仍能保持毫秒级检索延迟。\n• 良好的可扩展性：存储与计算解耦，支持水平扩展与多租户隔离，满足企业知识库长期演进需求。";

const DEMO_CITATIONS = [
  {
    id: "c1",
    type: "PDF",
    title: "RAG架构设计规范.pdf",
    location: "第 12 页",
    score: "94%",
    matchText: "RAG 系统的核心在于高效的检索与生成结合。Milvus 作为向量数据库，可支撑亿级向量检索与毫秒级响应。",
    chunkId: "chunk-12-003",
  },
  {
    id: "c2",
    type: "MD",
    title: "向量数据库选型指南.md",
    location: "Chunk #42",
    score: "91%",
    matchText: "在向量数据库选型中，需要重点关注性能、扩展性、可用性与生态兼容性，Milvus 在企业级场景表现稳定。",
    chunkId: "chunk-42",
  },
  {
    id: "c3",
    type: "PDF",
    title: "Milvus部署实践手册.pdf",
    location: "第 8 页",
    score: "89%",
    matchText: "Milvus 支持分布式集群部署，提供多种存储后端与索引类型，适合长期演进的企业知识库架构。",
    chunkId: "chunk-8-007",
  },
];

const INITIAL_HISTORY = [
  {
    id: "h1",
    question: "Milvus 为什么适合企业级 RAG？",
    answer: DEMO_ANSWER,
    time: "2026-08-23 14:32",
    citations: DEMO_CITATIONS,
  },
  {
    id: "h2",
    question: "生产环境如何配置统一身份认证？",
    answer: "根据《统一身份认证接入规范》，推荐采用 OIDC + 企业 SSO，并通过 RBAC 映射部门与知识库权限。",
    time: "2026-08-23 11:18",
    citations: [],
  },
  {
    id: "h3",
    question: "如何设计多租户知识隔离？",
    answer: "建议按租户划分 Milvus Collection / Partition，并在检索层注入 tenant_id 过滤条件，配合 RBAC 控制文档可见范围。",
    time: "2026-08-22 17:05",
    citations: [],
  },
];

const QUICK_ACTIONS = [
  [MessageCircle, "技术问题", "解答架构、原理与实现等技术问题"],
  [Wrench, "问题排查", "协助定位与分析系统或业务问题"],
  [Clipboard, "文档总结", "提炼文档要点，生成结构化摘要"],
];

const INITIAL_USER = {
  displayName: "张伟",
  nickname: "张工程师",
  avatar: "张",
  email: "zhangwei@company.com",
  employeeId: "RD-10248",
  phone: "13800135621",
  department: "研发部",
  team: "平台工程组",
  role: "高级工程师",
  manager: "李总监",
  loginMethod: "企业 SSO",
  lastLogin: "2026-08-23 17:28",
  joinedAt: "2024-03-15",
  status: "正常",
};

function buildWorkspaceUser(apiUser) {
  if (!apiUser) return INITIAL_USER;
  const name = apiUser.nickname || apiUser.username || "用户";
  return {
    ...INITIAL_USER,
    displayName: name,
    nickname: name,
    avatar: name.slice(0, 1),
    phone: apiUser.phone || INITIAL_USER.phone,
    team: apiUser.team || INITIAL_USER.team,
    department: apiUser.team || INITIAL_USER.department,
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
  const [kb, setKb] = useState("安全与合规知识库");
  const [hasRun, setHasRun] = useState(true);
  const rewrittenQuery = "生产环境的统一身份认证与权限配置方案";
  const results = [
    { score: "0.94", doc: "身份认证接入规范.pdf", type: "PDF", location: "第 18 页", snippet: "OIDC 接入应统一使用企业 IdP，并结合 MFA 与角色映射控制知识库访问权限。" },
    { score: "0.91", doc: "生产环境部署手册.md", type: "MD", location: "Chunk #42", snippet: "生产环境需启用统一身份认证，并通过 RBAC 控制不同部门对文档与知识库的可见范围。" },
    { score: "0.88", doc: "研发安全基线.docx", type: "DOC", location: "第 7 页", snippet: "所有研发系统登录必须接入企业 SSO，并保留完整审计日志以满足合规要求。" },
  ];

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
          <header className="retrieval-side-head">
            <h2>测试输入</h2>
            <p>模拟用户在问答中的提问，检查知识库召回是否准确。</p>
          </header>

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
            <select value={kb} onChange={(e) => { setKb(e.target.value); setHasRun(false); }}>
              <option>安全与合规知识库</option>
              <option>平台工程知识库</option>
              <option>研发实践知识库</option>
            </select>
          </label>

          <dl className="retrieval-params">
            <div><dt>Top K</dt><dd>20</dd></div>
            <div><dt>重排模型</dt><dd>bge-reranker-v2-m3</dd></div>
            <div><dt>检索模式</dt><dd>混合检索</dd></div>
          </dl>

          <GlassButton className="feature-primary retrieval-run" onClick={() => setHasRun(true)}>
            <Search size={17} /> 运行检索
          </GlassButton>
          <p className="retrieval-side-note">不会生成 AI 回答，仅展示召回片段与相关度分数。</p>
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
                  </div>
                  <span className="retrieval-kb-tag">{kb}</span>
                </header>
                <div className="retrieval-result-list">
                  {results.map((item, index) => (
                    <article className="retrieval-result-card" key={item.doc}>
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
            <p className="profile-subtitle">{user.nickname} · {user.role}</p>
            <p className="profile-meta">{user.department} / {user.team}</p>
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
            <ProfileField label="工号" value={user.employeeId} />
            <ProfileField label="邮箱" value={user.email} hint="由企业 SSO 同步，不可修改" />
            <ProfileField label="手机号" value={maskPhone(user.phone)} />
            <ProfileField label="入职日期" value={user.joinedAt} />
          </div>
        </section>

        <section className="admin-card profile-card">
          <header className="profile-card-head"><Building2 size={18} /><h3>组织信息</h3></header>
          <div className="profile-fields">
            <ProfileField label="部门" value={user.department} />
            <ProfileField label="团队" value={user.team} />
            <ProfileField label="岗位" value={user.role} />
            <ProfileField label="直属上级" value={user.manager} />
          </div>
        </section>

        <section className="admin-card profile-card">
          <header className="profile-card-head"><KeyRound size={18} /><h3>账号与安全</h3></header>
          <div className="profile-fields">
            <ProfileField label="登录方式" value={user.loginMethod} />
            <ProfileField label="上次登录" value={user.lastLogin} />
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
            <p className="admin-note">邮箱与组织信息由企业目录同步，如需变更请联系管理员。</p>
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
  const [copied, setCopied] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarSearchOpen, setSidebarSearchOpen] = useState(false);
  const [sidebarQuery, setSidebarQuery] = useState("");
  const [user, setUser] = useState(() => buildWorkspaceUser(getStoredUser()));
  const [activeCitations, setActiveCitations] = useState(DEMO_CITATIONS);
  const [kbs, setKbs] = useState([]);
  const [history, setHistory] = useState(INITIAL_HISTORY);
  const [hasConversation, setHasConversation] = useState(false);

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

  function switchView(next) {
    setView(next);
    setSourceOpen(false);
    setSideOpen(false);
  }

  function ask(questionText) {
    const text = (questionText ?? prompt).trim();
    if (!text || working) return;
    setPrompt(text);
    setCurrentQuestion(text);
    setHasConversation(true);
    setWorking(true);
    setStage(0);
    setStream("");
    setSourceOpen(false);
    setActiveCitations(text.includes("Milvus") ? DEMO_CITATIONS : []);
    [0, 1, 2, 3, 4, 5].forEach((value, index) => setTimeout(() => setStage(value), index * 550));
    setTimeout(() => {
      let i = 0;
      const timer = setInterval(() => {
        i += 8;
        setStream(DEMO_ANSWER.slice(0, i));
        if (i >= DEMO_ANSWER.length) {
          clearInterval(timer);
          setWorking(false);
          setHistory((prev) => {
            const exists = prev.find((h) => h.question === text);
            if (exists) return prev.map((h) => (h.question === text ? { ...h, answer: DEMO_ANSWER, time: "刚刚" } : h));
            return [{ id: `h${Date.now()}`, question: text, answer: DEMO_ANSWER, time: "刚刚", citations: DEMO_CITATIONS }, ...prev];
          });
        }
      }, 23);
    }, 3000);
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
                <Bell /><CircleHelp />
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
                  <button type="button" className="composer-send" onClick={() => ask()} aria-label="发送">
                    <Send size={18} />
                  </button>
                </div>
              </div>
            </div>
          </>
        ) : (
          <>
            {view === "knowledge" && <KnowledgeAdmin />}
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

function Login({ onSuccess }) {
  const [show, setShow] = useState(false);
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState("");
  const [method, setMethod] = useState("password");
  const [mode, setMode] = useState("login");
  const [codeSent, setCodeSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [debugCode, setDebugCode] = useState("");

  const isRegister = mode === "register";

  async function submit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      let data;
      if (isRegister) {
        if (!account.trim() || !password || !phone.trim() || !code.trim()) {
          setError("请填写用户名、密码、手机号和验证码");
          return;
        }
        data = await authApi.register({
          username: account.trim(),
          password,
          phone: phone.trim(),
          sms_code: code.trim(),
        });
      } else if (method === "password") {
        if (!account.trim() || !password) {
          setError("请输入账号和密码");
          return;
        }
        data = await authApi.login(account.trim(), password);
      } else {
        if (!phone.trim() || !code.trim()) {
          setError("请输入手机号和验证码");
          return;
        }
        data = await authApi.smsLogin(phone.trim(), code.trim());
      }
      setAuth(data.access_token, data.user);
      onSuccess(data.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const switchMethod = () => { setMethod((v) => (v === "password" ? "phone" : "password")); setError(""); setCodeSent(false); setDebugCode(""); };

  async function sendCode() {
    if (!phone.trim()) { setError("请先输入手机号"); return; }
    setError("");
    try {
      const data = await authApi.sendCode(phone.trim());
      setCodeSent(true);
      if (data.debug_code) setDebugCode(data.debug_code);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="login-page">
      <section className="login-box">
        <div className="login-brand">
          <h1 className="login-brand-title">
            <svg className="login-brand-icon" viewBox="0 0 64 56" aria-hidden="true">
              <path d="M32 8 13 43M32 8l19 35M13 43h38" />
              <circle cx="32" cy="8" r="7" />
              <circle cx="13" cy="43" r="6" />
              <circle cx="51" cy="43" r="6" />
              <circle className="logo-dot" cx="32" cy="8" r="2.5" />
            </svg>
            <span>
              {isRegister ? "注册 DevMind AI" : "登录 DevMind AI"}
              <small>INTELLIGENT DEV PARTNER</small>
            </span>
          </h1>
        </div>
        <form onSubmit={submit}>
          {isRegister ? (
            <>
              <label>用户名<input value={account} onChange={(e) => setAccount(e.target.value)} placeholder="请输入用户名" autoComplete="username" /></label>
              <label>密码<span className="password-field"><input value={password} onChange={(e) => setPassword(e.target.value)} type={show ? "text" : "password"} placeholder="请输入密码" autoComplete="new-password" /><button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? "隐藏密码" : "显示密码"}>{show ? <EyeOff /> : <Eye />}</button></span></label>
              <label>手机号<input value={phone} onChange={(e) => { setPhone(e.target.value); setCodeSent(false); setDebugCode(""); }} placeholder="请输入手机号" inputMode="tel" autoComplete="tel" /></label>
              <label>验证码<span className="code-field"><input value={code} onChange={(e) => setCode(e.target.value)} placeholder="请输入验证码" inputMode="numeric" autoComplete="one-time-code" /><button type="button" onClick={sendCode}>{codeSent ? "已发送" : "获取验证码"}</button></span></label>
              {debugCode ? <p className="login-debug">开发环境验证码：{debugCode}</p> : null}
            </>
          ) : method === "password" ? (
            <>
              <label>账号 / 邮箱<input value={account} onChange={(e) => setAccount(e.target.value)} placeholder="请输入账号或企业邮箱" autoComplete="username" /></label>
              <label>密码<span className="password-field"><input value={password} onChange={(e) => setPassword(e.target.value)} type={show ? "text" : "password"} placeholder="请输入密码" autoComplete="current-password" /><button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? "隐藏密码" : "显示密码"}>{show ? <EyeOff /> : <Eye />}</button></span></label>
            </>
          ) : (
            <>
              <label>手机号<input value={phone} onChange={(e) => { setPhone(e.target.value); setCodeSent(false); setDebugCode(""); }} placeholder="请输入手机号" inputMode="tel" autoComplete="tel" /></label>
              <label>验证码<span className="code-field"><input value={code} onChange={(e) => setCode(e.target.value)} placeholder="请输入验证码" inputMode="numeric" autoComplete="one-time-code" /><button type="button" onClick={sendCode}>{codeSent ? "已发送" : "获取验证码"}</button></span></label>
              {debugCode ? <p className="login-debug">开发环境验证码：{debugCode}</p> : null}
            </>
          )}
          {error && <p className="login-error">{error}</p>}
          {!isRegister && <div className="login-options"><label><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />记住登录状态</label><button type="button">忘记密码？</button></div>}
          {isRegister && <p className="register-note">注册即表示你同意 <a>用户协议</a> 与 <a>隐私政策</a></p>}
          <button className="login-submit" type="submit" disabled={loading}>{loading ? "处理中…" : isRegister ? "注册并进入" : "登录"} <ArrowRight /></button>
        </form>
        {import.meta.env.DEV && !isRegister && method === "password" && (
          <p className="login-dev-hint">开发测试账号：admin / 123456（此前 Mock 登录不校验密码，现已接入真实鉴权）</p>
        )}
        <div className="login-switch">
          <span>{isRegister ? "已有账号？" : "还没有账号？"}</span>
          <button type="button" onClick={() => { setMode(isRegister ? "login" : "register"); setError(""); setDebugCode(""); }}>
            {isRegister ? "登录" : "注册账号"}
          </button>
        </div>
        {!isRegister && (
          <div className="login-alt">
            <div className="login-divider"><span>其他登录方式</span></div>
            <button type="button" className="login-alt-btn" onClick={switchMethod}>
              {method === "password" ? "手机验证码登录" : "账号密码登录"}
            </button>
          </div>
        )}
      </section>
      <footer className="login-footer">© 2026 DevMind AI　 <a>隐私政策</a> · <a>用户协议</a></footer>
    </main>
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

  if (path === "/login") return <Login onSuccess={() => navigate("/workspace")} />;
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
