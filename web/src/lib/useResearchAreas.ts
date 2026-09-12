import { useEffect, useRef, useState } from "react";
import { AREA_STORAGE_KEY, LEGACY_AREA_STORAGE_KEY, readAreaStorageRaw, type ResearchArea } from "./worldMap";
import { areaStorageState, openAreaVault, saveAreaVault, type AreaSession, type AreaStorageState } from "./researchAreaVault";

export function useResearchAreas() {
  const session = useRef<AreaSession | null>(null);
  const generation = useRef(0);
  const active = useRef(false);
  const inFlight = useRef(false);
  const [areas, setAreas] = useState<ResearchArea[]>([]);
  const [state, setState] = useState<AreaStorageState | "invalid" | "unlocked">("locked");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  function lock(message: string | null = null) {
    generation.current += 1;
    session.current = null;
    setAreas([]); setError(message);
    try { setState(areaStorageState(readAreaStorageRaw())); }
    catch (failure) { setState("invalid"); setError(failure instanceof Error ? failure.message : "Saved areas unavailable; stored data was left unchanged."); }
  }
  useEffect(() => {
    active.current = true;
    lock();
    const changed = (event: StorageEvent) => {
      if (event.storageArea === localStorage && (event.key === AREA_STORAGE_KEY || event.key === LEGACY_AREA_STORAGE_KEY || event.key === null)) lock("Research areas changed in another tab. Unlock to reload them.");
    };
    window.addEventListener("storage", changed);
    return () => { active.current = false; generation.current += 1; session.current = null; window.removeEventListener("storage", changed); };
  }, []);
  async function run(operation: (isCurrent: () => boolean) => Promise<AreaSession>) {
    if (inFlight.current) return false;
    inFlight.current = true; setBusy(true); setError(null);
    const started = generation.current;
    const isCurrent = () => active.current && generation.current === started;
    try {
      const next = await operation(isCurrent);
      if (!isCurrent()) return false;
      session.current = next; setAreas(next.areas); setState("unlocked");
      return true;
    } catch (failure) {
      if (isCurrent()) setError(failure instanceof Error ? failure.message : "Research-area operation failed; stored data was left unchanged.");
      return false;
    } finally { inFlight.current = false; if (active.current) setBusy(false); }
  }
  const unlock = (passphrase: string, migrate: boolean) => run(current => openAreaVault(passphrase, migrate, current));
  const update = (change: (current: ResearchArea[]) => ResearchArea[]) => run(current => {
    const opened = session.current;
    if (!opened) throw new Error("Unlock research areas before editing them.");
    return saveAreaVault(opened, change(opened.areas), current);
  });
  return { areas, state, busy, error, unlock, lock, update };
}
