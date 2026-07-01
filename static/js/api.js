function buildApiError(data, status) {
  const detail = data?.detail;
  const message = typeof detail === "object" && detail !== null
    ? detail.message || `HTTP ${status}`
    : detail || data?.message || `HTTP ${status}`;
  const err = new Error(String(message));
  err.status = status;
  err.detail = detail;
  if (typeof detail === "object" && detail !== null) {
    err.category = detail.category || "";
    err.code = detail.code || "";
    err.suggestion = detail.suggestion || "";
  }
  return err;
}

export async function fetchJson(url) {
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw buildApiError(data, res.status);
  return data;
}

export async function postJson(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw buildApiError(data, res.status);
  return data;
}

export async function postForm(url, formData) {
  const res = await fetch(url, {
    method: "POST",
    body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw buildApiError(data, res.status);
  return data;
}
