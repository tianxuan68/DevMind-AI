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
    let message = data?.detail || (typeof data === "string" ? data : null);
    if (!message && response.status >= 500) {
      message = `服务端错误（HTTP ${response.status}）`;
    }
    if (!message) message = `请求失败（${response.status}）`;
    if (typeof message !== "string") message = JSON.stringify(message);
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data;
}

export function uploadFormData(path, formData, { onProgress, auth = true, timeoutMs = 120000 } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const timer = setTimeout(() => {
      xhr.abort();
      reject(new Error("上传超时，请确认后端已启动并重试"));
    }, timeoutMs);

    xhr.open("POST", `${API_BASE_URL}${path}`);
    if (auth) {
      const token = getToken();
      if (!token) {
        clearTimeout(timer);
        reject(new Error("请先登录"));
        return;
      }
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }
    xhr.upload.onloadstart = () => {
      if (onProgress) onProgress(1);
    };
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.max(1, Math.round((event.loaded / event.total) * 100)));
      }
    };
    xhr.onload = () => {
      clearTimeout(timer);
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        data = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        if (onProgress) onProgress(100);
        resolve(data);
        return;
      }
      handleAuthError(xhr.status);
      const message = data?.detail || `上传失败（${xhr.status}）`;
      reject(new Error(typeof message === "string" ? message : JSON.stringify(message)));
    };
    xhr.onerror = () => {
      clearTimeout(timer);
      reject(new Error("网络错误：请确认 Nginx/后端 API 可访问"));
    };
    xhr.onabort = () => {
      clearTimeout(timer);
      reject(new Error("上传已取消或超时"));
    };
    xhr.send(formData);
  });
}

/** 浏览器直传 OSS 预签名 URL（可获取真实上传进度） */
export function uploadToPresignedUrl(url, file, { headers = {}, onProgress, timeoutMs = 600000 } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const timer = setTimeout(() => {
      xhr.abort();
      reject(new Error("OSS 上传超时"));
    }, timeoutMs);

    xhr.open("PUT", url);
    Object.entries(headers || {}).forEach(([key, value]) => {
      if (value != null && value !== "") xhr.setRequestHeader(key, value);
    });
    xhr.upload.onloadstart = () => onProgress?.(1);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.max(1, Math.round((event.loaded / event.total) * 100)));
      }
    };
    xhr.onload = () => {
      clearTimeout(timer);
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100);
        resolve({ status: xhr.status });
        return;
      }
      reject(new Error(`OSS 上传失败（${xhr.status}）`));
    };
    xhr.onerror = () => {
      clearTimeout(timer);
      reject(new Error("OSS 上传网络错误，请检查 Bucket CORS 配置"));
    };
    xhr.onabort = () => {
      clearTimeout(timer);
      reject(new Error("OSS 上传已取消或超时"));
    };
    xhr.send(file);
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
  initOssUpload: (body) => request("/api/knowledge/docs/oss/init", { method: "POST", body, auth: true }),
  completeOssUpload: (docId) => request(`/api/knowledge/docs/${docId}/oss/complete`, { method: "POST", auth: true }),
  updateDoc: (id, body) => request(`/api/knowledge/docs/${id}`, { method: "PATCH", body, auth: true }),
  deleteDoc: (id) => request(`/api/knowledge/docs/${id}`, { method: "DELETE", auth: true }),
  detail: (id) => request(`/api/knowledge/docs/${id}`, { auth: true }),
  listChunks: (docId) => request(`/api/knowledge/docs/${docId}/chunks`, { auth: true }),
  searchRetrieval: (body) => request("/api/knowledge/retrieval/search", { method: "POST", body, auth: true }),
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

// ---------- 智能问答（T8：query / stream / feedback） ----------
export function getWsBaseUrl() {
  if (API_BASE_URL) {
    return API_BASE_URL.replace(/^http/, "ws");
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}`;
}

/**
 * WS /api/stream 流式问答。
 * 时序：auth → start → query → token* → end
 */
export function streamChat({
  query,
  sessionId = null,
  sourceFilter = null,
  onToken,
  timeoutMs = 180000,
} = {}) {
  const token = getToken();
  if (!token) {
    return Promise.reject(new Error("请先登录"));
  }

  return new Promise((resolve, reject) => {
    let settled = false;
    let answer = "";
    let activeSessionId = sessionId;
    const ws = new WebSocket(`${getWsBaseUrl()}/api/stream`);

    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {
        ws.close();
      } catch {
        // ignore
      }
      fn(value);
    };

    const timer = setTimeout(() => {
      finish(reject, new Error("流式问答超时，请稍后重试"));
    }, timeoutMs);

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "auth", token }));
    };

    ws.onmessage = (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch {
        finish(reject, new Error("流式响应格式错误"));
        return;
      }

      if (msg.type === "start") {
        activeSessionId = sessionId || msg.session_id || activeSessionId;
        ws.send(JSON.stringify({
          type: "query",
          query,
          session_id: activeSessionId,
          source_filter: sourceFilter || null,
        }));
        return;
      }

      if (msg.type === "token") {
        const piece = msg.token || "";
        answer += piece;
        if (onToken) onToken(piece, answer);
        return;
      }

      if (msg.type === "end") {
        finish(resolve, {
          answer,
          sources: msg.sources || [],
          session_id: activeSessionId,
          need_human: Boolean(msg.need_human),
          is_complete: msg.is_complete !== false,
          processing_time: msg.processing_time,
        });
        return;
      }

      if (msg.type === "error") {
        const errText = msg.error || "流式问答失败";
        if (/未认证|token|401/i.test(errText)) {
          handleAuthError(401);
        }
        finish(reject, new Error(errText));
      }
    };

    ws.onerror = () => {
      finish(reject, new Error("WebSocket 连接失败，请确认后端已启动且代理支持 WS"));
    };

    ws.onclose = () => {
      if (!settled) {
        finish(reject, new Error("WebSocket 连接已关闭"));
      }
    };
  });
}

export const chatApi = {
  createSession: () => request("/api/create_session", { method: "POST", auth: true }),
  query: (body) => request("/api/query", { method: "POST", body, auth: true }),
  feedback: (body) => request("/api/feedback", { method: "POST", body, auth: true }),
  stream: streamChat,
};

// ---------- 客户端启动配置 ----------
export const bootstrapApi = {
  get: () => request("/api/client/bootstrap"),
};
