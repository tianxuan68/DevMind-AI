import React, { useEffect, useState } from "react";
import { ArrowRight, Eye, EyeOff } from "lucide-react";
import { authApi, setAuth } from "../api/qa";

const DEFAULT_SEND_INTERVAL = 60;

export default function LoginPage({ onSuccess, onNavigate }) {
  const [show, setShow] = useState(false);
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [remember, setRemember] = useState(false);
  const [agreeTerms, setAgreeTerms] = useState(false);
  const [error, setError] = useState("");
  const [method, setMethod] = useState("phone");
  const [mode, setMode] = useState("login");
  const [codeCountdown, setCodeCountdown] = useState(0);
  const [sendingCode, setSendingCode] = useState(false);
  const [loading, setLoading] = useState(false);

  const isRegister = mode === "register";

  useEffect(() => {
    if (codeCountdown <= 0) return undefined;
    const timer = window.setInterval(() => {
      setCodeCountdown((prev) => (prev <= 1 ? 0 : prev - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [codeCountdown]);

  function openLegal(path, event) {
    event.preventDefault();
    event.stopPropagation();
    onNavigate?.(path);
  }

  function resetCodeState() {
    setCodeCountdown(0);
    setCode("");
  }

  function switchMethod(next) {
    setMethod(next);
    setError("");
    resetCodeState();
  }

  function handlePhoneChange(value) {
    setPhone(value);
    resetCodeState();
  }

  async function sendCode() {
    if (!phone.trim()) { setError("请先输入手机号"); return; }
    if (codeCountdown > 0 || sendingCode) return;
    setError("");
    setSendingCode(true);
    try {
      const data = await authApi.sendCode(phone.trim());
      setCodeCountdown(data.send_interval ?? DEFAULT_SEND_INTERVAL);
    } catch (err) {
      setError(err.message);
    } finally {
      setSendingCode(false);
    }
  }

  async function submit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      let data;
      if (isRegister) {
        if (!agreeTerms) {
          setError("请先阅读并同意用户协议与隐私政策");
          return;
        }
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

  const codeButtonLabel = sendingCode
    ? "发送中…"
    : codeCountdown > 0
      ? `${codeCountdown}s后重发`
      : "获取验证码";

  const codeField = (
    <span className="code-field">
      <input
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder="请输入验证码"
        inputMode="numeric"
        autoComplete="one-time-code"
      />
      <button
        type="button"
        onClick={sendCode}
        disabled={codeCountdown > 0 || sendingCode}
      >
        {codeButtonLabel}
      </button>
    </span>
  );

  return (
    <main className="login-page">
      <section className="login-box">
        <div className="login-brand">
          <h1 className="login-brand-title" aria-label="DevMind AI">
            <svg className="login-brand-icon" viewBox="0 0 64 56" aria-hidden="true">
              <path d="M32 8 13 43M32 8l19 35M13 43h38" />
              <circle cx="32" cy="8" r="7" />
              <circle cx="13" cy="43" r="6" />
              <circle cx="51" cy="43" r="6" />
              <circle className="logo-dot" cx="32" cy="8" r="2.5" />
            </svg>
            <span>{isRegister ? "注册" : "登录"} DevMind <b>AI</b></span>
          </h1>
        </div>

        {!isRegister && (
          <div className="login-tabs" role="tablist" aria-label="登录方式">
            <button
              type="button"
              role="tab"
              aria-selected={method === "phone"}
              className={method === "phone" ? "active" : ""}
              onClick={() => switchMethod("phone")}
            >
              手机验证码登录
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={method === "password"}
              className={method === "password" ? "active" : ""}
              onClick={() => switchMethod("password")}
            >
              账号密码登录
            </button>
          </div>
        )}

        <form onSubmit={submit}>
          {isRegister ? (
            <>
              <label>用户名<input value={account} onChange={(e) => setAccount(e.target.value)} placeholder="请输入用户名" autoComplete="username" /></label>
              <label>密码<span className="password-field"><input value={password} onChange={(e) => setPassword(e.target.value)} type={show ? "text" : "password"} placeholder="请输入密码" autoComplete="new-password" /><button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? "隐藏密码" : "显示密码"}>{show ? <EyeOff /> : <Eye />}</button></span></label>
              <label>手机号<input value={phone} onChange={(e) => handlePhoneChange(e.target.value)} placeholder="请输入手机号" inputMode="tel" autoComplete="tel" /></label>
              <label>验证码{codeField}</label>
            </>
          ) : method === "password" ? (
            <>
              <label>账号 / 邮箱<input value={account} onChange={(e) => setAccount(e.target.value)} placeholder="请输入账号或企业邮箱" autoComplete="username" /></label>
              <label>密码<span className="password-field"><input value={password} onChange={(e) => setPassword(e.target.value)} type={show ? "text" : "password"} placeholder="请输入密码" autoComplete="current-password" /><button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? "隐藏密码" : "显示密码"}>{show ? <EyeOff /> : <Eye />}</button></span></label>
            </>
          ) : (
            <>
              <label>手机号<input value={phone} onChange={(e) => handlePhoneChange(e.target.value)} placeholder="请输入手机号" inputMode="tel" autoComplete="tel" /></label>
              <label>验证码{codeField}</label>
            </>
          )}

          {error && <p className="login-error">{error}</p>}

          {!isRegister && method === "password" && (
            <div className="login-options">
              <label><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />记住登录状态</label>
              <button type="button">忘记密码？</button>
            </div>
          )}

          {isRegister && (
            <label className="register-agree">
              <input type="checkbox" checked={agreeTerms} onChange={(e) => setAgreeTerms(e.target.checked)} />
              <span>注册即表示你同意 <a href="/terms" onClick={(e) => openLegal("/terms", e)}>用户协议</a> 与 <a href="/privacy" onClick={(e) => openLegal("/privacy", e)}>隐私政策</a></span>
            </label>
          )}

          <button className="login-submit" type="submit" disabled={loading}>
            {loading ? "处理中…" : isRegister ? "注册并进入" : "登录"} <ArrowRight />
          </button>
        </form>

        {import.meta.env.DEV && !isRegister && method === "password" && (
          <p className="login-dev-hint">开发测试账号：admin / 123456</p>
        )}

        <div className="login-switch">
          <span>{isRegister ? "已有账号？" : "还没有账号？"}</span>
          <button type="button" onClick={() => { setMode(isRegister ? "login" : "register"); setError(""); setAgreeTerms(false); resetCodeState(); }}>
            {isRegister ? "登录" : "注册账号"}
          </button>
        </div>
      </section>

      <footer className="login-footer">
        © 2026 DevMind AI　
        <a href="/privacy" onClick={(e) => openLegal("/privacy", e)}>隐私政策</a> ·
        <a href="/terms" onClick={(e) => openLegal("/terms", e)}>用户协议</a>
      </footer>
    </main>
  );
}
