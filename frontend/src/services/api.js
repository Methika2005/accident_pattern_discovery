
const API_BASE_URL = "http://127.0.0.1:5000";

async function request(endpoint, options = {}) {
  let response;

  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new Error(
      "Cannot connect to Flask. Check that the backend is running."
    );
  }

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      data.error || data.message || `Request failed (${response.status})`
    );
  }

  return data;
}

export function checkHealth() {
  return request("/api/health");
}

export function getDatasetStats() {
  return request("/api/dataset/stats");
}

export function getDatasetPreview(n = 10) {
  return request(`/api/dataset/preview?n=${n}`);
}

export function minePatterns({
  min_support,
  min_confidence,
  exclude = [],
  max_k = 4,
}) {
  return request("/api/mine", {
    method: "POST",
    body: JSON.stringify({
      min_support,
      min_confidence,
      exclude,
      max_k,
    }),
  });
}
