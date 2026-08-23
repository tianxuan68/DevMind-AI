// 后端 API 封装：所有请求都走这里，组件里不直接写 fetch。
import { API_BASE_URL } from "../utils/constants";

const TOKEN_KEY = "devmind_token";
const USER_KEY = "devmind_user";

let onUnauthorized = null;

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

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

function handleAuthError(status) {
  if (status === 401 && onUnauthorized) {
    clearAuth();
    onUnauthorized();
  }
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
    handleAuthError(response.status);
    let message = data?.detail || `请求失败（${response.status}）`;
    if (typeof message !== "string") message = JSON.stringify(message);
    if (response.status >= 500 && !data?.detail) {
      message = "服务端错误：请确认后端已启动，且已执行 sql/schema.sql 初始化数据库";
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data;
}

export function uploadFormData(path, formData, { onProgress, auth = true } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}${path}`);
    if (auth) {
      const token = getToken();
      if (!token) {
        reject(new Error("请先登录"));
        return;
      }
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        data = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data);
        return;
      }
      handleAuthError(xhr.status);
      const message = data?.detail || `上传失败（${xhr.status}）`;
      reject(new Error(typeof message === "string" ? message : JSON.stringify(message)));
    };
    xhr.onerror = () => reject(new Error("网络错误，上传失败"));
    xhr.send(formData);
  });
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
  listBases: () => request("/api/knowledge/bases", { auth: true }),
  createBase: (body) => request("/api/knowledge/bases", { method: "POST", body, auth: true }),
  updateBase: (id, body) => request(`/api/knowledge/bases/${id}`, { method: "PATCH", body, auth: true }),
  deleteBase: (id) => request(`/api/knowledge/bases/${id}`, { method: "DELETE", auth: true }),
  listDocs: (params = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") query.set(key, value);
    });
    return request(`/api/knowledge/docs?${query.toString()}`, { auth: true });
  },
  uploadDoc: (kbId, file, onProgress) => {
    const formData = new FormData();
    formData.append("knowledge_base_id", String(kbId));
    formData.append("file", file);
    return uploadFormData("/api/knowledge/docs", formData, { onProgress, auth: true });
  },
  updateDoc: (id, body) => request(`/api/knowledge/docs/${id}`, { method: "PATCH", body, auth: true }),
  deleteDoc: (id) => request(`/api/knowledge/docs/${id}`, { method: "DELETE", auth: true }),
  detail: (id) => request(`/api/knowledge/docs/${id}`, { auth: true }),
  /** @deprecated 兼容旧组件，请使用 listDocs */
  list: (params = {}) => knowledgeApi.listDocs(params),
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
