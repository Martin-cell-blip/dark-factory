// The HTTP API from the browser. Every call settles as one of three outcomes:
//   ok        - 2xx, with the parsed body
//   refused   - a 4xx the service answered in its error envelope (a confirmed "no")
//   uncertain - no answer, a 5xx or an unreadable one: the write may or may not have happened

const TOKEN_KEY = "pocketful.token";

export const session = {
  get token() { return localStorage.getItem(TOKEN_KEY); },
  save(token) { localStorage.setItem(TOKEN_KEY, token); },
  clear() { localStorage.removeItem(TOKEN_KEY); },
};

// Idempotency keys. crypto.getRandomValues works outside secure contexts too.
export function newKey() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function call(method, path, { body, key, signedIn = true } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (signedIn && session.token) headers.Authorization = `Bearer ${session.token}`;
  if (key) headers["Idempotency-Key"] = key;
  let response;
  try {
    response = await fetch(path, {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    return { kind: "uncertain" };
  }
  if (response.status >= 500) return { kind: "uncertain" };
  let data = null;
  if (response.status !== 204) {
    try {
      data = await response.json();
    } catch {
      return { kind: "uncertain" };
    }
  }
  if (response.ok) return { kind: "ok", status: response.status, data };
  if (response.status === 401 && signedIn) {
    session.clear();
    location.assign("/login");
  }
  const error = (data && data.error) || {};
  return { kind: "refused", status: response.status, code: error.code || "", message: error.message || "" };
}

// Several reads at once; ok only when every one of them is.
export async function readAll(paths) {
  const results = await Promise.all(paths.map((path) => call("GET", path)));
  if (results.every((r) => r.kind === "ok")) return { ok: true, data: results.map((r) => r.data) };
  return { ok: false };
}

// "Latest refresh wins": a response to an earlier refresh never overwrites a later one,
// whatever order the responses arrive in.
export function latestWins(load, apply, fail) {
  let issued = 0;
  return async function refresh() {
    const ticket = ++issued;
    const result = await load();
    if (ticket !== issued) return;
    if (result.ok) apply(result.data);
    else fail();
  };
}
