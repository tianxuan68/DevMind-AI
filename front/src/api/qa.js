// 后端 API 封装：所有请求都走这里，组件里不直接写 fetch。
import { API_BASE_URL } from "../utils/constants";

const TOKEN_KEY = "devmind_token";
const USER_KEY = "devmind_user";

// ---------- 登录状态存储 ----------
export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getStoredUser() {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

// ---------- 通用请求 ----------
async function request(path, { method = "GET", body, auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const token = getToken();
    if (!token) throw new Error("请先登录");
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message = data?.detail || `请求失败（${response.status}）`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data;
}

// ---------- 认证接口 ----------
export const authApi = {
  sendCode: (phone) => request("/api/auth/send-code", { method: "POST", body: { phone } }),
  register: (payload) => request("/api/auth/register", { method: "POST", body: payload }),
  login: (account, password) => request("/api/auth/login", { method: "POST", body: { account, password } }),
  smsLogin: (phone, sms_code) => request("/api/auth/login/sms", { method: "POST", body: { phone, sms_code } }),
  logout: () => request("/api/auth/logout", { method: "POST", auth: true }),
  me: () => request("/api/user/me", { auth: true }),
};

// ---------- 知识库接口 ----------
export const knowledgeApi = {
  list: (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") query.set(key, value);
    });
    return request(`/api/knowledge/docs?${query.toString()}`);
  },
  detail: (id) => request(`/api/knowledge/docs/${id}`),
};

// ---------- FAQ 接口 ----------
export const faqApi = {
  list: (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") query.set(key, value);
    });
    return request(`/api/faq?${query.toString()}`);
  },
  detail: (id) => request(`/api/faq/${id}`),
  search: (question) => request("/api/faq/search", { method: "POST", body: { question }, auth: true }),
};

// ---------- 客户端启动配置 ----------
export const bootstrapApi = {
  get: () => request("/api/client/bootstrap"),
};
