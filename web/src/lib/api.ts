import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTrackerPause } from "./trackerPause";

const runtimeHost =
  typeof window !== "undefined" && window.location.hostname
    ? window.location.hostname
    : "127.0.0.1";
const API_BASE =
  import.meta.env.VITE_API_BASE || `http://${runtimeHost}:8000`;
const ENV_API_KEY = import.meta.env.VITE_API_KEY;
const LOCAL_KEY = "clear_api_key";
const SESSION_KEY = "clear_api_key_session";
const ENCRYPTED_PREFIX = "enc:v1:";
const CRYPTO_DB_NAME = "clear_browser_keys";
const CRYPTO_DB_STORE = "keys";
const CRYPTO_KEY_ID = "api-key-encryption-v1";

let sessionCryptoKeyPromise: Promise<CryptoKey> | null = null;
let runtimeApiKey: string | null = null;
let decryptedApiKey: string | null | undefined;

function openCryptoKeyDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("Encrypted browser storage is unavailable."));
      return;
    }
    const request = indexedDB.open(CRYPTO_DB_NAME, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(CRYPTO_DB_STORE)) {
        request.result.createObjectStore(CRYPTO_DB_STORE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Could not open encrypted browser storage."));
  });
}

async function getOrCreateStoredCryptoKey(): Promise<CryptoKey> {
  const generated = await crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  );
  const database = await openCryptoKeyDatabase();
  try {
    return await new Promise((resolve, reject) => {
      let selected: CryptoKey | null = null;
      const transaction = database.transaction(CRYPTO_DB_STORE, "readwrite");
      const request = transaction.objectStore(CRYPTO_DB_STORE).get(CRYPTO_KEY_ID);
      request.onsuccess = () => {
        const existing = (request.result as CryptoKey | undefined) || null;
        selected = existing || generated;
        if (!existing) {
          transaction.objectStore(CRYPTO_DB_STORE).put(generated, CRYPTO_KEY_ID);
        }
      };
      request.onerror = () => reject(request.error || new Error("Could not read encrypted browser storage."));
      transaction.oncomplete = () => {
        if (selected) resolve(selected);
        else reject(new Error("Encrypted browser storage returned no key."));
      };
      transaction.onerror = () => reject(transaction.error || new Error("Could not save encrypted browser storage."));
      transaction.onabort = () => reject(transaction.error || new Error("Encrypted browser storage was cancelled."));
    });
  } finally {
    database.close();
  }
}

function getStorageCryptoKey(): Promise<CryptoKey> {
  if (!sessionCryptoKeyPromise) {
    sessionCryptoKeyPromise = getOrCreateStoredCryptoKey().catch((error) => {
      sessionCryptoKeyPromise = null;
      throw error;
    });
  }
  return sessionCryptoKeyPromise;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

function base64ToBytes(base64: string): Uint8Array<ArrayBuffer> {
  const binary = atob(base64);
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function encryptApiKey(value: string): Promise<string> {
  const key = await getStorageCryptoKey();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plaintext = new TextEncoder().encode(value);
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plaintext);
  return `${ENCRYPTED_PREFIX}${bytesToBase64(iv)}:${bytesToBase64(new Uint8Array(ciphertext))}`;
}

async function decryptApiKey(payload: string): Promise<string | null> {
  if (!payload.startsWith(ENCRYPTED_PREFIX)) {
    throw new Error("Unsupported API key storage format.");
  }
  const encoded = payload.slice(ENCRYPTED_PREFIX.length);
  const [ivB64, dataB64] = encoded.split(":");
  if (!ivB64 || !dataB64) return null;
  const iv = base64ToBytes(ivB64);
  const data = base64ToBytes(dataB64);
  const key = await getStorageCryptoKey();
  const plaintext = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, data);
  return new TextDecoder().decode(plaintext);
}

export type ApiKeyScope = "memory" | "session" | "local" | "env" | "none";

export function getApiBase(): string {
  return API_BASE;
}

type CacheEntry<T> = {
  ts: number;
  ttl: number;
  data: T;
};

type ApiMeta = {
  warnings?: string[];
};

const cache = new Map<string, CacheEntry<unknown>>();
const inflight = new Map<string, Promise<unknown>>();

function cacheKey(path: string) {
  return `${API_BASE}${path}`;
}

export function invalidateApiCache(pathPrefix?: string) {
  if (!pathPrefix) {
    cache.clear();
    return;
  }
  const match = cacheKey(pathPrefix);
  for (const key of [...cache.keys()]) {
    if (key.startsWith(match) || key.includes(pathPrefix)) cache.delete(key);
  }
}

export function extractWarnings(payload: unknown): string[] {
  if (!payload || typeof payload !== "object") return [];
  const meta = (payload as { meta?: ApiMeta }).meta;
  if (!meta || !Array.isArray(meta.warnings)) return [];
  return meta.warnings.filter((item): item is string => typeof item === "string");
}

async function parseJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  try {
    return JSON.parse(text) as T;
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Unknown error";
    throw new Error(`Invalid JSON response: ${detail}`);
  }
}

export async function getApiKey(): Promise<string | null> {
  if (runtimeApiKey) return runtimeApiKey;
  if (decryptedApiKey !== undefined) return decryptedApiKey;
  try {
    const sessionValue = sessionStorage.getItem(SESSION_KEY);
    if (sessionValue) {
      try {
        const decrypted = await decryptApiKey(sessionValue);
        if (decrypted) {
          decryptedApiKey = decrypted;
          return decrypted;
        }
      } catch {
        sessionStorage.removeItem(SESSION_KEY);
      }
    }

  } catch {
    // Continue to device storage when session storage is blocked.
  }

  try {
    const localValue = localStorage.getItem(LOCAL_KEY);
    if (localValue) {
      try {
        const decrypted = await decryptApiKey(localValue);
        if (decrypted) {
          decryptedApiKey = decrypted;
          return decrypted;
        }
      } catch {
        localStorage.removeItem(LOCAL_KEY);
      }
    }

  } catch {
    // Environment configuration remains available when device storage is blocked.
  }
  const resolved = ENV_API_KEY || null;
  decryptedApiKey = resolved;
  return resolved;
}

export function getApiKeyScope(): ApiKeyScope {
  if (runtimeApiKey) return "memory";
  try {
    if (sessionStorage.getItem(SESSION_KEY)) return "session";
  } catch {
    // Continue to device storage when session storage is blocked.
  }
  try {
    if (localStorage.getItem(LOCAL_KEY)) return "local";
  } catch {
    // Environment configuration remains available when device storage is blocked.
  }
  return ENV_API_KEY ? "env" : "none";
}

export async function setApiKey(
  value: string,
  options: { persist?: boolean } = {}
): Promise<ApiKeyScope> {
  try {
    const encrypted = await encryptApiKey(value);
    if (options.persist) {
      localStorage.setItem(LOCAL_KEY, encrypted);
      try {
        sessionStorage.removeItem(SESSION_KEY);
      } catch {
        // The newly persisted key remains authoritative.
      }
      runtimeApiKey = null;
      decryptedApiKey = undefined;
      return "local";
    } else {
      sessionStorage.setItem(SESSION_KEY, encrypted);
      try {
        localStorage.removeItem(LOCAL_KEY);
      } catch {
        // The newly saved session key remains authoritative.
      }
      runtimeApiKey = null;
      decryptedApiKey = undefined;
      return "session";
    }
  } catch {
    if (options.persist) {
      throw new Error(
        "The key could not be stored on this device. Browser encrypted storage may be unavailable; the previous key was left unchanged."
      );
    }
    runtimeApiKey = value;
    try {
      localStorage.removeItem(LOCAL_KEY);
    } catch {
      // Page-memory storage remains available even when browser storage is blocked.
    }
    try {
      sessionStorage.removeItem(SESSION_KEY);
    } catch {
      // Page-memory storage remains available even when browser storage is blocked.
    }
    return "memory";
  }
}

export function clearApiKey(): void {
  runtimeApiKey = null;
  decryptedApiKey = undefined;
  try {
    localStorage.removeItem(LOCAL_KEY);
  } catch {
    // Continue clearing independent storage scopes.
  }
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // Page memory has still been cleared.
  }
}

export function getAuthHint(): string {
  const scope = getApiKeyScope();
  if (scope === "env") {
    return "API key is set in the environment. Verify CLEAR_WEB_API_KEY matches.";
  }
  if (scope === "local" || scope === "session") {
    return "Check the API key in System settings or clear and re-enter it.";
  }
  if (scope === "memory") {
    return "The API key is active for this page only. Re-enter it after a reload.";
  }
  return "Set an API key in System settings if CLEAR_WEB_API_KEY is enabled.";
}

function _isAbortError(err: unknown): boolean {
  if (!err) return false;
  if (typeof DOMException !== "undefined" && err instanceof DOMException && err.name === "AbortError") {
    return true;
  }
  if (err instanceof Error) {
    if (err.name === "AbortError") return true;
    return /abort/i.test(err.message);
  }
  return false;
}

function formatApiError(status: number): string {
  if (status === 401 || status === 403) {
    return `API ${status}: authentication required. ${getAuthHint()}`;
  }
  return `API ${status}`;
}

async function responseError(response: Response): Promise<Error> {
  const prefix = formatApiError(response.status);
  if (response.status === 401 || response.status === 403 || response.status >= 500) return new Error(prefix);
  try {
    const payload = await response.json();
    const detail = payload.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail)
      ? detail.map((item: { field?: string; message?: string; loc?: string[]; msg?: string }) => `${item.field || item.loc?.filter(part => part !== "body").join(".") || "Input"}: ${item.message || item.msg || "Invalid value"}`).join("; ")
      : detail?.message;
    return new Error(message ? `${prefix}: ${message}` : prefix);
  } catch { return new Error(prefix); }
}

export async function apiGet<T>(path: string, ttl = 0, signal?: AbortSignal): Promise<T> {
  const key = cacheKey(path);
  if (ttl > 0) {
    const existing = cache.get(key) as CacheEntry<T> | undefined;
    if (existing && Date.now() - existing.ts < existing.ttl) {
      return existing.data;
    }
  }
  if (signal?.aborted) {
    throw new DOMException("Aborted", "AbortError");
  }
  let pending = inflight.get(key) as Promise<T> | undefined;
  if (!pending) {
    pending = (async () => {
      const headers: Record<string, string> = {};
      const apiKey = await getApiKey();
      if (apiKey) {
        headers["X-API-Key"] = apiKey;
      }
      let response: Response;
      try {
        response = await fetch(`${API_BASE}${path}`, { headers });
      } catch (err) {
        const detail = err instanceof Error ? err.message : "Network error";
        const cspHint = /failed to fetch|networkerror/i.test(detail)
          ? " Check CSP connect-src allows the API base."
          : "";
        throw new Error(`API unreachable at ${API_BASE}. ${detail}${cspHint}`);
      }
      if (!response.ok) {
        throw await responseError(response);
      }
      const payload = await parseJson<T>(response);
      if (ttl > 0) {
        cache.set(key, { ts: Date.now(), ttl, data: payload });
      }
      return payload;
    })().finally(() => {
      inflight.delete(key);
    });
    inflight.set(key, pending);
  }
  if (!signal) return pending;
  return new Promise<T>((resolve, reject) => {
    const abort = () => reject(new DOMException("Aborted", "AbortError"));
    if (signal.aborted) {
      abort();
      return;
    }
    signal.addEventListener("abort", abort, { once: true });
    pending!.then((value) => {
      signal.removeEventListener("abort", abort);
      resolve(value);
    }, (error) => {
      signal.removeEventListener("abort", abort);
      reject(error);
    });
  });
}

type WriteMethod = "POST" | "PATCH" | "PUT" | "DELETE";

async function apiWrite<T>(path: string, method: WriteMethod, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (path === "/api/application/shutdown") headers["X-Clear-Shutdown"] = "confirm";
  const apiKey = await getApiKey();
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Network error";
    throw new Error(`API unreachable at ${API_BASE}. ${detail}`);
  }
  if (!response.ok) {
    throw await responseError(response);
  }
  return parseJson<T>(response);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return apiWrite<T>(path, "POST", body);
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return apiWrite<T>(path, "PATCH", body);
}

export function apiPut<T>(path: string, body?: unknown): Promise<T> {
  return apiWrite<T>(path, "PUT", body);
}

type UseApiOptions = {
  ttl?: number;
  interval?: number;
  enabled?: boolean;
};

export function useApi<T>(path: string, options: UseApiOptions = {}) {
  const { ttl = 0, interval = 0, enabled = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(enabled);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const requestGen = useRef(0);
  const { paused } = useTrackerPause();
  const trackerPaused = paused && path.startsWith("/api/trackers");

  const fetchData = useMemo(
    () => async () => {
      if (!enabled || trackerPaused) return;
      abortRef.current?.abort();
      const gen = requestGen.current + 1;
      requestGen.current = gen;
      abortRef.current = new AbortController();
      setLoading(true);
      setError(null);
      try {
        const payload = await apiGet<T>(path, ttl, abortRef.current.signal);
        if (gen !== requestGen.current) return;
        setData(payload);
        setWarnings(extractWarnings(payload));
        setError(null);
      } catch (err) {
        if (gen !== requestGen.current || _isAbortError(err)) {
          return;
        }
        setError(err instanceof Error ? err.message : "Unknown error");
        setWarnings([]);
      } finally {
        if (gen === requestGen.current) {
          setLoading(false);
        }
      }
    },
    [enabled, path, ttl, trackerPaused]
  );

  useLayoutEffect(() => {
    if (!enabled || trackerPaused) {
      requestGen.current += 1;
      abortRef.current?.abort();
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
  }, [enabled, path, trackerPaused]);

  useEffect(() => {
    if (trackerPaused) {
      setWarnings([]);
      return;
    }
    if (!enabled) return;
    fetchData();
    if (!interval) return;
    const timer = setInterval(fetchData, interval);
    return () => clearInterval(timer);
  }, [fetchData, interval, enabled, trackerPaused]);

  useEffect(() => () => abortRef.current?.abort(), []);

  return { data, loading, error, warnings, refresh: fetchData };
}
