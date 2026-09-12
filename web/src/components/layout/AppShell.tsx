import { lazy, ReactNode, Suspense, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { navItems } from "../../config/navigation";
import { ErrorBanner } from "../ui/ErrorBanner";
import { getApiBase, useApi } from "../../lib/api";
import { TopNav } from "./TopNav";
import { CloseApp } from "./CloseApp";
import { SceneProvider, useSceneController } from "../../lib/scene";

type AppShellProps = {
  children: ReactNode;
};

const GlobeOverlay = lazy(() =>
  import("../scene/GlobeOverlay").then((module) => ({
    default: module.GlobeOverlay
  }))
);
const ContextDrawer = lazy(() =>
  import("./ContextDrawer").then((module) => ({
    default: module.ContextDrawer
  }))
);
const ChatDrawer = lazy(() =>
  import("../ui/ChatDrawer").then((module) => ({
    default: module.ChatDrawer
  }))
);

function SceneOverlayLoading() {
  return (
    <div className="globe-overlay">
      <div className="globe-overlay__backdrop" />
      <div className="globe-overlay__loading">
        <p>Loading world view...</p>
      </div>
    </div>
  );
}

function DrawerLoading() {
  return (
    <div className="fixed bottom-6 right-6 z-40 glass-panel rounded-2xl px-4 py-3">
      <p className="text-xs text-slate-300">Loading panel...</p>
    </div>
  );
}

function ShellFrame({ children }: AppShellProps) {
  const [closeRequested, setCloseRequested] = useState(false);
  const [stopping, setStopping] = useState(false);
  const location = useLocation();
  const { error: healthError, warnings: healthWarnings, refresh } = useApi<{
    status: string;
  }>(
    "/api/health",
    { interval: 60000, enabled: !stopping }
  );
  const [contextOpen, setContextOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const { closeScene, isOpen, toggleScene } = useSceneController();
  const apiBase = getApiBase();
  const entry = (() => {
    const path = location.pathname;
    if (path === "/") return "dashboard";
    if (path.startsWith("/clients")) return "clients";
    if (path.startsWith("/reports")) return "reports";
    if (path.startsWith("/system")) return "system";
    if (path.startsWith("/osint")) return "osint";
    if (path.startsWith("/trackers")) return "trackers";
    if (path.startsWith("/intel")) return "intel";
    if (path.startsWith("/news")) return "news";
    return "unknown";
  })();
  const sceneEnabled = true;

  useEffect(() => {
    closeScene();
  }, [location.pathname, closeScene]);

  const healthMessages: string[] = [];
  if (healthError) {
    healthMessages.push(`API health check failed (${apiBase}): ${healthError}`);
  }
  for (const warning of healthWarnings) {
    healthMessages.push(`API health warning: ${warning}`);
  }

  if (stopping) return <main className="bank-stopped"><h1>Lotbook is shutting down.</h1><p>The shutdown request was accepted. Active API work will finish, then the dashboard server will stop.</p><p>You can close this browser tab. Your saved records remain on this computer.</p></main>;

  return (
    <div className="min-h-screen text-slate-100 overflow-x-hidden bg-black">
      <TopNav
        items={navItems}
        onToggleContext={() => setContextOpen((prev) => !prev)}
        onToggleAssistant={() => setAssistantOpen((prev) => !prev)}
        onToggleScene={() => toggleScene(sceneEnabled ? "overview" : undefined)}
        sceneAvailable={sceneEnabled}
        sceneOpen={isOpen}
        onCloseApp={() => setCloseRequested(true)}
      />
      <div className="flex min-h-screen min-w-0">
        <main id="main-content" tabIndex={-1} className="flex-1 min-w-0 px-4 py-8 md:px-10 lg:px-12 space-y-10 overflow-x-hidden">
          <ErrorBanner messages={healthMessages} onRetry={refresh} />
          {children}
        </main>
      </div>
      {isOpen ? (
        <Suspense fallback={<SceneOverlayLoading />}>
          <GlobeOverlay />
        </Suspense>
      ) : null}
      {closeRequested && <CloseApp onCancel={() => setCloseRequested(false)} onStopping={() => { closeScene(); setStopping(true); }} />}
      {contextOpen ? (
        <Suspense fallback={<DrawerLoading />}>
          <ContextDrawer variant="overlay" onClose={() => setContextOpen(false)} />
        </Suspense>
      ) : null}
      {assistantOpen ? (
        <Suspense fallback={<DrawerLoading />}>
          <ChatDrawer entry={entry} onClose={() => setAssistantOpen(false)} />
        </Suspense>
      ) : null}
    </div>
  );
}

export function AppShell({ children }: AppShellProps) {
  return (
    <SceneProvider>
      <ShellFrame>{children}</ShellFrame>
    </SceneProvider>
  );
}
