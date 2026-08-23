import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowRight,
  Bell,
  BookOpen,
  Bot,
  ChevronDown,
  CircleHelp,
  Clipboard,
  Copy,
  Eye,
  EyeOff,
  FileText,
  Heart,
  History,
  Library,
  Mail,
  MessageCircle,
  PanelRight,
  Plus,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Smartphone,
  Star,
  Wrench,
  X,
} from "lucide-react";
import "./styles.css";

const answer =
  "Milvus 非常适合企业级 RAG 场景，主要体现在以下三点：\n\n• 分布式架构：基于云原生设计，支持弹性扩展与高可用部署，轻松应对大规模数据与并发场景。\n• 高性能向量检索：支持多种索引算法，在亿级向量规模下仍能保持毫秒级检索延迟。\n• 良好的可扩展性：存储与计算解耦，支持水平扩展与多租户隔离，满足企业知识库长期演进需求。";
const citations = [
  [
    "PDF",
    "RAG架构设计规范.pdf",
    "第 12 页",
    "94%",
    "RAG 系统的核心在于高效的检索与生成结合。Milvus 作为向量数据库…",
  ],
  [
    "MD",
    "向量数据库选型指南.md",
    "Chunk #42",
    "91%",
    "在向量数据库选型中，需要重点关注性能、扩展性、可用性与生态兼容性…",
  ],
  [
    "PDF",
    "Milvus部署实践手册.pdf",
    "第 8 页",
    "89%",
    "Milvus 支持分布式集群部署，提供多种存储后端与索引类型…",
  ],
];

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
      <span>
        DevMind <b>AI</b>
        <small>INTELLIGENT DEV PARTNER</small>
      </span>
    </div>
  );
}
function GlassButton({ className = "", children, ...props }) {
  return (
    <button className={`glass-button ${className}`} {...props}>
      {children}
    </button>
  );
}
function NavItem({ icon: Icon, children, active, onClick }) {
  return (
    <button onClick={onClick} className={`side-nav ${active ? "active" : ""}`}>
      <Icon size={19} />
      <span>{children}</span>
    </button>
  );
}
function NavLabel({ icon: Icon, children }) {
  return (
    <div className="side-nav side-label">
      <Icon size={19} />
      <span>{children}</span>
    </div>
  );
}
function CitationCard({ item, index }) {
  return (
    <article
      className="citation-card"
      style={{ animationDelay: `${120 + index * 120}ms` }}
    >
      <div className={`file-icon ${item[0].toLowerCase()}`}>{item[0]}</div>
      <div className="citation-title">{item[1]}</div>
      <p className="citation-meta">
        {item[2]} <i /> 相关度 <strong>{item[3]}</strong>
      </p>
      <p className="citation-copy">{item[4]}</p>
    </article>
  );
}
function RagProgress({ stage }) {
  const labels = ["检索", "召回", "重排", "生成"];
  const status = [
    "正在分析问题…",
    "正在检索 12 个知识库…",
    "已找到 13 个相关片段",
    "正在重新排序…",
    "已选取 5 个高相关片段",
  ];
  return (
    <div className="rag-progress">
      <div>
        <Search size={18} />
        <span>
          {stage < 5
            ? status[stage]
            : "已检索 13 个相关片段 · 已重排 5 个高相关结果"}
        </span>
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

const featureData = {
  knowledge: ["平台工程知识库", "安全与合规知识库", "研发实践知识库"],
  documents: [
    "身份认证接入规范.pdf",
    "生产环境部署手册.md",
    "研发安全基线.docx",
  ],
  history: [
    "Milvus 为什么适合企业级 RAG？",
    "生产环境如何配置统一身份认证？",
    "如何设计多租户知识隔离？",
  ],
  favorites: ["企业级 RAG 的索引策略", "统一身份认证的配置建议"],
};
function FeatureOverlay({ view, close }) {
  const [query, setQuery] = useState("统一身份认证");
  const [saved, setSaved] = useState(false);
  const title = {
    knowledge: "知识库",
    documents: "文档管理",
    retrieval: "检索测试",
    history: "历史记录",
    favorites: "我的收藏",
    settings: "系统设置",
  }[view];
  const list = featureData[view] || [];
  return (
    <section className="feature-overlay">
      <header>
        <div>
          <button className="back" onClick={close}>
            ← 返回智能问答
          </button>
          <h1>{title}</h1>
          <p>
            {view === "retrieval"
              ? "验证召回片段与重排效果，不生成回答。"
              : "以下内容使用 Mock 数据呈现，等待接口接入。"}
          </p>
        </div>
        {view === "documents" && (
          <GlassButton className="feature-primary">＋ 上传文档</GlassButton>
        )}
        {view === "knowledge" && (
          <GlassButton className="feature-primary">＋ 新建知识库</GlassButton>
        )}
      </header>
      {view === "retrieval" ? (
        <div className="retrieval-panel">
          <label>
            测试问题
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div>
            <span>知识库：安全与合规知识库</span>
            <span>Top K：20</span>
            <GlassButton className="feature-primary">
              运行检索 <Search />
            </GlassButton>
          </div>
          <article>
            <b>Query 改写</b>
            <p>生产环境的统一身份认证与权限配置方案</p>
            <ol>
              <li>
                <strong>0.94</strong> 身份认证接入规范.pdf　·　第 18 页
              </li>
              <li>
                <strong>0.91</strong> 生产环境部署手册.md　·　Chunk #42
              </li>
              <li>
                <strong>0.88</strong> 研发安全基线.docx　·　第 7 页
              </li>
            </ol>
          </article>
        </div>
      ) : view === "settings" ? (
        <div className="settings-panel">
          <article>
            <b>默认知识库</b>
            <p>安全与合规知识库、平台工程知识库</p>
            <button>编辑选择</button>
          </article>
          <article>
            <b>默认回答模式</b>
            <p>技术问题</p>
            <button>技术问题　⌄</button>
          </article>
          <article>
            <b>界面语言</b>
            <p>简体中文</p>
            <button>简体中文　⌄</button>
          </article>
          <footer>
            <GlassButton
              className="feature-primary"
              onClick={() => setSaved(true)}
            >
              {saved ? "已保存 ✓" : "保存偏好"}
            </GlassButton>
          </footer>
        </div>
      ) : (
        <div className="feature-grid">
          {list.map((item, index) => (
            <article key={item}>
              <span className="feature-icon">
                {view === "documents"
                  ? "PDF"
                  : view === "knowledge"
                    ? "KB"
                    : view === "favorites"
                      ? "☆"
                      : "◷"}
              </span>
              <div>
                <b>{item}</b>
                <p>
                  {view === "knowledge"
                    ? `已收录 ${[128, 86, 214][index]} 份文档 · 状态正常`
                    : view === "documents"
                      ? `安全与合规知识库 · ${["已就绪", "处理中", "已就绪"][index]}`
                      : "最近更新于今天 14:32"}
                </p>
              </div>
              <button aria-label="更多操作">•••</button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function ProfileOverlay({ profile, onSave, close }) {
  const [draft, setDraft] = useState(profile);
  const [saved, setSaved] = useState(false);
  useEffect(() => setDraft(profile), [profile]);
  const change = (field) => (event) => {
    setDraft((value) => ({ ...value, [field]: event.target.value }));
    setSaved(false);
  };
  const save = (event) => {
    event.preventDefault();
    onSave(draft);
    setSaved(true);
  };
  return (
    <section className="feature-overlay profile-overlay">
      <header>
        <div>
          <button className="back" onClick={close}>
            ← 返回智能问答
          </button>
          <h1>个人信息</h1>
          <p>完善个人档案，帮助团队成员快速识别你的角色与协作方式。</p>
        </div>
      </header>
      <form className="profile-editor" onSubmit={save}>
        <aside className="profile-summary-card">
          <div className="profile-summary-identity">
            <div className="profile-summary-avatar">{draft.display_name?.slice(0, 1) || "张"}</div>
            <div>
              <h2>{draft.display_name || "未填写姓名"}</h2>
              <p>{draft.job_title || "未填写职位"} · {draft.department_name || "未填写部门"}</p>
            </div>
          </div>
          <div className="profile-summary-status"><i /> 账户资料完整度良好</div>
          <div className="profile-summary-facts">
            <div><Mail /><span>企业邮箱</span><b>{draft.email || "待填写"}</b></div>
            <div><Smartphone /><span>手机号</span><b>{draft.phone || "待填写"}</b></div>
            <div><ShieldCheck /><span>工号</span><b>{draft.employee_no || "待填写"}</b></div>
          </div>
        </aside>
        <div className="profile-editor-grid">
          <div className="profile-form-panels">
            <section className="profile-form-panel">
              <div className="profile-panel-heading">
                <h2>基础资料</h2>
                <p>这些信息将用于工作台中的个人身份展示。</p>
              </div>
              <div className="profile-form-grid">
                <label>
                  姓名
                  <input value={draft.display_name} onChange={change("display_name")} required />
                </label>
                <fieldset className="profile-gender">
                  <legend>性别</legend>
                  {[["male", "男"], ["female", "女"], ["unspecified", "不透露"]].map(([value, label]) => (
                    <label key={value} className={draft.gender === value ? "selected" : ""}>
                      <input type="radio" name="gender" value={value} checked={draft.gender === value} onChange={change("gender")} />
                      {label}
                    </label>
                  ))}
                </fieldset>
                <label>
                  出生日期
                  <input type="date" value={draft.birth_date} onChange={change("birth_date")} />
                </label>
                <label>
                  手机号
                  <input type="tel" value={draft.phone} onChange={change("phone")} placeholder="请输入手机号" />
                </label>
                <label className="profile-span-2">
                  企业邮箱
                  <input type="email" value={draft.email} onChange={change("email")} required />
                </label>
              </div>
            </section>
            <section className="profile-form-panel">
              <div className="profile-panel-heading">
                <h2>工作信息</h2>
                <p>清晰的团队信息会同步展示在侧栏与个人资料中。</p>
              </div>
              <div className="profile-form-grid">
                <label>
                  部门
                  <input value={draft.department_name} onChange={change("department_name")} required />
                </label>
                <label>
                  职位
                  <input value={draft.job_title} onChange={change("job_title")} required />
                </label>
                <label>
                  工号
                  <input value={draft.employee_no} onChange={change("employee_no")} />
                </label>
                <label>
                  入职日期
                  <input type="date" value={draft.joined_at} onChange={change("joined_at")} />
                </label>
                <label className="profile-span-2">
                  个人简介
                  <textarea value={draft.bio} onChange={change("bio")} placeholder="介绍你的专业方向与协作偏好" />
                </label>
              </div>
            </section>
            <section className="profile-form-panel profile-preferences-panel">
              <div className="profile-panel-heading">
                <h2>使用偏好</h2>
              </div>
              <div className="profile-form-grid">
                <label>
                  时区
                  <select value={draft.timezone} onChange={change("timezone")}>
                    <option value="Asia/Shanghai">中国标准时间（UTC+8）</option>
                    <option value="Asia/Tokyo">日本标准时间（UTC+9）</option>
                    <option value="America/Los_Angeles">太平洋时间</option>
                  </select>
                </label>
                <label>
                  界面语言
                  <select value={draft.locale} onChange={change("locale")}>
                    <option value="zh-CN">简体中文</option>
                    <option value="en-US">English</option>
                  </select>
                </label>
              </div>
            </section>
          </div>
        </div>
        <footer className="profile-form-actions">
          <span>{saved ? "资料已保存，并已同步至侧栏" : "修改后请点击保存资料"}</span>
          <div>
            <button type="button" onClick={() => { setDraft(profile); setSaved(false); }}>重置</button>
            <GlassButton className="feature-primary" type="submit">{saved ? "已保存 ✓" : "保存资料"}</GlassButton>
          </div>
        </footer>
      </form>
    </section>
  );
}

function Workspace({ onLanding, onLogout }) {
  const [prompt, setPrompt] = useState("");
  const [question, setQuestion] = useState("");
  const [stage, setStage] = useState(5);
  const [stream, setStream] = useState("");
  const [working, setWorking] = useState(false);
  const [sideOpen, setSideOpen] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(
    () => window.matchMedia("(min-width: 901px)").matches,
  );
  const [view, setView] = useState("chat");
  const [copied, setCopied] = useState(false);
  const [favorited, setFavorited] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [profile, setProfile] = useState({
    display_name: "张工程师",
    gender: "male",
    birth_date: "1998-08-12",
    email: "zhang@example.com",
    phone: "13800138000",
    department_name: "平台研发部",
    job_title: "高级后端工程师",
    employee_no: "DM-2024-018",
    joined_at: "2024-03-18",
    bio: "专注企业平台与知识系统研发。",
    timezone: "Asia/Shanghai",
    locale: "zh-CN",
  });
  const ask = () => {
    if (!prompt.trim() || working) return;
    setQuestion(prompt.trim());
    setWorking(true);
    setStage(0);
    setStream("");
    [0, 1, 2, 3, 4, 5].forEach((value, index) =>
      setTimeout(() => setStage(value), index * 550),
    );
    setTimeout(() => {
      let i = 0;
      const timer = setInterval(() => {
        i += 8;
        setStream(answer.slice(0, i));
        if (i >= answer.length) {
          clearInterval(timer);
          setWorking(false);
        }
      }, 23);
    }, 3000);
  };
  const copyAnswer = async () => {
    try {
      await navigator.clipboard.writeText(stream);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };
  const sidebar = (
    <aside className={`sidebar ${sideOpen ? "shown" : ""}`}>
      <div className="sidebar-top">
        <Logo />
        <button
          className="mobile-close"
          onClick={() => setSideOpen(false)}
          aria-label="关闭菜单"
        >
          <X />
        </button>
      </div>
      <GlassButton
        className="new-chat"
        onClick={() => {
          setView("chat");
          setPrompt("");
          setQuestion("");
          setStream("");
        }}
      >
        <Plus /> 新建对话
      </GlassButton>
      <nav>
        <NavLabel icon={PanelRight}>AI 工作台</NavLabel>
        <NavItem
          icon={MessageCircle}
          active={view === "chat"}
          onClick={() => setView("chat")}
        >
          智能问答
        </NavItem>
        <NavItem
          icon={Library}
          active={view === "knowledge"}
          onClick={() => setView("knowledge")}
        >
          知识库
        </NavItem>
        <NavItem
          icon={FileText}
          active={view === "documents"}
          onClick={() => setView("documents")}
        >
          文档管理
        </NavItem>
        <NavItem
          icon={Search}
          active={view === "retrieval"}
          onClick={() => setView("retrieval")}
        >
          检索测试
        </NavItem>
        <span className="nav-label">历史记录</span>
        <NavItem
          icon={History}
          active={view === "history"}
          onClick={() => setView("history")}
        >
          历史记录
        </NavItem>
        <NavItem
          icon={Star}
          active={view === "favorites"}
          onClick={() => setView("favorites")}
        >
          我的收藏
        </NavItem>
        <span className="nav-label">系统</span>
        <NavItem
          icon={Settings}
          active={view === "settings"}
          onClick={() => setView("settings")}
        >
          系统设置
        </NavItem>
      </nav>
      <div className="profile-wrap">
        <button
          className="profile"
          onClick={() => setProfileOpen((value) => !value)}
        >
          <div className="avatar">{profile.display_name.slice(0, 1) || "张"}</div>
          <div className="profile-meta">
            <b>{profile.display_name}</b>
            <span>{profile.job_title} · {profile.department_name}</span>
          </div>
          <ChevronDown size={17} />
        </button>
        {profileOpen && (
          <div className="profile-menu">
            <div className="profile-menu-summary">
              <div className="avatar">{profile.display_name.slice(0, 1) || "张"}</div>
              <div>
                <b>{profile.display_name}</b>
                <span>{profile.job_title}</span>
                <small>{profile.department_name}</small>
              </div>
            </div>
            <button
              onClick={() => {
                setView("profile");
                setProfileOpen(false);
              }}
            >
              查看个人信息
            </button>
            <button className="profile-logout" onClick={onLogout}>
              退出登录
            </button>
          </div>
        )}
      </div>
    </aside>
  );
  const sources = (
    <aside className={`citations ${sourceOpen ? "shown" : ""}`}>
      <header>
        <div>
          <h2>引用来源</h2>
          <p>每个结论均可溯源至原文</p>
        </div>
        <button
          className="mobile-close"
          onClick={() => setSourceOpen(false)}
          aria-label="关闭引用"
        >
          <X />
        </button>
      </header>
      {citations.map((item, index) => (
        <CitationCard key={item[1]} item={item} index={index} />
      ))}
      <div className="trust">
        <ShieldCheck />
        <div>
          <b>回答依据 5 个知识片段</b>
          <span>
            可信度　<strong>高</strong>
          </span>
        </div>
      </div>
    </aside>
  );
  return (
    <div className={`workspace-shell ${sourceOpen ? "" : "citations-hidden"}`}>
      <button
        className="mobile-trigger left"
        onClick={() => setSideOpen(true)}
        aria-label="打开菜单"
      >
        <PanelRight />
      </button>
      {sidebar}
      <main className="workspace-main">
        <header className="workspace-header">
          <div>
            <p className="back" onClick={onLanding}>
              ← 返回展示页
            </p>
            <h1>企业技术知识助手</h1>
          </div>
          <div className="top-actions">
            <span className="connection">
              <i /> 已连接 12 个知识库
            </span>
            <button
              className="citation-toggle"
              onClick={() => setSourceOpen((value) => !value)}
              aria-label={sourceOpen ? "隐藏引用来源" : "打开引用来源"}
              aria-pressed={sourceOpen}
            >
              <PanelRight />
            </button>
            <Bell />
            <CircleHelp />
          </div>
        </header>
        <div className={`workspace-context ${!stream && !working ? "is-empty" : ""}`}>
          {!stream && !working && (
            <>
              <section className="greeting">
                <div className="greeting-orbit">
                  <span />
                  <span />
                  <span />
                </div>
                <h2>👋 晚上好，今天想了解什么？</h2>
                <p>连接企业文档、Wiki 与代码仓库，获取带依据的技术答案。</p>
              </section>
              <section className="quick-actions">
                {[
                  [MessageCircle, "技术问题", "解答架构、原理与实现等技术问题"],
                  [Wrench, "问题排查", "协助定位与分析系统或业务问题"],
                  [Clipboard, "文档总结", "提炼文档要点，生成结构化摘要"],
                ].map(([Icon, title, copy]) => (
                  <button key={title} onClick={() => setPrompt(title)}>
                    <span className={`action-icon ${title}`}>
                      <Icon />
                    </span>
                    <div>
                      <b>{title}</b>
                      <p>{copy}</p>
                    </div>
                    <ArrowRight />
                  </button>
                ))}
              </section>
            </>
          )}
          <section className="conversation">
            {(stream || working) && (
              <>
                <div className="user-message">{question}</div>
                <div className="answer-row">
                  <div className="bot-avatar">
                    <Bot size={19} />
                  </div>
                  <article className="answer-card">
                    <p className="answer-text">
                      {stream || "正在为你整理企业内部知识…"}
                      {working && <i className="typing" />}
                    </p>
                    {!working && stream && (
                      <div className="answer-actions">
                        <GlassButton onClick={copyAnswer}>
                          <Copy />
                          {copied ? "已复制" : "复制"}
                        </GlassButton>
                        <GlassButton
                          onClick={() =>
                            setPrompt(
                              "基于刚才的回答，请继续说明企业落地时的注意事项。 ",
                            )
                          }
                        >
                          <MessageCircle />
                          继续追问
                        </GlassButton>
                        <GlassButton onClick={() => setSourceOpen(true)}>
                          <BookOpen />
                          查看引用
                        </GlassButton>
                        <GlassButton
                          onClick={() => setFavorited((value) => !value)}
                        >
                          <Heart fill={favorited ? "currentColor" : "none"} />
                          {favorited ? "已收藏" : "收藏"}
                        </GlassButton>
                      </div>
                    )}
                  </article>
                </div>
              </>
            )}
          </section>
          {(stream || working) && <RagProgress stage={stage} />}
        </div>
        <section className="workspace-composer">
          <div className="question-box">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  ask();
                }
              }}
              placeholder="例如：Milvus 为什么适合企业级 RAG？"
              aria-label="技术问题"
            />
            <button onClick={ask} aria-label="发送问题">
              <Send size={20} />
            </button>
          </div>
        </section>
      </main>
      {view === "profile" ? (
        <ProfileOverlay profile={profile} onSave={setProfile} close={() => setView("chat")} />
      ) : (
        view !== "chat" && <FeatureOverlay view={view} close={() => setView("chat")} />
      )}
      <button
        className="mobile-trigger right"
        onClick={() => setSourceOpen(true)}
        aria-label="打开引用"
      >
        <BookOpen />
      </button>
      {sources}
    </div>
  );
}
function Landing({ onEnter, onLogin }) {
  return (
    <div className="landing landing-reference">
      <section className="landing-left">
        <header className="reference-brand">
          <Logo />
          <span className="deploy-tag">企业级 · 私有部署</span>
        </header>
        <main className="reference-copy">
          <p>Enterprise AI Knowledge Workspace</p>
          <h1>
            让企业技术知识
            <br />
            真正可检索
            <br />
            <em>可追溯、可回答</em>
          </h1>
          <div className="copy-detail">
            连接内部文档、Wiki、代码仓库与技术规范，
            <br />
            让可信检索、权限控制与引用溯源贯穿每次回答。
          </div>
          <div className="feature-tags">
            <span>私有化部署</span>
            <span>细粒度权限</span>
            <span>全链路溯源</span>
          </div>
          <div className="reference-cta">
            <GlassButton className="primary" onClick={onEnter}>
              进入 DevMind AI <ArrowRight />
            </GlassButton>
            <button className="watch">
              <span>▶</span>观看演示
            </button>
          </div>
        </main>
        <footer className="reference-foot">
          <span>企业知识基础设施</span>
          <div>
            <b>SSO / RBAC</b>
            <b>审计日志</b>
            <b>多知识库隔离</b>
          </div>
          <small>PDF　WIKI　GIT　API　DATABASE</small>
        </footer>
      </section>
      <section className="landing-right">
        <header className="reference-nav">
          <nav>
            <a>工作空间</a>
            <a>知识库</a>
            <a>安全与权限</a>
            <a>开发者</a>
          </nav>
          <GlassButton onClick={onLogin}>
            登录 <ArrowRight size={15} />
          </GlassButton>
        </header>
        <div className="ambient-orbit" />
        <i className="network-dot d1" />
        <i className="network-dot d2" />
        <i className="network-dot d3" />
        <div className="preview-shell">
          <div className="preview-app">
            <header className="preview-header">
              <Logo compact />
              <span>
                <i /> 已连接 12 个知识库
              </span>
              <div className="preview-avatar">张</div>
            </header>
            <aside className="preview-side">
              <button>＋ 新建对话</button>
              <b>◉　智能问答</b>
              <span>◫　知识库</span>
              <span>▤　文档管理</span>
              <span>⌕　检索测试</span>
              <span>◷　历史记录</span>
              <span>☆　我的收藏</span>
            </aside>
            <main className="preview-main">
              <h2>企业技术知识助手</h2>
              <p>基于内部知识库回答 · 自动检索、重排并引用原文</p>
              <div className="preview-question">
                生产环境如何配置统一身份认证？<i>➤</i>
              </div>
              <div className="preview-rag">
                <small>RAG 检索链路</small>
                <div>
                  <b />
                  检索 <i /> <b />
                  召回 <i /> <b />
                  重排 <i /> <b className="ready">✓</b>生成
                </div>
                <strong>13 片段 → 5 高相关结果</strong>
              </div>
              <article className="preview-answer">
                <b>DevMind AI</b>
                <p>
                  根据《统一身份认证接入规范》与《生产环境部署手册》，推荐采用
                  OIDC + 企业 SSO：
                </p>
                <span>• 身份源：接入企业 IdP，并启用 MFA。</span>
                <span>• 权限：通过 RBAC 映射部门与知识库权限。</span>
                <span>• 审计：记录登录、检索与文档访问事件。</span>
                <footer>复制　　继续追问　　查看引用</footer>
              </article>
            </main>
            <aside className="preview-citations">
              <h3>引用来源</h3>
              <small>点击可定位到原文</small>
              {[
                ["PDF", "身份认证接入规范", "94%"],
                ["MD", "生产环境部署手册", "91%"],
                ["DOC", "研发安全基线", "88%"],
              ].map(([type, name, score]) => (
                <article key={name}>
                  <b className={type}>{type}</b>
                  <strong>{name}</strong>
                  <span>
                    第 18 页 · <em>{score}</em>
                  </span>
                  <p>OIDC 接入应统一使用企业 IdP，并结合 MFA 与角色…</p>
                </article>
              ))}
              <div className="preview-trust">
                <ShieldCheck />
                <span>
                  回答依据 <b>5</b> 个知识片段
                  <br />
                  <small>
                    可信度　<strong>高</strong>
                  </small>
                </span>
              </div>
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
  const submit = (e) => {
    e.preventDefault();
    const valid =
      method === "password"
        ? account.trim() && password
        : phone.trim() && code.trim();
    if (!valid) {
      setError(
        method === "password" ? "请输入账号和密码" : "请输入手机号和验证码",
      );
      return;
    }
    onSuccess();
  };
  const isRegister = mode === "register";
  const switchMethod = () => {
    setMethod((value) => (value === "password" ? "phone" : "password"));
    setError("");
    setCodeSent(false);
  };
  const sendCode = () => {
    if (!phone.trim()) {
      setError("请先输入手机号");
      return;
    }
    setError("");
    setCodeSent(true);
  };
  return (
    <main className="login-page">
      <section className="login-box">
        <div className="login-brand">
          <Logo />
          <h1>{isRegister ? "注册 DevMind AI" : "登录 DevMind AI"}</h1>
          <p>
            {isRegister
              ? "创建企业技术知识工作空间账号"
              : "访问企业内部技术知识工作空间"}
          </p>
        </div>
        <form onSubmit={submit}>
          {method === "password" ? (
            <>
              <label>
                账号 / 邮箱
                <input
                  value={account}
                  onChange={(e) => setAccount(e.target.value)}
                  placeholder="请输入账号或企业邮箱"
                  autoComplete="username"
                />
              </label>
              <label>
                密码
                <span className="password-field">
                  <input
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    type={show ? "text" : "password"}
                    placeholder="请输入密码"
                    autoComplete={
                      isRegister ? "new-password" : "current-password"
                    }
                  />
                  <button
                    type="button"
                    onClick={() => setShow((v) => !v)}
                    aria-label={show ? "隐藏密码" : "显示密码"}
                  >
                    {show ? <EyeOff /> : <Eye />}
                  </button>
                </span>
              </label>
            </>
          ) : (
            <>
              <label>
                手机号
                <input
                  value={phone}
                  onChange={(e) => {
                    setPhone(e.target.value);
                    setCodeSent(false);
                  }}
                  placeholder="请输入手机号"
                  inputMode="tel"
                  autoComplete="tel"
                />
              </label>
              <label>
                验证码
                <span className="code-field">
                  <input
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="请输入验证码"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                  />
                  <button type="button" onClick={sendCode}>
                    {codeSent ? "已发送" : "获取验证码"}
                  </button>
                </span>
              </label>
            </>
          )}
          {error && <p className="login-error">{error}</p>}
          {!isRegister && (
            <div className="login-options">
              <label>
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                />
                记住登录状态
              </label>
              <button type="button">忘记密码？</button>
            </div>
          )}
          {isRegister && (
            <p className="register-note">
              注册即表示你同意 <a>用户协议</a> 与 <a>隐私政策</a>
            </p>
          )}
          <button className="login-submit" type="submit">
            {isRegister ? "注册并进入" : "登录"} <ArrowRight />
          </button>
        </form>
        <div className="login-switch">
          {isRegister ? "已有账号？" : "还没有账号？"}
          <button
            onClick={() => {
              setMode(isRegister ? "login" : "register");
              setError("");
            }}
          >
            {isRegister ? "登录" : "注册账号"}
          </button>
        </div>
        <div className="login-sso">
          <span>其他登录方式</span>
          <button type="button" onClick={switchMethod}>
            {method === "password" ? "手机验证码登录" : "使用账号密码"}{" "}
            <ArrowRight />
          </button>
        </div>
      </section>
      <footer className="login-footer">
        © 2026 DevMind AI　 <a>隐私政策</a> · <a>用户协议</a>
      </footer>
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
  return [
    path,
    (to) => {
      history.pushState({}, "", to);
      setPath(to);
    },
  ];
}
function App() {
  const [path, navigate] = useRoute();
  if (path === "/login")
    return <Login onSuccess={() => navigate("/workspace")} />;
  if (path === "/workspace")
    return (
      <Workspace
        onLanding={() => navigate("/")}
        onLogout={() => navigate("/")}
      />
    );
  return (
    <Landing
      onEnter={() => navigate("/login")}
      onLogin={() => navigate("/login")}
    />
  );
}

createRoot(document.getElementById("root")).render(<App />);
