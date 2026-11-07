const BASE = "/api";
let token = localStorage.getItem("lg_token") || "";

export const hasToken = () => Boolean(token);

export function setToken(t) {
  token = t || "";
  if (token) localStorage.setItem("lg_token", token);
  else localStorage.removeItem("lg_token");
}

async function request(method, path, body, isForm = false) {
  const headers = {};
  if (token) headers.Authorization = "Bearer " + token;
  let payload;
  if (body !== undefined) {
    if (isForm) payload = body;
    else {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
  }
  const res = await fetch(BASE + path, { method, headers, body: payload });
  if (res.status === 401 && token) {
    setToken("");
    window.dispatchEvent(new Event("lg-logout"));
  }
  if (!res.ok) {
    let err = res.statusText;
    try {
      err = (await res.json()).error || err;
    } catch (_) {
      /* ignore */
    }
    throw new Error(err);
  }
  return res;
}

const json = async (...args) => (await request(...args)).json();

export const api = {
  get: (p) => json("GET", p),
  post: (p, b) => json("POST", p, b ?? {}),
  put: (p, b) => json("PUT", p, b ?? {}),
  patch: (p, b) => json("PATCH", p, b ?? {}),
  del: (p) => json("DELETE", p),
  postForm: (p, form) => json("POST", p, form, true),
  async download(path, filename) {
    const res = await request("GET", path);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};
