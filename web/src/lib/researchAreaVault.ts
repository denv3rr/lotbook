import { AREA_STORAGE_KEY, LEGACY_AREA_STORAGE_KEY, readAreaStorageRaw, readAreas, type ResearchArea } from "./worldMap";

// The passphrase/key never goes to storage. Keep format/KDF fixed and bounded
// before processing untrusted browser data; a new format needs explicit migration.
const FORMAT = "lotbook-research-areas-aes-gcm-v1";
const LEGACY_FORMAT = "clear-research-areas-aes-gcm-v1";
const ITERATIONS = 600_000;
const MAX_BYTES = 65_536;
const encoder = new TextEncoder();
type StoredFormat = typeof FORMAT | typeof LEGACY_FORMAT;
type Envelope = { format: StoredFormat; salt: string; iv: string; ciphertext: string };
export type AreaSession = { key: CryptoKey; salt: string; raw: string; areas: ResearchArea[] };
export type AreaStorageState = "new" | "legacy" | "locked";

function encode(bytes: Uint8Array): string {
  return btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join(""));
}
function decode(value: unknown): Uint8Array<ArrayBuffer> {
  if (typeof value !== "string" || value.length > MAX_BYTES || !/^[A-Za-z0-9+/]*={0,2}$/.test(value)) throw new Error("Invalid encrypted research areas; stored data was left unchanged.");
  return Uint8Array.from(atob(value), character => character.charCodeAt(0));
}
function envelope(raw: string): Envelope {
  if (raw.length > MAX_BYTES) throw new Error("Saved research areas exceed the storage limit.");
  const value = JSON.parse(raw);
  if (!value || (value.format !== FORMAT && value.format !== LEGACY_FORMAT) || decode(value.salt).length !== 16 || decode(value.iv).length !== 12 || decode(value.ciphertext).length < 16) throw new Error("Invalid encrypted research areas; stored data was left unchanged.");
  return value;
}
export function areaStorageState(raw: string | null): AreaStorageState {
  if (raw === null) return "new";
  if (raw.length > MAX_BYTES) throw new Error("Saved research areas exceed the storage limit.");
  if (raw.trimStart().startsWith("[")) { readAreas(raw); return "legacy"; }
  envelope(raw);
  return "locked";
}
function requireCrypto() {
  if (!globalThis.crypto?.subtle || !navigator.locks) throw new Error("Encrypted area storage requires HTTPS or localhost and a browser with Web Crypto and Web Locks. Map browsing is still available.");
}
async function derive(passphrase: string, salt: Uint8Array<ArrayBuffer>): Promise<CryptoKey> {
  requireCrypto();
  if (passphrase.length < 12 || passphrase.length > 128) throw new Error("Use a research-area passphrase of 12–128 characters.");
  const material = await crypto.subtle.importKey("raw", encoder.encode(passphrase), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey({ name: "PBKDF2", hash: "SHA-256", salt, iterations: ITERATIONS }, material, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
}
async function encrypt(areas: ResearchArea[], key: CryptoKey, salt: string): Promise<string> {
  const plaintext = encoder.encode(JSON.stringify(readAreas(JSON.stringify(areas))));
  if (plaintext.length > MAX_BYTES / 2) throw new Error("Saved research areas exceed the storage limit.");
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: encoder.encode(FORMAT), tagLength: 128 }, key, plaintext);
  return JSON.stringify({ format: FORMAT, salt, iv: encode(iv), ciphertext: encode(new Uint8Array(ciphertext)) } satisfies Envelope);
}
async function replace(expected: string | null, ciphertext: string, isCurrent: () => boolean): Promise<void> {
  requireCrypto();
  await navigator.locks.request(AREA_STORAGE_KEY, { mode: "exclusive", ifAvailable: true }, lock => {
    if (!lock) throw new Error("Research areas are being updated in another tab. Try again.");
    if (!isCurrent()) throw new Error("Research-area operation cancelled.");
    if (readAreaStorageRaw() !== expected) throw new Error("Saved research areas changed in another tab. Lock and unlock to reload them.");
    // This is the only writer: ciphertext only, after encryption and revision check.
    localStorage.setItem(AREA_STORAGE_KEY, ciphertext);
    localStorage.removeItem(LEGACY_AREA_STORAGE_KEY);
  });
}
export async function openAreaVault(passphrase: string, allowMigration: boolean, isCurrent: () => boolean): Promise<AreaSession> {
  requireCrypto();
  const raw = readAreaStorageRaw();
  const state = areaStorageState(raw);
  if (state === "legacy" && !allowMigration) throw new Error("Confirm encryption of existing unencrypted research areas first.");
  const saved = state === "locked" ? envelope(raw!) : null;
  const salt = saved?.salt ?? encode(crypto.getRandomValues(new Uint8Array(16)));
  const key = await derive(passphrase, decode(salt));
  let areas: ResearchArea[];
  if (saved) {
    try {
      const plaintext = await crypto.subtle.decrypt({ name: "AES-GCM", iv: decode(saved.iv), additionalData: encoder.encode(saved.format), tagLength: 128 }, key, decode(saved.ciphertext));
      areas = readAreas(new TextDecoder("utf-8", { fatal: true }).decode(plaintext));
    } catch { throw new Error("Could not unlock research areas. Check the passphrase; damaged data is left unchanged."); }
  } else areas = readAreas(raw);
  if (!isCurrent()) throw new Error("Research-area operation cancelled.");
  if (readAreaStorageRaw() !== raw) throw new Error("Saved research areas changed. Try unlocking again.");
  const needsRewrite = !saved || saved.format !== FORMAT;
  const encrypted = needsRewrite ? await encrypt(areas, key, salt) : raw!;
  if (needsRewrite) await replace(raw, encrypted, isCurrent);
  return { key, salt, raw: encrypted, areas };
}
export async function saveAreaVault(session: AreaSession, areas: ResearchArea[], isCurrent: () => boolean): Promise<AreaSession> {
  const raw = await encrypt(areas, session.key, session.salt);
  await replace(session.raw, raw, isCurrent);
  return { ...session, raw, areas };
}
