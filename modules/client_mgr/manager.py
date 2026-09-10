# modules/client_mgr/manager.py

from rich.console import Console, Group
from rich.layout import Layout
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import time
import os
import json

# --- Internal Modules ---
from modules.client_mgr.client_model import Client, Account
from modules.client_mgr.holdings import (
    build_lot_entry,
    normalize_ticker,
    parse_timestamp,
)
from modules.client_mgr.data_handler import DataHandler
from modules.client_mgr.valuation import ValuationEngine
from modules.client_mgr.toolkit import FinancialToolkit
from modules.client_mgr.regime_views import RegimeRenderer
from modules.client_mgr.regime import RegimeModels
from modules.client_mgr.tools import Tools
from modules.client_mgr.tax import TaxEngine
from modules.market_data.trackers import GlobalTrackers, TrackerRelevance       
from modules.reporting.engine import ReportEngine

# --- Interface & Utils ---
from interfaces.components import UIComponents
from interfaces.navigator import Navigator
from interfaces.shell import ShellRenderer
from interfaces.menu_layout import build_sidebar, build_status_header, compact_for_width
from utils.input import InputSafe
from utils.report_synth import ReportSynthesizer, build_report_context, build_ai_sections

# --- Configuration Constants ---
HISTORY_PERIOD = {"1W": "5d", "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}
HISTORY_INTERVAL_MAP = {"1W": "1d", "1M": "1d", "3M": "1d", "6M": "1d", "1Y": "1d"}
INTERVAL_POINTS = {"1W": 40, "1M": 22, "3M": 66, "6M": 132, "1Y": 252}
CAPM_PERIOD = {"1W": "5d", "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}
CAPM_PERIOD_FALLBACK = {"1W": "1mo", "1M": "6mo", "3M": "1y", "6M": "2y", "1Y": "5y"}
REGIME_PERIOD_FALLBACK = {"1W": "1mo", "1M": "6mo", "3M": "1y", "6M": "2y", "1Y": "5y"}
REGIME_MIN_SAMPLES = 60

class ClientManager:
    """
    Controller for Client & Account Management.
    Orchestrates Data -> UI -> Input -> Action.
    """
    def __init__(self):
        self.console = Console()
        self.clients: List[Client] = DataHandler.load_clients()
        self._valuation_engine: Optional[ValuationEngine] = None
        self._tax_engine: Optional[TaxEngine] = None
        self._trackers: Optional[GlobalTrackers] = None
        self._list_val_cache = {}
        self._settings_file = os.path.join(os.getcwd(), "config", "settings.json")

    @property
    def valuation_engine(self) -> ValuationEngine:
        if self._valuation_engine is None:
            self._valuation_engine = ValuationEngine()
        return self._valuation_engine

    @property
    def tax_engine(self) -> TaxEngine:
        if self._tax_engine is None:
            self._tax_engine = TaxEngine()
        return self._tax_engine

    @property
    def trackers(self) -> GlobalTrackers:
        if self._trackers is None:
            self._trackers = GlobalTrackers()
        return self._trackers


    # =========================================================================
    # MAIN LOOP & LIST VIEW
    # =========================================================================

    def run(self):
        """Entry point for the Manager module."""
        while True:
            # 1. Prepare Data for List View
            val_map = {}
            for c in self.clients:
                val_map[c.client_id] = self._get_cached_list_value(c)

            # 2. Render List View
            cache_age = "-"
            if self._list_val_cache:
                last_ts = max(c.get("ts", 0) for c in self._list_val_cache.values())
                if last_ts:
                    cache_age = f"{int(time.time() - last_ts)}s"
            status_panel = build_status_header(
                "Status",
                [
                    ("Clients", str(len(self.clients))),
                    ("Val Cache", cache_age),
                ],
                compact=compact_for_width(self.console.width),
            )
            content = Group(
                status_panel,
                UIComponents.header("CLIENT MANAGER", breadcrumbs="Main > Clients"),
                UIComponents.client_list_table(self.clients, val_map),
            )
            options = {
                "1": "Add New Client",
                "2": "Select Client (ID)",
                "3": "Delete Client",
            }
            compact = compact_for_width(self.console.width)
            sidebar = build_sidebar(
                [("Clients", options)],
                show_main=True,
                show_back=True,
                show_exit=True,
                compact=compact,
            )
            choice = ShellRenderer.render_and_prompt(
                content,
                context_actions=options,
                valid_choices=list(options.keys()) + ["m", "x"],
                prompt_label=">",
                show_main=True,
                show_back=True,
                show_exit=True,
                show_header=False,
                sidebar_override=sidebar,
            )

            # 3. Navigation
            if choice in ("0", "m"):
                break
            if choice == "x":
                Navigator.exit_app()

            # 4. Handle Action
            if choice == "1": self.add_client_workflow()
            elif choice == "2":
                if self.select_client_workflow() == "MAIN_MENU":
                    break
            elif choice == "3": self.delete_client_workflow()
            
            # Save state on loop exit/action completion
            DataHandler.save_clients(self.clients)

    def _client_holdings_fingerprint(self, client: Client) -> tuple:
        holdings = {}
        for acc in client.accounts:
            for ticker, qty in (acc.holdings or {}).items():
                holdings[ticker] = holdings.get(ticker, 0.0) + float(qty or 0.0)
        return tuple(sorted((t, round(q, 6)) for t, q in holdings.items()))

    def _get_cached_list_value(self, client: Client, ttl_seconds: int = 30) -> float:
        cache = self._list_val_cache.get(client.client_id)
        now = time.time()
        fp = self._client_holdings_fingerprint(client)
        if cache:
            if cache.get("fp") == fp and (now - cache.get("ts", 0)) < ttl_seconds:
                return float(cache.get("value", 0.0) or 0.0)

        total = 0.0
        for acc in client.accounts:
            ShellRenderer.set_busy(0.8)
            v, _ = self.valuation_engine.calculate_portfolio_value(
                acc.holdings, history_period="1mo", history_interval="1d"
            )
            total += float(v or 0.0)
        self._list_val_cache[client.client_id] = {"fp": fp, "ts": now, "value": total}
        return total

    # =========================================================================
    # CLIENT DASHBOARD CONTROLLER
    # =========================================================================

    def select_client_workflow(self):
        cid = InputSafe.get_string("Enter Client ID (partial):")
        client = next((c for c in self.clients if c.client_id.startswith(cid)), None)
        if client:
            return self.client_dashboard_loop(client)
        else:
            self.console.print("[red]Client not found.[/red]")
            InputSafe.pause()
        return None

    def client_dashboard_loop(self, client: Client):
        """Displays specific client portfolio and handles client-level actions."""
        while True:
            # --- 1. Fetch & Calculate Data ---
            interval = str(getattr(client, "active_interval", "1M") or "1M").upper()
            
            # Aggregate holdings
            all_holdings = {}
            all_lots = {}
            for acc in client.accounts:
                for t, q in acc.holdings.items():
                    all_holdings[t] = all_holdings.get(t, 0) + q
                for t, lots in (acc.lots or {}).items():
                    all_lots.setdefault(t, []).extend(lots or [])

            # Market Valuation
            hp = HISTORY_PERIOD.get(interval, "1mo")
            hi = HISTORY_INTERVAL_MAP.get(interval, "1d")
            ShellRenderer.set_busy(1.0)
            total_val, enriched_data = self.valuation_engine.calculate_portfolio_value(
                all_holdings, history_period=hp, history_interval=hi
            )

            # Manual Valuation
            manual_total = 0.0
            for acc in client.accounts:
                m_val, _ = self.valuation_engine.calculate_manual_holdings_value(acc.manual_holdings)
                manual_total += m_val

            # History & Charts
            history_dates, history = self.valuation_engine.generate_portfolio_history_series(
                enriched_data=enriched_data,
                holdings=all_holdings,
                interval=interval,
                lot_map=all_lots,
            )
            n_points = INTERVAL_POINTS.get(interval, 22)
            spark_data = history[-n_points:] if history else []

            # CAPM Metrics
            ShellRenderer.set_busy(1.0)
            capm = Tools.compute_capm_metrics_from_holdings(
                all_holdings, benchmark_ticker="SPY", period=CAPM_PERIOD.get(interval, "1y")
            )
            if capm.get("error") or int(capm.get("points", 0) or 0) < 30:
                ShellRenderer.set_busy(1.0)
                capm = Tools.compute_capm_metrics_from_holdings(
                    all_holdings, benchmark_ticker="SPY", period=CAPM_PERIOD_FALLBACK.get(interval, "1y")
                )
            auto_risk = Tools.assess_risk_profile(capm)
            if client.risk_profile_source != "manual":
                client.risk_profile = auto_risk
                client.risk_profile_source = "auto"

            # --- 2. Render UI (via Components) ---
            regime_panel = self._build_regime_section(
                history=history,
                history_dates=history_dates,
                interval=interval,
                scope_label="Portfolio",
                holdings=all_holdings,
                lots=all_lots,
            )
            tracker_panel = self._build_tracker_metrics_panel(client=client)
            status_panel = build_status_header(
                "Status",
                [
                    ("Interval", interval),
                    ("Accounts", str(len(client.accounts))),
                    ("Holdings", str(len(all_holdings))),
                ],
                compact=compact_for_width(self.console.width),
            )
            ai_panel = self._build_ai_portfolio_panel(
                scope_label=f"Client: {client.name}",
                total_val=total_val,
                manual_total=manual_total,
                holdings_count=len(all_holdings),
                accounts_count=len(client.accounts),
                risk_label=client.risk_profile,
                capm=capm,
                report_type="client_portfolio",
            )
            content = Group(
                status_panel,
                UIComponents.header(
                    f"CLIENT: {client.name}",
                    subtitle=f"ID: {client.client_id} | Interval: {interval} | Risk: {client.risk_profile}",
                    breadcrumbs="Clients > Dashboard"
                ),
                UIComponents.portfolio_summary_panel(total_val, manual_total, spark_data),
                UIComponents.account_list_panel(client, enriched_data),
                UIComponents.risk_profile_full_width(capm),
                ai_panel if ai_panel else Text(""),
                tracker_panel if tracker_panel else Text(""),
                UIComponents.client_tax_profile_panel(client),
                UIComponents.tax_estimate_panel(
                    self.tax_engine.estimate_client_unrealized_tax(
                        client,
                        enriched_data,
                    ),
                    title="Portfolio Tax Estimate"
                ),
                regime_panel,
            )
            options = {
                "1": "Edit Profile",
                "2": "Manage Accounts",
                "3": "Tools",
                "4": "Change Interval",
                "5": "Export Reports",
                "0": "Back to Clients",
            }
            compact = compact_for_width(self.console.width)
            sidebar = build_sidebar(
                [("Client", options)],
                show_main=True,
                show_back=True,
                show_exit=True,
                compact=compact,
            )
            choice = ShellRenderer.render_and_prompt(
                content,
                context_actions=options,
                valid_choices=list(options.keys()) + ["m", "x"],
                prompt_label=">",
                show_main=True,
                show_back=True,
                show_exit=True,
                show_header=False,
                sidebar_override=sidebar,
            )

            # --- 3. Navigation ---
            if choice == "0": break
            if choice == "m":
                return "MAIN_MENU"
            if choice == "x":
                Navigator.exit_app()
            if choice == "1": self.edit_client_workflow(client)
            elif choice == "2":
                if self.manage_accounts_router(client) == "MAIN_MENU":
                    return "MAIN_MENU"
            elif choice == "3": Tools(client).run()
            elif choice == "4": self._change_interval_workflow(client)
            elif choice == "5": self._export_client_reports(client)
            
            DataHandler.save_clients(self.clients)
        return None

    def _build_regime_section(self, history, history_dates, interval, scope_label: str, holdings: dict, lots: dict):
        """Helper to render regime snapshot if data exists."""
        returns, used_interval, used_dates = self._prepare_regime_returns(
            history=history,
            history_dates=history_dates,
            interval=interval,
            holdings=holdings,
            lots=lots,
        )
        
        if len(returns) >= 8:
            scope_text = self._format_regime_label(scope_label, interval, used_interval)
            snap = RegimeModels.compute_markov_snapshot(
                returns,
                horizon=1,
                label=scope_text,
                interval=used_interval,
                timestamps=used_dates,
            )
            snap["scope_label"] = scope_label
            snap["interval"] = interval
            snap["regime_window"] = used_interval
            return RegimeRenderer.render(snap)
        return Text("")

    def _format_regime_label(self, scope_label: str, view_interval: str, regime_interval: str) -> str:
        if view_interval == regime_interval:
            return f"{scope_label} [dim]({view_interval})[/dim]"
        return f"{scope_label} [dim](View {view_interval} | Regime {regime_interval})[/dim]"

    def _prepare_regime_returns(self, history, history_dates, interval, holdings, lots):
        returns = []
        dates = history_dates or []
        if history and len(history) >= 8:
            for i in range(1, len(history)):
                prev = history[i-1]
                if prev > 0:
                    returns.append((history[i] - prev) / prev)

        if len(returns) >= REGIME_MIN_SAMPLES or not holdings:
            return returns, interval, dates

        fallback_period = REGIME_PERIOD_FALLBACK.get(interval)
        if not fallback_period:
            return returns, interval, dates

        ShellRenderer.set_busy(1.0)
        _, extended_enriched = self.valuation_engine.calculate_portfolio_value(
            holdings,
            history_period=fallback_period,
            history_interval=HISTORY_INTERVAL_MAP.get(interval, "1d"),
        )
        ext_dates, ext_history = self.valuation_engine.generate_portfolio_history_series(
            enriched_data=extended_enriched,
            holdings=holdings,
            interval=interval,
            lot_map=lots,
        )

        ext_returns = []
        if ext_history and len(ext_history) >= 8:
            for i in range(1, len(ext_history)):
                prev = ext_history[i-1]
                if prev > 0:
                    ext_returns.append((ext_history[i] - prev) / prev)

        if len(ext_returns) > len(returns):
            return ext_returns, fallback_period, ext_dates

        return returns, interval, dates

    # =========================================================================
    # ACCOUNT MANAGEMENT CONTROLLER
    # =========================================================================

    def manage_accounts_router(self, client: Client):
        """Route user to specific account actions."""
        while True:
            rows = Table.grid(expand=True)
            rows.add_column()
            rows.add_row(UIComponents.header(f"ACCOUNTS: {client.name}", breadcrumbs="Dashboard > Accounts"))
            for i, acc in enumerate(client.accounts, 1):
                rows.add_row(f"[{i}] {acc.account_name} ({acc.account_type})")
            rows.add_row("")
            rows.add_row("[A] Add New Account")
            rows.add_row("[R] Remove Account")
            rows.add_row("[0] Back")

            valid_choices = [str(i) for i in range(1, len(client.accounts) + 1)]
            valid_choices += ["a", "r", "0", "m", "x"]
            choice = ShellRenderer.render_and_prompt(
                Group(rows),
                context_actions={
                    "A": "Add New Account",
                    "R": "Remove Account",
                    "0": "Back",
                },
                valid_choices=valid_choices,
                prompt_label=">",
                show_main=True,
                show_back=True,
                show_exit=True,
                show_header=False,
                sidebar_override=build_sidebar(
                    [("Accounts", {"A": "Add New Account", "R": "Remove Account"})],
                    show_main=True,
                    show_back=True,
                    show_exit=True,
                    compact=compact_for_width(self.console.width),
                ),
            )

            if choice == "0":
                break
            if choice == "m":
                return "MAIN_MENU"
            if choice == "x":
                Navigator.exit_app()
            elif choice == "a":
                self.add_account_workflow(client)
            elif choice == "r":
                self.remove_account_workflow(client)
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(client.accounts):
                    if self.manage_holdings_loop(client, client.accounts[idx]) == "MAIN_MENU":
                        return "MAIN_MENU"
        return None

    def manage_holdings_loop(self, client: Client, account: Account):
        """Detailed view for a single account."""
        while True:
            interval = str(getattr(client, "active_interval", "1M") or "1M").upper()
            account.active_interval = interval # Sync

            # 1. Fetch Data
            hp = HISTORY_PERIOD.get(interval, "1mo")
            hi = HISTORY_INTERVAL_MAP.get(interval, "1d")
            
            # Market Val
            ShellRenderer.set_busy(1.0)
            total_val, enriched = self.valuation_engine.calculate_portfolio_value(
                account.holdings, history_period=hp, history_interval=hi
            )
            account.current_value = total_val

            manual_total, manual_list = self.valuation_engine.calculate_manual_holdings_value(
                account.manual_holdings
            )

            # Metrics for THIS account
            history_dates, history = self.valuation_engine.generate_portfolio_history_series(
                enriched_data=enriched,
                holdings=account.holdings,
                interval=interval,
                lot_map=account.lots,
            )
            ShellRenderer.set_busy(1.0)
            capm = FinancialToolkit.compute_capm_metrics_from_holdings(
                account.holdings, benchmark_ticker="SPY", period=CAPM_PERIOD.get(interval, "1y")
            )
            if capm.get("error") or int(capm.get("points", 0) or 0) < 30:
                ShellRenderer.set_busy(1.0)
                capm = FinancialToolkit.compute_capm_metrics_from_holdings(
                    account.holdings, benchmark_ticker="SPY", period=CAPM_PERIOD_FALLBACK.get(interval, "1y")
                )

            n_points = INTERVAL_POINTS.get(interval, 22)
            spark_data = history[-n_points:] if history else []

            # --- 2. Render UI (Same components, scoped data) ---
            regime_panel = self._build_regime_section(
                history=history,
                history_dates=history_dates,
                interval=interval,
                scope_label=f"Account: {account.account_name}",
                holdings=account.holdings,
                lots=account.lots,
            )
            tracker_panel = self._build_tracker_metrics_panel(client=client, account=account)
            status_panel = build_status_header(
                "Status",
                [
                    ("Interval", interval),
                    ("Holdings", str(len(account.holdings))),
                    ("Manual", str(len(manual_list))),
                ],
                compact=compact_for_width(self.console.width),
            )
            ai_panel = self._build_ai_portfolio_panel(
                scope_label=f"Account: {account.account_name}",
                total_val=total_val,
                manual_total=manual_total,
                holdings_count=len(account.holdings),
                accounts_count=1,
                risk_label=client.risk_profile,
                capm=capm,
                report_type="account_portfolio",
            )
            content = Group(
                status_panel,
                UIComponents.header(
                    f"ACCOUNT: {account.account_name}",
                    subtitle=f"{client.name} | {account.account_type}",
                    breadcrumbs=f"Clients > {client.name[:10]}... > Account"
                ),
                UIComponents.account_detail_overview(total_val, manual_total, history[-30:]),
                UIComponents.holdings_table(account, enriched, total_val),
                UIComponents.manual_assets_table(manual_list) if manual_list else Text(""),
                UIComponents.risk_profile_full_width(capm),
                ai_panel if ai_panel else Text(""),
                tracker_panel if tracker_panel else Text(""),
                UIComponents.account_tax_settings_panel(account),
                UIComponents.tax_estimate_panel(
                    self.tax_engine.estimate_account_unrealized_tax(
                        account,
                        enriched,
                        client.tax_profile,
                    ),
                    title="Account Tax Estimate"
                ),
                regime_panel,
            )
            options = {
                "1": "Add/Update Holding",
                "2": "Remove Holding",
                "3": "Edit Account Details",
            }
            compact = compact_for_width(self.console.width)
            sidebar = build_sidebar(
                [("Account", options)],
                show_main=True,
                show_back=True,
                show_exit=True,
                compact=compact,
            )
            choice = ShellRenderer.render_and_prompt(
                content,
                context_actions=options,
                valid_choices=list(options.keys()) + ["m", "x"],
                prompt_label=">",
                show_main=True,
                show_back=True,
                show_exit=True,
                show_header=False,
                sidebar_override=sidebar,
            )

            # --- 3. Navigation ---
            if choice == "0":
                break
            if choice == "m":
                return "MAIN_MENU"
            if choice == "x":
                Navigator.exit_app()
            if choice == "1": self.add_holding_workflow(account)
            elif choice == "2": self.remove_holding_workflow(account)
            elif choice == "3": self.edit_account_workflow(account)
            
            DataHandler.save_clients(self.clients)
        return None

    def _build_tracker_metrics_panel(self, client: Client, account: Optional[Account] = None):
        account_tags: Dict[str, List[str]] = {}
        if account:
            if account.tags:
                account_tags[account.account_name] = account.tags
        else:
            for acc in client.accounts:
                if acc.tags:
                    account_tags[acc.account_name] = acc.tags

        rules, matched_accounts = TrackerRelevance.match_rules(account_tags)
        if not rules:
            return None

        snapshot = self.trackers.get_snapshot(mode="combined", allow_refresh=False)
        points = snapshot.get("points", []) or []
        if not points:
            return UIComponents.tracker_metrics_panel({
                "status": "not_loaded",
                "accounts": matched_accounts,
                "tags": sorted({tag for tags in matched_accounts.values() for tag in tags}),
                "message": "Tracker data not cached. Open Global Trackers to fetch.",
            })

        filtered = TrackerRelevance.filter_points(points, rules)
        summary = TrackerRelevance.summarize(filtered)
        age = "-"
        if self.trackers._last_refresh:
            age = f"{int(time.time() - self.trackers._last_refresh)}s"
        return UIComponents.tracker_metrics_panel({
            "status": "ok",
            "accounts": matched_accounts,
            "tags": sorted({tag for tags in matched_accounts.values() for tag in tags}),
            "last_refresh_age": age,
            "summary": summary,
        })

    # =========================================================================
    # WORKFLOWS (Logic Wrappers)
    # =========================================================================

    def add_client_workflow(self):
        name = InputSafe.get_string("Client Name:")
        if not name: return
        new_client = Client(name=name, risk_profile="Not Assessed")
        new_client.accounts.append(Account(account_name="Primary Brokerage"))
        self.clients.append(new_client)
        self.console.print("[green]Client Added.[/green]")
        InputSafe.pause()

    def edit_client_workflow(self, client: Client):
        new_name = InputSafe.get_string(f"New Name [{client.name}]:")
        if new_name: client.name = new_name
        new_risk = InputSafe.get_string(
            f"Risk Profile [{client.risk_profile}] (auto/manual, Enter to keep):"
        )
        if new_risk:
            cleaned = new_risk.strip()
            if cleaned.lower() in ("auto", "automatic"):
                client.risk_profile = "Not Assessed"
                client.risk_profile_source = "auto"
            else:
                client.risk_profile = cleaned
                client.risk_profile_source = "manual"
        if InputSafe.get_yes_no("Update tax profile?"):
            self._edit_client_tax_profile(client)
        InputSafe.pause()

    def delete_client_workflow(self):
        cid = InputSafe.get_string("Client ID (full) to DELETE:")
        client = next((c for c in self.clients if c.client_id == cid), None)
        if client and InputSafe.get_yes_no(f"Delete {client.name}?"):
            self.clients.remove(client)
            self.console.print("[green]Deleted.[/green]")
        InputSafe.pause()

    def _change_interval_workflow(self, client):
        opts = list(INTERVAL_POINTS.keys())
        options = {str(idx + 1): opt for idx, opt in enumerate(opts)}
        options["0"] = "Back"
        choice = self._prompt_menu("Select Interval", options)
        if choice in ("0", "m"):
            return
        selected = options.get(choice)
        if not selected:
            return
        client.active_interval = selected
        for acc in client.accounts:
            acc.active_interval = selected

    def _export_client_reports(self, client: Client) -> None:
        engine = ReportEngine()
        while True:
            options = {
                "1": "Client Summary",
                "2": "Client Detailed",
                "3": "Account Report",
                "0": "Back",
            }
            choice = self._prompt_menu("Export Reports", options)
            if choice in ("0", "m"):
                return

            fmt = self._prompt_menu(
                "Export Format",
                {"1": "Markdown", "2": "JSON", "0": "Back"},
            )
            if fmt in ("0", "m"):
                continue
            fmt_val = "md" if fmt == "1" else "json"

            if choice == "1":
                report = engine.generate_client_portfolio_report(
                    client,
                    output_format=fmt_val,
                    interval=client.active_interval,
                    detailed=False,
                )
                self._write_report_file(
                    report.content,
                    client_id=client.client_id,
                    report_slug="client_summary",
                    ext=fmt_val,
                )
            elif choice == "2":
                report = engine.generate_client_portfolio_report(
                    client,
                    output_format=fmt_val,
                    interval=client.active_interval,
                    detailed=True,
                )
                self._write_report_file(
                    report.content,
                    client_id=client.client_id,
                    report_slug="client_detailed",
                    ext=fmt_val,
                )
            elif choice == "3":
                if not client.accounts:
                    self.console.print("[yellow]No accounts available.[/yellow]")
                    InputSafe.pause()
                    continue
                account_options = {
                    str(idx + 1): acc.account_name
                    for idx, acc in enumerate(client.accounts)
                }
                account_options["0"] = "Back"
                account_choice = self._prompt_menu("Select Account", account_options)
                if account_choice in ("0", "m"):
                    continue
                try:
                    account_idx = int(account_choice) - 1
                except Exception:
                    continue
                if not (0 <= account_idx < len(client.accounts)):
                    continue
                account = client.accounts[account_idx]
                report = engine.generate_account_portfolio_report(
                    client,
                    account,
                    output_format=fmt_val,
                    interval=account.active_interval,
                )
                self._write_report_file(
                    report.content,
                    client_id=client.client_id,
                    report_slug=f"account_{account.account_id}",
                    ext=fmt_val,
                )

    def _write_report_file(self, content: str, client_id: str, report_slug: str, ext: str) -> None:
        reports_dir = os.path.join("data", "reports", client_id)
        os.makedirs(reports_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{report_slug}_{timestamp}.{ext}"
        path = os.path.join(reports_dir, filename)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.console.print(f"[green]Report saved: {path}[/green]")
        except Exception as exc:
            self.console.print(f"[red]Failed to save report: {exc}[/red]")
        InputSafe.pause()

    def _prompt_menu(
        self,
        title: str,
        options: Dict[str, str],
        show_main: bool = True,
        show_back: bool = True,
        show_exit: bool = True,
    ) -> str:
        table = Table.grid(padding=(0, 1))
        table.add_column()
        for key, label in options.items():
            table.add_row(f"[bold cyan]{key}[/bold cyan]  {label}")
        panel = Panel(table, title=title, border_style="cyan", box=box.ROUNDED)
        return ShellRenderer.render_and_prompt(
            Group(panel),
            context_actions=options,
            valid_choices=list(options.keys()) + ["m", "x"],
            prompt_label=">",
            show_main=show_main,
            show_back=show_back,
            show_exit=show_exit,
            show_header=False,
        )

    # --- Account CRUD ---
    def add_account_workflow(self, client):
        name = InputSafe.get_string("Account Name:")
        if not name: return
        type_map = {
            "1": "Taxable",
            "2": "Traditional IRA",
            "3": "Roth IRA",
            "4": "401k",
            "5": "403b",
            "6": "457b",
            "7": "SEP IRA",
            "8": "SIMPLE IRA",
            "9": "HSA",
            "10": "529",
            "11": "Trust",
            "12": "Joint",
            "13": "Custodial",
            "14": "Corporate",
            "15": "Crypto",
            "U": "Manual",
            "0": "Back",
        }
        choice = self._prompt_menu("Account Type", type_map)
        if choice in ("0", "MAIN_MENU"):
            return
        if choice.lower() == "u":
            manual = InputSafe.get_string("Custom Type:")
            account_type = manual.strip() if manual else "Unspecified"
        else:
            account_type = type_map.get(choice, "Unspecified")
        account = Account(account_name=name, account_type=account_type)
        tag_hint = ", ".join(sorted(TrackerRelevance.TAG_RULES.keys()))
        if tag_hint:
            self.console.print(f"[dim]Optional tracker tags (comma-separated): {tag_hint}[/dim]")
        tags = InputSafe.get_string("Tags (optional, comma-separated):")
        if tags:
            account.tags = [t.strip() for t in tags.split(",") if t.strip()]
        client.accounts.append(account)

    def remove_account_workflow(self, client):
        # Logic to remove account...
        pass

    def edit_account_workflow(self, account):
        name = InputSafe.get_string(f"New Name [{account.account_name}]:")
        if name: account.account_name = name
        acc_type = InputSafe.get_string(f"Account Type [{account.account_type}] (Enter to keep):")
        if acc_type:
            account.account_type = acc_type.strip()
        ownership = InputSafe.get_string(f"Ownership Type [{account.ownership_type}] (Enter to keep):")
        if ownership:
            account.ownership_type = ownership.strip()
        custodian = InputSafe.get_string(f"Custodian [{account.custodian}] (Enter to keep):")
        if custodian:
            account.custodian = custodian.strip()
        tag_hint = ", ".join(sorted(TrackerRelevance.TAG_RULES.keys()))
        if tag_hint:
            self.console.print(f"[dim]Tracker tags (comma-separated) for relevance: {tag_hint}[/dim]")
        tags = InputSafe.get_string("Tags (comma-separated, Enter to keep):")
        if tags:
            account.tags = [t.strip() for t in tags.split(",") if t.strip()]
        if InputSafe.get_yes_no("Update account tax settings?"):
            self._edit_account_tax_settings(account)

    # --- Holding CRUD ---
    def add_holding_workflow(self, account):
        self.console.print("\n[dim]Enter Ticker or 'MANUAL'[/dim]")
        ticker_raw = InputSafe.get_string("Ticker:")
        ticker = normalize_ticker(ticker_raw)
        if not ticker:
            return

        if ticker == "MANUAL":
            self._add_manual_holding_logic(account)
            return

        method = self._prompt_menu(
            "Add/Update Holding",
            {
                "1": "Market Price",
                "2": "Historical (timestamp)",
                "3": "Manual Basis",
                "4": "Lot Entry",
                "5": "Aggregate Entry",
                "0": "Back",
            },
        )
        if method in ("0", "m"):
            return

        if method == "4":
            self._add_lot_entries_workflow(account, ticker)
            return

        if method == "5":
            self._add_aggregate_entry_workflow(account, ticker)
            return

        qty = InputSafe.get_float("Shares:", min_val=0.0000001)
        lot_entry = self._build_single_lot_entry(ticker, method, qty)
        if not lot_entry:
            return

        account.lots.setdefault(ticker, []).append(lot_entry)
        account.sync_holdings_from_lots()
        self.console.print("[green]Holding Updated.[/green]")
        InputSafe.pause()

    def _add_manual_holding_logic(self, account):
        name = InputSafe.get_string("Asset Name:")
        val = InputSafe.get_float("Estimated Value:")
        if not account.manual_holdings: account.manual_holdings = []
        account.manual_holdings.append({"name": name, "total_value": val})
        
    def remove_holding_workflow(self, account):
        ticker = InputSafe.get_string("Ticker to remove:").upper()
        if ticker in account.holdings:
            del account.holdings[ticker]
            if ticker in account.lots: del account.lots[ticker]
            self.console.print("[green]Removed.[/green]")
        InputSafe.pause()

    def _load_ai_settings(self) -> dict:
        defaults = {
            "enabled": True,
            "provider": "auto",
            "model_id": "rule_based_v1",
            "persona": "advisor_legal_v1",
            "cache_ttl": 21600,
            "cache_file": "data/ai_report_cache.json",
            "endpoint": "",
        }
        if not os.path.exists(self._settings_file):
            return defaults
        try:
            with open(self._settings_file, "r", encoding="ascii") as f:
                data = json.load(f)
            ai_conf = data.get("ai", {}) if isinstance(data, dict) else {}
        except Exception:
            return defaults
        if not isinstance(ai_conf, dict):
            ai_conf = {}
        for key, value in defaults.items():
            if key not in ai_conf:
                ai_conf[key] = value
        return ai_conf

    @staticmethod
    def _map_risk_level(label: str) -> str:
        text = (label or "").lower()
        if "high" in text or "aggressive" in text:
            return "High"
        if "low" in text or "conservative" in text:
            return "Low"
        if "moderate" in text or "balanced" in text:
            return "Moderate"
        return "Moderate"

    def _build_ai_portfolio_panel(
        self,
        scope_label: str,
        total_val: float,
        manual_total: float,
        holdings_count: int,
        accounts_count: int,
        risk_label: str,
        capm: dict,
        report_type: str,
    ) -> Optional[Group]:
        ai_conf = self._load_ai_settings()
        if not bool(ai_conf.get("enabled", True)):
            return None
        risk_level = self._map_risk_level(risk_label)
        beta = capm.get("beta") if isinstance(capm, dict) else None
        sharpe = capm.get("sharpe") if isinstance(capm, dict) else None
        vol = capm.get("vol_annual") if isinstance(capm, dict) else None
        alpha = capm.get("alpha_annual") if isinstance(capm, dict) else None
        signals = []
        if beta is not None:
            signals.append(f"Beta {beta:.2f}")
        if sharpe is not None:
            signals.append(f"Sharpe {sharpe:.2f}")
        if vol is not None:
            signals.append(f"Volatility {vol:.2%}")
        if alpha is not None:
            signals.append(f"Alpha {alpha:+.2%}")
        impacts = []
        if beta is not None and beta > 1.2:
            impacts.append("Market sensitivity elevated.")
        elif beta is not None and beta < 0.8:
            impacts.append("Defensive tilt vs benchmark.")
        if sharpe is not None and sharpe < 0.5:
            impacts.append("Risk-adjusted returns below target.")
        summary = [
            f"Scope: {scope_label}",
            f"Market Value: ${total_val:,.2f}",
            f"Manual Assets: ${manual_total:,.2f}",
            f"Accounts: {accounts_count}",
            f"Holdings: {holdings_count}",
            f"Risk Profile: {risk_label}",
        ]
        sections = [
            {
                "title": "Portfolio Overview",
                "rows": [
                    ["Market Value", f"${total_val:,.2f}"],
                    ["Manual Assets", f"${manual_total:,.2f}"],
                    ["Accounts", str(accounts_count)],
                    ["Holdings", str(holdings_count)],
                    ["Risk Profile", risk_label],
                ],
            }
        ]
        report = {
            "summary": summary,
            "risk_level": risk_level,
            "risk_score": None,
            "confidence": None,
            "signals": signals,
            "impacts": impacts,
            "sections": sections,
        }
        synthesizer = ReportSynthesizer(
            provider=str(ai_conf.get("provider", "rule_based")),
            model_id=str(ai_conf.get("model_id", "rule_based_v1")),
            persona=str(ai_conf.get("persona", "advisor_legal_v1")),
            cache_file=str(ai_conf.get("cache_file", "data/ai_report_cache.json")),
            cache_ttl=int(ai_conf.get("cache_ttl", 21600)),
            endpoint=str(ai_conf.get("endpoint", "")),
        )
        context = build_report_context(
            report,
            report_type,
            region="Global",
            industry="portfolio",
            news_items=[],
        )
        ai_payload = synthesizer.synthesize(context)
        sections = build_ai_sections(ai_payload)
        if not sections:
            return None
        return UIComponents.advisor_panels(sections)

    def _prompt_timestamp(self, prompt: str) -> Optional[datetime]:
        while True:
            ts_str = InputSafe.get_string(prompt)
            if not ts_str:
                return None
            ts = parse_timestamp(ts_str)
            if ts is None:
                self.console.print(
                    "[red]Invalid timestamp format. Use ISO 8601 or MM/DD/YY HH:MM:SS[/red]"
                )
                continue
            return ts

    def _prompt_optional_float(self, prompt: str) -> Optional[float]:
        raw = InputSafe.get_string(prompt)
        if not raw:
            return None
        try:
            return float(raw)
        except Exception:
            self.console.print("[red]Invalid number. Try again.[/red]")
            return self._prompt_optional_float(prompt)

    def _build_single_lot_entry(self, ticker: str, method: str, qty: float) -> Optional[dict]:
        if method == "1":
            quote = self.valuation_engine.get_quote_data(ticker)
            price = float(quote.get("price", 0.0) or 0.0)
            if price <= 0:
                price = InputSafe.get_float("Enter current price ($):", min_val=0.01)
            ts = datetime.now()
            try:
                return build_lot_entry(qty, price, ts, source="MARKET")
            except ValueError as exc:
                self.console.print(f"[red]{exc}[/red]")
                InputSafe.pause()
                return None

        if method == "2":
            ts = self._prompt_timestamp("Timestamp (ISO 8601 or MM/DD/YY HH:MM:SS):")
            if ts is None:
                self.console.print("[red]Timestamp required for historical add.[/red]")
                InputSafe.pause()
                return None
            basis = self._prompt_optional_float(
                "Cost basis per share (Enter to use historical price):"
            )
            if basis is None:
                price = self.valuation_engine.get_historical_price(ticker, ts)
                if price is None or price <= 0:
                    self.console.print(
                        "[yellow]Unable to fetch historical price. Enter manually.[/yellow]"
                    )
                    basis = InputSafe.get_float(
                        "Enter historical price ($):",
                        min_val=0.0,
                    )
                else:
                    basis = float(price)
            try:
                return build_lot_entry(
                    qty,
                    basis,
                    ts,
                    source="HISTORICAL",
                )
            except ValueError as exc:
                self.console.print(f"[red]{exc}[/red]")
                InputSafe.pause()
                return None

        basis = InputSafe.get_float("Enter cost basis per share ($):", min_val=0.0)
        ts = datetime.now()
        try:
            return build_lot_entry(qty, basis, ts, source="CUSTOM")
        except ValueError as exc:
            self.console.print(f"[red]{exc}[/red]")
            InputSafe.pause()
            return None

    def _add_lot_entries_workflow(self, account: Account, ticker: str) -> None:
        entries = []
        while True:
            qty = InputSafe.get_float("Lot shares:", min_val=0.0000001)
            ts = self._prompt_timestamp("Lot timestamp (ISO 8601 or MM/DD/YY HH:MM:SS):")
            basis = self._prompt_optional_float(
                "Lot cost basis per share (Enter to use historical price):"
            )
            if basis is None and ts is not None:
                price = self.valuation_engine.get_historical_price(ticker, ts)
                if price is None or price <= 0:
                    self.console.print(
                        "[yellow]Unable to fetch historical price. Enter manually.[/yellow]"
                    )
                    basis = InputSafe.get_float(
                        "Enter historical price ($):",
                        min_val=0.0,
                    )
                else:
                    basis = float(price)
            try:
                entry = build_lot_entry(
                    qty,
                    basis,
                    ts,
                    source="LOT",
                )
            except ValueError as exc:
                self.console.print(f"[red]{exc}[/red]")
                if not InputSafe.get_yes_no("Retry lot entry?"):
                    break
                continue
            entries.append(entry)
            if not InputSafe.get_yes_no("Add another lot?"):
                break

        if not entries:
            return
        account.lots.setdefault(ticker, []).extend(entries)
        account.sync_holdings_from_lots()
        self.console.print("[green]Lots Added.[/green]")
        InputSafe.pause()

    def _add_aggregate_entry_workflow(self, account: Account, ticker: str) -> None:
        qty = InputSafe.get_float("Aggregate shares:", min_val=0.0000001)
        mode = self._prompt_menu(
            "Aggregate Basis",
            {
                "1": "Average Cost",
                "2": "Total Cost",
                "3": "Timestamp Price",
                "0": "Back",
            },
        )
        if mode in ("0", "m"):
            return
        basis = None
        ts = None
        source = "AGGREGATE"
        if mode == "1":
            basis = InputSafe.get_float("Average cost per share ($):", min_val=0.0)
        elif mode == "2":
            total_cost = InputSafe.get_float("Total cost ($):", min_val=0.0)
            basis = total_cost / qty if qty > 0 else 0.0
            source = "AGGREGATE_TOTAL"
        elif mode == "3":
            ts = self._prompt_timestamp("Timestamp (ISO 8601 or MM/DD/YY HH:MM:SS):")
            if ts is None:
                self.console.print("[red]Timestamp required for historical add.[/red]")
                InputSafe.pause()
                return
        if basis is None and ts is not None:
            price = self.valuation_engine.get_historical_price(ticker, ts)
            if price is None or price <= 0:
                self.console.print(
                    "[yellow]Unable to fetch historical price. Enter manually.[/yellow]"
                )
                basis = InputSafe.get_float("Enter historical price ($):", min_val=0.0)
            else:
                basis = float(price)
        try:
            entry = build_lot_entry(
                qty,
                basis,
                ts,
                source=source,
                kind="aggregate",
            )
        except ValueError as exc:
            self.console.print(f"[red]{exc}[/red]")
            InputSafe.pause()
            return
        account.lots.setdefault(ticker, []).append(entry)
        account.sync_holdings_from_lots()
        self.console.print("[green]Aggregate Holding Updated.[/green]")
        InputSafe.pause()

    def _edit_client_tax_profile(self, client: Client):
        profile = client.tax_profile or {}
        residency = InputSafe.get_string(
            f"Residency Country [{profile.get('residency_country', '')}] (Enter to keep):"
        )
        tax_country = InputSafe.get_string(
            f"Tax Country [{profile.get('tax_country', '')}] (Enter to keep):"
        )
        currency = InputSafe.get_string(
            f"Reporting Currency [{profile.get('reporting_currency', 'USD')}] (Enter to keep):"
        )
        treaty = InputSafe.get_string(
            f"Treaty Country [{profile.get('treaty_country', '')}] (Enter to keep):"
        )
        tax_id = InputSafe.get_string(
            f"Tax ID [{profile.get('tax_id', '')}] (Enter to keep):"
        )

        if residency:
            profile["residency_country"] = residency.strip()
        if tax_country:
            profile["tax_country"] = tax_country.strip()
        if currency:
            profile["reporting_currency"] = currency.strip().upper()
        if treaty:
            profile["treaty_country"] = treaty.strip()
        if tax_id:
            profile["tax_id"] = tax_id.strip()
        client.tax_profile = profile

    def _edit_account_tax_settings(self, account: Account):
        settings = account.tax_settings or {}
        jurisdiction = InputSafe.get_string(
            f"Jurisdiction [{settings.get('jurisdiction', '')}] (Enter to keep):"
        )
        currency = InputSafe.get_string(
            f"Account Currency [{settings.get('account_currency', 'USD')}] (Enter to keep):"
        )
        withhold = InputSafe.get_string(
            f"Withholding Rate % [{settings.get('withholding_rate', '')}] (Enter to keep):"
        )
        tax_exempt = InputSafe.get_yes_no(
            f"Tax Exempt? (current: {settings.get('tax_exempt', False)})"
        )

        if jurisdiction:
            settings["jurisdiction"] = jurisdiction.strip()
        if currency:
            settings["account_currency"] = currency.strip().upper()
        if withhold:
            try:
                rate = float(withhold)
                if rate < 0:
                    rate = 0.0
                if rate > 100:
                    rate = 100.0
                settings["withholding_rate"] = rate
            except Exception:
                pass
        settings["tax_exempt"] = bool(tax_exempt)
        account.tax_settings = settings
