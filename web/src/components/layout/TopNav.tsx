import { useEffect, useRef, useState, type ComponentType } from "react";
import { NavLink, Link, useLocation } from "react-router-dom";
import { ChevronDown, Menu, Power, X } from "lucide-react";

type NavItem = { label: string; icon: ComponentType<{ size?: number }>; path: string };
type TopNavProps = { items: NavItem[]; onToggleContext?: () => void; onToggleAssistant?: () => void; onToggleScene?: () => void; sceneAvailable?: boolean; sceneOpen?: boolean; onCloseApp?: () => void };
export function TopNav({ items, onToggleContext, onToggleAssistant, onToggleScene, sceneOpen, onCloseApp }: TopNavProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const menu = useRef<HTMLDetailsElement>(null);
  const location = useLocation();
  useEffect(() => { setMobileOpen(false); if (menu.current) menu.current.open = false; }, [location.pathname]);
  function choose(action?: () => void) { if (menu.current) menu.current.open = false; action?.(); }
  return <header className="bank-nav"><a href="#main-content" className="bank-skip">Skip to workspace</a><div className="bank-nav-inner"><Link to="/" className="bank-brand">LOTBOOK<span>Advisory & wealth</span></Link>
    <button className="bank-icon-button bank-mobile-toggle" aria-label="Toggle navigation" aria-expanded={mobileOpen} onClick={() => setMobileOpen(!mobileOpen)}>{mobileOpen ? <X size={18} /> : <Menu size={18} />}</button>
    <nav aria-label="Primary navigation" className={`bank-primary-nav ${mobileOpen ? "is-open" : ""}`}>{items.filter(item => item.path !== "/system").map(({ path, label, icon: Icon }) => <NavLink end={path === "/"} to={path} key={path}><Icon size={16} />{label}</NavLink>)}</nav>
    <div className="bank-nav-utilities"><details ref={menu} className="bank-workspace-menu" onKeyDown={event => { if (event.key === "Escape" && menu.current) { menu.current.open = false; menu.current.querySelector("summary")?.focus(); } }}><summary className="bank-button">Workspace <ChevronDown size={15} /></summary><div className="bank-menu-items">
      <button onClick={() => choose(onToggleScene)}>{sceneOpen ? "Close World" : "Open World"}</button>
      <Link to="/osint">Intelligence & trackers</Link><Link to="/system">System & settings</Link>
      <button onClick={() => choose(onToggleAssistant)}>Assistant</button><button onClick={() => choose(onToggleContext)}>Client context</button>
    </div></details><button className="bank-button bank-close-app" type="button" aria-label="Close app" onClick={onCloseApp}><Power size={15} /><span>Close app</span></button></div>
  </div></header>;
}
