import { useState } from "react";
import AuthPage from "./components/AuthPage";
import ChatWindow from "./components/ChatWindow";
import FaqPage from "./components/FaqPage";
import KnowledgePage from "./components/KnowledgePage";
import { authApi, clearAuth, getStoredUser } from "./api/qa";
import "./styles.css";

export default function App() {
  const [user, setUser] = useState(getStoredUser());
  const [page, setPage] = useState("chat");

  async function handleLogout() {
    try {
      await authApi.logout();
    } catch {
      // 即使后端退出失败，也清除本地登录状态
    }
    clearAuth();
    setUser(null);
  }

  if (!user) {
    return <AuthPage onLogin={setUser} />;
  }

  return (
    <div className="layout">
      <header className="header">
        <h1>DevMind-AI</h1>
        <nav>
          <button className={page === "chat" ? "active" : ""} onClick={() => setPage("chat")}>智能问答</button>
          <button className={page === "faq" ? "active" : ""} onClick={() => setPage("faq")}>高频FAQ</button>
          <button className={page === "knowledge" ? "active" : ""} onClick={() => setPage("knowledge")}>知识库</button>
          <button className={page === "me" ? "active" : ""} onClick={() => setPage("me")}>我的</button>
        </nav>
        <div className="user-box">
          <span>{user.nickname || user.username}</span>
          <button onClick={handleLogout}>退出</button>
        </div>
      </header>

      <main>
        {page === "chat" && <ChatWindow />}
        {page === "faq" && <FaqPage />}
        {page === "knowledge" && <KnowledgePage />}
        {page === "me" && (
          <div className="page">
            <h2>我的信息</h2>
            <p>用户名：{user.username}</p>
            <p>昵称：{user.nickname || "-"}</p>
            <p>手机号：{user.phone || "-"}</p>
            <p>团队：{user.team || "-"}</p>
            <p>权限等级：{user.security_level || "-"}</p>
          </div>
        )}
      </main>
    </div>
  );
}
