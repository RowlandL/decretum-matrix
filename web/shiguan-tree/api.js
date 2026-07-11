const SHIGUAN_ADMIN_TOKEN_KEY = "shiguan-admin-token";

function migrateShiguanAdminToken() {
  const url = new URL(window.location.href);
  const queryToken = url.searchParams.get("admin_token") || "";
  if (queryToken) {
    try {
      sessionStorage.setItem(SHIGUAN_ADMIN_TOKEN_KEY, queryToken);
    } catch (_error) {
      window.__shiguanAdminToken = queryToken;
    }
    url.searchParams.delete("admin_token");
    const cleanUrl = `${url.pathname}${url.search}${url.hash}`;
    window.history.replaceState(null, document.title, cleanUrl);
  }
}

function shiguanAdminToken() {
  try {
    return sessionStorage.getItem(SHIGUAN_ADMIN_TOKEN_KEY)
      || window.__shiguanAdminToken
      || "";
  } catch (_error) {
    return window.__shiguanAdminToken || "";
  }
}

migrateShiguanAdminToken();

async function shiguanApi(path, options = {}) {
  const { headers: optionHeaders = {}, ...fetchOptions } = options;
  const method = String(fetchOptions.method || "GET").toUpperCase();
  const headers = { Accept: "application/json", ...optionHeaders };
  if (!['GET', 'HEAD'].includes(method)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
    headers["X-Shiguan-Admin-Request"] = "1";
  }
  const adminToken = shiguanAdminToken();
  if (adminToken) {
    headers["X-Shiguan-Admin-Token"] = adminToken;
  }
  const response = await fetch(path, {
    headers,
    cache: "no-store",
    credentials: "same-origin",
    referrerPolicy: "no-referrer",
    ...fetchOptions,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || JSON.stringify(body) || response.statusText);
  }
  return body;
}
