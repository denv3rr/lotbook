import json
import os
import time
from typing import Dict, List, Optional

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich import box
from rich.text import Text
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from utils.input import InputSafe
from interfaces.navigator import Navigator
from modules.market_data.finnhub_client import FinnhubWrapper
from modules.market_data.yfinance_client import YahooWrapper
from modules.market_data.trackers import GlobalTrackers
from modules.market_data.intel import MarketIntel, REGIONS, news_cache_status, rank_news_items
from utils.charts import ChartRenderer
from interfaces.shell import ShellRenderer, MainMenuRequested
from interfaces.menu_layout import build_sidebar, compact_for_width, build_status_header
from utils.scroll_text import build_scrolling_line
from utils.layout import fit_renderable_to_height
from utils.system import SystemHost
from utils.world_clocks import build_world_clocks_panel
from utils.report_synth import ReportSynthesizer, build_report_context, build_ai_sections

try:
    from interfaces.gui_tracker import launch_tracker_gui
except Exception:
    launch_tracker_gui = None

try:
    from utils.gui_bootstrap import launch_gui_in_venv
except Exception:
    launch_gui_in_venv = None

class MarketFeed:
    def __init__(self):
        self.console = Console()
        self.finnhub = FinnhubWrapper()
        self.yahoo = YahooWrapper()
        self.trackers = GlobalTrackers()
        self.intel = MarketIntel()
        
        # Default View State
        self.current_period = "1d"
        self.current_interval = "15m"
        
        # Preset Intervals
        # Format: (Display Label, API Period, API Interval)
        self.interval_options = [
            ("1D", "1d", "15m"),
            ("5D", "5d", "60m"),
            ("1M", "1mo", "1d"),
            ("3M", "3mo", "1d"),
            ("1Y", "1y", "1wk")
        ]
        self.interval_idx = 0
        self.show_macro_dashboard = False
        self.intel_region_idx = self._guess_region_index()
        self.intel_industry = "all"
        self._intel_cache = {}
        self._intel_last_report = None
        self._intel_export_format = "md"
        self._tracker_last_analysis = None
        self._settings_file = os.path.join(os.getcwd(), "config", "settings.json")

    def toggle_interval(self):
        """Cycles to the next interval option."""
        self.interval_idx = (self.interval_idx + 1) % len(self.interval_options)
        label, p, i = self.interval_options[self.interval_idx]
        self.current_period = p
        self.current_interval = i
        return label

    def _guess_region_index(self) -> int:
        tz = ""
        try:
            tz = (time.tzname[time.daylight] or time.tzname[0] or "").lower()
        except Exception:
            tz = ""
        def pick(name: str) -> int:
            for idx, region in enumerate(REGIONS):
                if region.name.lower() == name.lower():
                    return idx
            return 0
        if "america" in tz or "pacific" in tz or "mountain" in tz or "eastern" in tz or "central" in tz:
            return pick("North America")
        if "buenos" in tz or "santiago" in tz or "argentina" in tz or "brazil" in tz:
            return pick("Latin America")
        if "europe" in tz or "london" in tz or "berlin" in tz or "paris" in tz:
            return pick("Europe")
        if "africa" in tz or "cairo" in tz or "lagos" in tz or "johannesburg" in tz:
            return pick("Africa")
        if "dubai" in tz or "riyadh" in tz or "tehran" in tz or "middle" in tz:
            return pick("Middle East")
        if "asia" in tz or "tokyo" in tz or "singapore" in tz or "hong_kong" in tz or "shanghai" in tz or "sydney" in tz or "australia" in tz:
            return pick("Asia-Pacific")
        return pick("North America")

    def run(self):
        """Standard interaction loop for the Market Module."""
        while True:
            # Display current settings in the view
            current_label = self.interval_options[self.interval_idx][0]

            macro_label = "Open Macro Dashboard" if not self.show_macro_dashboard else "Hide Macro Dashboard"
            panel = self.display_futures(view_label=current_label) if self.show_macro_dashboard else self._market_home_panel()
            compact = compact_for_width(self.console.width)
            options = {
                "1": "Ticker Search",
                "2": macro_label,
                "3": "Force Refresh",
                "4": f"Change Interval ({current_label})",
                "5": "Global Trackers",
                "6": "Reports",
                "7": f"Export Last Report ({self._intel_export_format})",
                "8": "Macro Dashboard",
                "0": "Back",
            }
            sidebar = build_sidebar(
                [
                    ("Market", {
                        "1": "Ticker Search",
                        "2": macro_label,
                        "3": "Force Refresh",
                        "4": f"Change Interval ({current_label})",
                        "5": "Global Trackers",
                    }),
                    ("Reports", {
                        "6": "Reports",
                        "7": f"Export Last Report ({self._intel_export_format})",
                    }),
                    ("Dash", {
                        "8": "Macro Dashboard",
                    }),
                ],
                show_main=True,
                show_back=True,
                show_exit=True,
                compact=compact,
            )
            choice = ShellRenderer.render_and_prompt(
                Group(panel),
                context_actions=options,
                valid_choices=list(options.keys()) + ["m", "x"],
                prompt_label=">",
                show_main=True,
                show_back=True,
                show_exit=True,
                show_header=False,
                sidebar_override=sidebar,
            )
            
            if choice == "0" or choice == "m":
                break
            elif choice == "x":
                Navigator.exit_app()
            elif choice == "1":
                self.stock_lookup_loop()
            elif choice == "2":
                self.show_macro_dashboard = not self.show_macro_dashboard
                continue
            elif choice == "3":
                # Clear fast cache to force real refresh
                self.yahoo._FAST_CACHE.clear()
                continue 
            elif choice == "4":
                new_label = self.toggle_interval()
            elif choice == "5":
                self.run_global_trackers()
            elif choice == "6":
                self.run_intel_reports()
            elif choice == "7":
                self._export_last_report()
            elif choice == "8":
                self.run_macro_dashboard()

    def _market_home_panel(self):
        info = {}
        try:
            info = SystemHost.get_info() or {}
        except Exception:
            info = {}

        ip = info.get("ip", "N/A")
        cpu = info.get("cpu_usage", "N/A")
        mem = info.get("mem_usage", "N/A")

        finnhub_ok = "YES" if self.finnhub.api_key else "NO"
        flight_ok = "YES" if (os.getenv("FLIGHT_DATA_URL") or os.getenv("FLIGHT_DATA_PATH")) else "NO"
        shipping_ok = "YES" if os.getenv("SHIPPING_DATA_URL") else "NO"

        macro_status = "Not loaded"
        if YahooWrapper._SNAPSHOT_CACHE:
            latest_ts = max(int(ts or 0) for ts, _ in YahooWrapper._SNAPSHOT_CACHE.values())
            age = max(0, int(time.time()) - latest_ts)
            macro_status = f"Cached {age}s ago"

        self.trackers.get_snapshot(mode="combined", allow_refresh=False)
        tracker_status = "Not loaded"
        if self.trackers._last_refresh:
            age = max(0, int(time.time() - self.trackers._last_refresh))
            tracker_status = f"Cached {age}s ago"
        tracker_warn = ""
        warnings = self.trackers._cached.get("warnings") if hasattr(self.trackers, "_cached") else []
        if warnings:
            tracker_warn = str(warnings[0])[:60]

        yahoo_warn = ""
        missing = YahooWrapper._LAST_MISSING if hasattr(YahooWrapper, "_LAST_MISSING") else []
        if missing:
            yahoo_warn = f"Missing: {', '.join(missing[:5])}"

        header = Text()
        header.append("Notes\n", style="bold gold1")
        header.append("Visit https://seperet.com \n", style="dim")

        stats = Table.grid(padding=(0, 1))
        stats.add_column(style="bold cyan", width=16)
        stats.add_column(style="white")
        stats.add_row("Local IP", str(ip))
        stats.add_row("CPU", str(cpu))
        stats.add_row("Memory", str(mem))
        stats.add_row("Finnhub", finnhub_ok)
        stats.add_row("Flight Feed", flight_ok)
        stats.add_row("Shipping", shipping_ok)
        stats.add_row("Macro Cache", macro_status)
        stats.add_row("Tracker Cache", tracker_status)
        if tracker_warn:
            stats.add_row("Tracker Warn", tracker_warn)
        if yahoo_warn:
            stats.add_row("YFinance Warn", yahoo_warn)

        clock_panel = build_world_clocks_panel(self.console.width)

        return Panel(
            Group(header, stats, clock_panel),
            border_style="yellow",
            title="[bold]Markets[/bold]",
        )


    def run_intel_reports(self):
        report_mode = "combined"
        while True:
            region = REGIONS[self.intel_region_idx].name
            industry = self.intel_industry
            report = self._get_intel_report(report_mode, region, industry)
            panel = self._render_intel_panel(report)
            compact = compact_for_width(self.console.width)
            options = {
                "1": "Weather Report",
                "2": "Conflict Report",
                "3": "Combined Report",
                "4": f"Region ({region})",
                "5": f"Industry ({industry})",
                "6": "Export Markdown",
                "7": "Export JSON",
                "8": f"Default Export ({self._intel_export_format})",
                "9": "Refresh Data",
                "10": "Fetch News Signals",
                "11": "News Feed",
                "0": "Back",
            }
            sidebar = build_sidebar(
                [
                    ("Reports", {
                        "1": "Weather Report",
                        "2": "Conflict Report",
                        "3": "Combined Report",
                    }),
                    ("Filters", {
                        "4": f"Region ({region})",
                        "5": f"Industry ({industry})",
                    }),
                    ("Export", {
                        "6": "Export Markdown",
                        "7": "Export JSON",
                        "8": f"Default Export ({self._intel_export_format})",
                    }),
                    ("Data", {
                        "9": "Refresh Data",
                        "10": "Fetch News Signals",
                        "11": "News Feed",
                    }),
                ],
                show_main=True,
                show_back=True,
                show_exit=True,
                compact=compact,
            )
            choice = ShellRenderer.render_and_prompt(
                Group(panel),
                context_actions=options,
                valid_choices=list(options.keys()) + ["m", "x"],
                prompt_label=">",
                show_main=True,
                show_back=True,
                show_exit=True,
                show_header=False,
                sidebar_override=sidebar,
            )
            if choice in ("0", "m"):
                return
            if choice == "x":
                Navigator.exit_app()
            if choice == "1":
                report_mode = "weather"
            elif choice == "2":
                report_mode = "conflict"
            elif choice == "3":
                report_mode = "combined"
            elif choice == "4":
                selected = self._select_region()
                if selected is not None:
                    self.intel_region_idx = selected
            elif choice == "5":
                selected = self._select_industry()
                if selected is not None:
                    self.intel_industry = selected
            elif choice == "6":
                path = self._export_intel_report(report, fmt="md")
                self._show_export_notice(path)
            elif choice == "7":
                path = self._export_intel_report(report, fmt="json")
                self._show_export_notice(path)
            elif choice == "8":
                self._intel_export_format = "json" if self._intel_export_format == "md" else "md"
            elif choice == "9":
                ShellRenderer.set_busy(1.0)
                report = self._get_intel_report(report_mode, region, industry, force=True)
                panel = self._render_intel_panel(report)
            elif choice == "10":
                settings = self._load_runtime_settings()
                ttl_seconds = int(settings.get("intel", {}).get("news_cache_ttl", 600))
                enabled = settings.get("news", {}).get("sources_enabled", [])
                ShellRenderer.set_busy(1.0)
                self.intel.fetch_news_signals(ttl_seconds=ttl_seconds, force=True, enabled_sources=enabled)
                report = self._get_intel_report(report_mode, region, industry, force=True)
                panel = self._render_intel_panel(report)
            elif choice == "11":
                self.run_news_feed()

    def _next_industry_filter(self) -> str:
        options = ["all", "energy", "agriculture", "shipping", "aviation", "defense", "tech", "finance", "logistics"]
        if self.intel_industry not in options:
            return "all"
        idx = options.index(self.intel_industry)
        return options[(idx + 1) % len(options)]

    def _select_region(self) -> Optional[int]:
        options = {str(idx + 1): region.name for idx, region in enumerate(REGIONS)}
        options["0"] = "Back"
        panel = Panel(
            Table.grid(),
            title="Select Region",
            border_style="cyan",
        )
        choice = ShellRenderer.render_and_prompt(
            Group(panel),
            context_actions=options,
            valid_choices=list(options.keys()) + ["m", "x"],
            prompt_label=">",
            show_main=True,
            show_back=True,
            show_exit=True,
            show_header=False,
        )
        if choice in ("0", "m"):
            return None
        if choice == "x":
            Navigator.exit_app()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(REGIONS):
                return idx
        return None

    def _select_industry(self) -> Optional[str]:
        options_list = ["all", "energy", "agriculture", "shipping", "aviation", "defense", "tech", "finance", "logistics"]
        options = {str(idx + 1): name for idx, name in enumerate(options_list)}
        options["0"] = "Back"
        panel = Panel(
            Table.grid(),
            title="Select Industry",
            border_style="cyan",
        )
        choice = ShellRenderer.render_and_prompt(
            Group(panel),
            context_actions=options,
            valid_choices=list(options.keys()) + ["m", "x"],
            prompt_label=">",
            show_main=True,
            show_back=True,
            show_exit=True,
            show_header=False,
        )
        if choice in ("0", "m"):
            return None
        if choice == "x":
            Navigator.exit_app()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(options_list):
                return options_list[idx]
        return None

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

    def _get_intel_report(self, report_mode: str, region: str, industry: str, force: bool = False) -> dict:
        settings = self._load_runtime_settings()
        intel_conf = settings.get("intel", {})
        auto_fetch = bool(intel_conf.get("auto_fetch", True))
        ttl_seconds = int(intel_conf.get("cache_ttl", 300))
        news_payload = None
        cache_key = (report_mode, region, industry)
        cached = self._intel_cache.get(cache_key)
        if cached and not force and (time.time() - cached[0]) < ttl_seconds:
            report = cached[1]
            self._intel_last_report = report
            return report
        if not auto_fetch and not force:
            return {
                "title": "Market Data",
                "summary": [
                    "Auto-fetch disabled in Settings.",
                    "Use Refresh to fetch a new report.",
                ],
                "sections": [],
            }
        news_conf = settings.get("news", {})
        conflict_sources = news_conf.get("conflict_sources_enabled") or news_conf.get("sources_enabled") or []
        conflict_categories = news_conf.get("conflict_categories_enabled") or []
        if report_mode in ("conflict", "combined", "weather") and auto_fetch:
            news_payload = self.intel.fetch_news_signals(ttl_seconds=ttl_seconds, enabled_sources=conflict_sources)
        if report_mode == "weather":
            ShellRenderer.set_busy(1.0)
            report = self.intel.weather_report(region, industry)
        elif report_mode == "conflict":
            ShellRenderer.set_busy(1.0)
            report = self.intel.conflict_report(
                region,
                industry,
                enabled_sources=conflict_sources,
                categories=conflict_categories,
            )
        else:
            ShellRenderer.set_busy(1.0)
            report = self.intel.combined_report(
                region,
                industry,
                enabled_sources=conflict_sources,
                categories=conflict_categories,
            )
        report = self._augment_report_with_ai(
            report,
            report_mode,
            region,
            industry,
            news_payload.get("items", []) if isinstance(news_payload, dict) else [],
            settings,
        )
        self._intel_cache[cache_key] = (time.time(), report)
        self._intel_last_report = report
        return report

    def _augment_report_with_ai(
        self,
        report: dict,
        report_mode: str,
        region: str,
        industry: str,
        news_items: List[dict],
        settings: dict,
    ) -> dict:
        ai_conf = settings.get("ai", {})
        if not bool(ai_conf.get("enabled", True)):
            return report
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
            report_mode,
            region,
            industry,
            news_items=news_items,
        )
        ai_payload = synthesizer.synthesize(context)
        report["ai"] = ai_payload
        report["sections"] = list(report.get("sections", []) or []) + build_ai_sections(ai_payload)
        return report

    def _render_intel_panel(self, report: dict) -> Panel:
        summary = report.get("summary", []) or []
        summary_text = Text()
        summary_text.append("Abstract\n", style="bold")
        for line in summary:
            summary_text.append(f"- {line}\n", style="dim")
        summary_panel = Panel(summary_text, border_style="cyan", title="Report Abstract")

        sections = report.get("sections", []) or []
        detail_layout = Table.grid(expand=True)
        detail_layout.add_column(ratio=1)
        settings = self._load_runtime_settings()
        intel_conf = settings.get("intel", {})
        if not bool(intel_conf.get("auto_fetch", True)):
            banner = Text("Auto-fetch disabled. Use Refresh Data to fetch live reports.", style="yellow")
            detail_layout.add_row(Panel(banner, border_style="yellow", title="Intel Status"))
        health = self.intel.conflict.health_status()
        status = health.get("status", "ok")
        backoff_until = health.get("backoff_until")
        last_attempt = health.get("last_attempt")
        last_ok = health.get("last_ok")
        last_fail = health.get("last_fail")
        now = time.time()
        if status == "idle":
            color = "dim"
            label = "Idle"
            detail_lines = [
                "No requests yet.",
                "Runs only when you open or refresh reports.",
            ]
        elif status == "cooldown":
            color = "yellow"
            label = "Cooldown"
            detail_lines = []
            if backoff_until:
                detail_lines.append(f"Retry in {max(0, int(backoff_until - now))}s.")
            if last_attempt:
                detail_lines.append(f"Last request {max(0, int(now - last_attempt))}s ago.")
            if last_fail:
                detail_lines.append(f"Last failure {max(0, int(now - last_fail))}s ago.")
        elif status == "warning":
            color = "yellow"
            label = "Warning"
            detail_lines = []
            if last_attempt:
                detail_lines.append(f"Last request {max(0, int(now - last_attempt))}s ago.")
            if last_fail:
                detail_lines.append(f"Last failure {max(0, int(now - last_fail))}s ago.")
        else:
            color = "green"
            label = "OK"
            detail_lines = []
            if last_ok:
                detail_lines.append(f"Last success {max(0, int(now - last_ok))}s ago.")
        status_text = Text()
        status_text.append(f"GDELT Status: {label}", style=color)
        for line in detail_lines:
            status_text.append(f"\n{line}", style="dim")
        detail_layout.add_row(Panel(status_text, border_style=color, title="Source Health"))
        risk_score = report.get("risk_score")
        risk_level = report.get("risk_level")
        confidence = report.get("confidence")
        if risk_score is not None:
            try:
                score_val = float(risk_score)
            except Exception:
                score_val = 0.0
            heat = ChartRenderer.generate_heatmap_bar(min(score_val / 10.0, 1.0), width=20)
            meter = Table.grid(padding=(0, 1))
            meter.add_column(style="bold cyan", width=12)
            meter.add_column(style="white")
            meter.add_row("Risk", f"{risk_level} ({score_val:.1f}/10)")
            if confidence:
                meter.add_row("Confidence", str(confidence))
            meter.add_row("Heat", heat)
            note = Text("Heatmap: low → high", style="dim")
            detail_layout.add_row(Panel(Group(meter, note), border_style="dim", title="Risk Meter"))
        detail_layout.add_row(summary_panel)

        for section in sections:
            title = section.get("title", "Details")
            rows = section.get("rows", [])
            table = Table(box=box.MINIMAL, expand=True)
            table.add_column("Field", style="bold cyan", width=18)
            table.add_column("Value", style="white")
            if rows and isinstance(rows[0], list):
                for row in rows:
                    if len(row) == 2:
                        table.add_row(str(row[0]), str(row[1]))
                    else:
                        table.add_row(str(row[0]), " ")
            else:
                for row in rows:
                    table.add_row(str(row), " ")
            detail_layout.add_row(Panel(table, border_style="dim", title=title))

        title = report.get("title", "Market Data")
        return Panel(detail_layout, border_style="blue", title=f"[bold]{title}[/bold]")

    def run_news_feed(self):
        offset = 0
        region_idx = 0
        industries = ["all", "energy", "agriculture", "shipping", "aviation", "defense", "finance", "tech"]
        while True:
            settings = self._load_runtime_settings()
            ttl_seconds = int(settings.get("intel", {}).get("news_cache_ttl", 600))
            enabled = settings.get("news", {}).get("sources_enabled", [])
            ShellRenderer.set_busy(1.0)
            cached = self.intel.fetch_news_signals(ttl_seconds=ttl_seconds, force=False, enabled_sources=enabled)
            items = cached.get("items", []) if isinstance(cached, dict) else []
            skipped = cached.get("skipped", []) if isinstance(cached, dict) else []
            health = cached.get("health", {}) if isinstance(cached, dict) else {}
            region_name = REGIONS[region_idx].name
            industry = industries[0] if not hasattr(self, "_news_industry") else self._news_industry
            filtered = self._filter_news_feed(items, region_name, industry)

            page_size = max(6, self.console.height - 12)
            page = filtered[offset:offset + page_size]

            table = Table(box=box.MINIMAL, expand=True)
            table.add_column("Source", style="bold cyan", width=14)
            table.add_column("Headline", style="white")
            table.add_column("Published", style="dim", width=20)

            if page:
                for item in page:
                    table.add_row(
                        str(item.get("source", ""))[:14],
                        str(item.get("title", ""))[:120],
                        str(item.get("published", ""))[:20],
                    )
            else:
                table.add_row("-", "No news items available.", "-")

            cache_state = news_cache_status(cached)
            status = build_status_header(
                "News Feed",
                [
                    ("Region", region_name),
                    ("Industry", industry),
                    ("Cache", cache_state),
                    ("Items", str(len(filtered))),
                    ("Showing", f"{offset + 1}-{min(len(filtered), offset + page_size)}"),
                ],
                compact=compact_for_width(self.console.width),
            )
            panel = Panel(table, border_style="blue", title="[bold]Market News[/bold]")
            health_panel = self._build_news_health_panel(health, skipped)
            content = Group(status, health_panel, panel)

            options = {
                "1": "Next Page",
                "2": "Prev Page",
                "3": "Refresh News",
                "4": f"Region ({region_name})",
                "5": f"Industry ({industry})",
                "0": "Back",
            }
            sidebar = build_sidebar(
                [("Feed", {
                    "1": "Next Page",
                    "2": "Prev Page",
                    "3": "Refresh News",
                    "4": f"Region ({region_name})",
                    "5": f"Industry ({industry})",
                })],
                show_main=True,
                show_back=True,
                show_exit=True,
                compact=compact_for_width(self.console.width),
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

            if choice in ("0", "m"):
                return
            if choice == "x":
                Navigator.exit_app()
            if choice == "1":
                if offset + page_size >= len(filtered):
                    with self.console.status("Fetching more news...", spinner="dots"):
                        fetched = self.intel.fetch_news_signals(
                            ttl_seconds=ttl_seconds,
                            force=True,
                            enabled_sources=enabled,
                        )
                        items = fetched.get("items", []) if isinstance(fetched, dict) else []
                        skipped = fetched.get("skipped", []) if isinstance(fetched, dict) else []
                        filtered = self._filter_news_feed(items, region_name, industry)
                if offset + page_size < len(filtered):
                    offset += page_size
            if choice == "2":
                offset = max(0, offset - page_size)
            if choice == "3":
                with self.console.status("Refreshing news feed...", spinner="dots"):
                    self.intel.fetch_news_signals(
                        ttl_seconds=ttl_seconds,
                        force=True,
                        enabled_sources=enabled,
                    )
                offset = 0
            if choice == "4":
                region_idx = (region_idx + 1) % len(REGIONS)
                offset = 0
            if choice == "5":
                if not hasattr(self, "_news_industry"):
                    self._news_industry = "all"
                idx = industries.index(self._news_industry)
                self._news_industry = industries[(idx + 1) % len(industries)]
                offset = 0

    def _filter_news_feed(self, items: list, region: str, industry: str) -> list:
        if not items:
            return []
        if region == "Global" and industry == "all":
            return rank_news_items(items, region=region, industry=industry)
        filtered = []
        for item in items:
            regions = item.get("regions", []) or []
            industries = item.get("industries", []) or []
            region_ok = True if region == "Global" else region in regions
            industry_ok = True if industry == "all" else industry in industries
            if region_ok and industry_ok:
                filtered.append(item)
        return rank_news_items(filtered, region=region, industry=industry)

    def _build_news_health_panel(self, health: dict, skipped: list) -> Panel:
        ok = 0
        warn = 0
        cooldown = 0
        now = int(time.time())
        for _, meta in (health or {}).items():
            backoff_until = int(meta.get("backoff_until", 0) or 0)
            fail_count = int(meta.get("fail_count", 0) or 0)
            if now < backoff_until:
                cooldown += 1
            elif fail_count > 0:
                warn += 1
            else:
                ok += 1

        line = Text.assemble(
            ("OK ", "bold green"),
            (str(ok), "green"),
            ("  WARN ", "bold yellow"),
            (str(warn), "yellow"),
            ("  COOLDOWN ", "bold red"),
            (str(cooldown), "red"),
        )
        if skipped:
            line.append("\n", style="dim")
            line.append("Skipped: " + ", ".join(skipped[:3]), style="yellow")
        return Panel(line, border_style="dim", title="Source Health")

    def _export_intel_report(self, report: dict, fmt: str = "md") -> str:
        os.makedirs(os.path.join("data", "reports"), exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = report.get("title", "report").lower().replace(" ", "_")
        filename = f"{base}_{stamp}.{fmt}"
        path = os.path.join("data", "reports", filename)
        if fmt == "json":
            import json as _json
            with open(path, "w", encoding="ascii") as f:
                _json.dump(report, f, indent=2)
            return path
        lines = []
        title = report.get("title", "Market Data")
        lines.append(f"# {title}")
        lines.append("")
        summary = report.get("summary", []) or []
        if summary:
            lines.append("## Abstract")
            for line in summary:
                lines.append(f"- {line}")
            lines.append("")
        sections = report.get("sections", []) or []
        for section in sections:
            sec_title = section.get("title", "Details")
            lines.append(f"## {sec_title}")
            rows = section.get("rows", [])
            if rows and isinstance(rows[0], list):
                lines.append("| Field | Value |")
                lines.append("| --- | --- |")
                for row in rows:
                    if len(row) == 2:
                        lines.append(f"| {row[0]} | {row[1]} |")
                    else:
                        lines.append(f"| {row[0]} |  |")
            else:
                for row in rows:
                    lines.append(f"- {row}")
            lines.append("")
        with open(path, "w", encoding="ascii") as f:
            f.write("\n".join(lines).strip() + "\n")
        return path

    def _show_export_notice(self, path: str) -> None:
        msg = Text(f"Report saved to {path}", style="green")
        ShellRenderer.render(Group(Panel(msg, border_style="green", title="Export Complete")), show_header=False)

    def _export_last_report(self) -> None:
        if not self._intel_last_report:
            msg = Text("No report generated yet. Open Intel Reports first.", style="yellow")
            ShellRenderer.render(Group(Panel(msg, border_style="yellow", title="Export Report")), show_header=False)
            return
        path = self._export_intel_report(self._intel_last_report, fmt=self._intel_export_format)
        self._show_export_notice(path)

    def _load_runtime_settings(self) -> dict:
        defaults = {
            "intel": {"auto_fetch": True, "cache_ttl": 300, "news_cache_ttl": 600},
            "trackers": {
                "auto_refresh": True,
                "gui_auto_refresh": True,
                "gui_refresh_interval": 10,
                "include_commercial_flights": False,
                "include_private_flights": False,
            },
            "news": {
                "sources_enabled": ["CNBC Top", "CNBC World", "MarketWatch", "BBC Business"],
                "aliases_file": "config/news_aliases.json",
            },
            "ai": {
                "enabled": True,
                "provider": "auto",
                "model_id": "rule_based_v1",
                "persona": "advisor_legal_v1",
                "cache_ttl": 21600,
                "cache_file": "data/ai_report_cache.json",
                "endpoint": "",
            },
            "reporting": {
                "ai": {
                    "enabled": True,
                    "provider": "auto",
                    "model_id": "llama3",
                    "endpoint": "http://127.0.0.1:11434",
                    "timeout_seconds": 15,
                }
            },
        }
        if not os.path.exists(self._settings_file):
            return defaults
        try:
            with open(self._settings_file, "r") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return defaults
        except Exception:
            return defaults
        for key, val in defaults.items():
            if key not in data or not isinstance(data.get(key), dict):
                data[key] = val
        return data

    def _tracker_snapshot(self, mode: str, allow_refresh: bool) -> dict:        
        snapshot = self.trackers.get_snapshot(mode=mode, allow_refresh=allow_refresh)
        if not allow_refresh:
            warnings = list(snapshot.get("warnings", []) or [])
            warnings.append("Auto-refresh disabled. Press Refresh to fetch.")
            snapshot["warnings"] = warnings
        return snapshot

    def _tracker_search_flow(self, snapshot: dict) -> None:
        query = InputSafe.get_string("Search flights (operator/flight/tail/ICAO24):")
        if not query:
            return
        result = self.trackers.search_snapshot(snapshot, query=query, fields=None, kind="flight", limit=20)
        rows = result.get("points", [])
        table = Table(box=box.SIMPLE, show_header=True)
        table.add_column("ID", style="cyan", width=10)
        table.add_column("Label", width=10)
        table.add_column("Operator", width=12)
        table.add_column("Flight", width=8)
        table.add_column("Tail", width=10)
        table.add_column("Country", width=12)
        for item in rows:
            table.add_row(
                str(item.get("id", ""))[:10],
                str(item.get("label", ""))[:10],
                str(item.get("operator_name", "") or item.get("operator", "") or "-")[:12],
                str(item.get("flight_number", "") or "-")[:8],
                str(item.get("tail_number", "") or "-")[:10],
                str(item.get("country", "") or "-")[:12],
            )
        panel = Panel(table, title=f"Search Results ({result.get('count', 0)})", border_style="cyan")
        ShellRenderer.render(Group(panel), show_header=False, show_main=True, show_back=True, show_exit=True)
        if rows:
            selection = InputSafe.get_string("Enter ID for history (blank to skip):")
            if selection:
                history = self.trackers.get_history(selection)
                hist_rows = history.get("history", [])[-10:]
                summary = history.get("summary", {})
                summary_lines = [
                    f"Points: {summary.get('points', 0)}",
                    f"Distance: {summary.get('distance_km', '-')}",
                    f"Direction: {summary.get('direction', '-')}",
                    f"Avg Speed: {summary.get('avg_speed_kts', '-')}",
                    f"Avg Alt: {summary.get('avg_altitude_ft', '-')}",
                    f"Duration: {summary.get('duration_sec', '-')}",
                    f"Route: {summary.get('route_hint', '-')}",
                ]
                hist_table = Table(box=box.SIMPLE, show_header=True)
                hist_table.add_column("TS", width=10)
                hist_table.add_column("Lat", width=8)
                hist_table.add_column("Lon", width=8)
                hist_table.add_column("Spd", width=6)
                for item in hist_rows:
                    hist_table.add_row(
                        str(item.get("ts", ""))[-10:],
                        f"{float(item.get('lat', 0.0)):.2f}",
                        f"{float(item.get('lon', 0.0)):.2f}",
                        "-" if item.get("speed_kts") is None else f"{float(item.get('speed_kts', 0.0)):.0f}",
                    )
                summary_panel = Panel(Text("\n".join(summary_lines), style="dim"), title="Summary", border_style="dim")
                hist_panel = Panel(hist_table, title=f"History: {selection}", border_style="dim")
                ShellRenderer.render(Group(summary_panel, hist_panel), show_header=False, show_main=True, show_back=True, show_exit=True)

    def _export_tracker_analysis(self, analysis: dict, fmt: str = "json") -> str:
        base_dir = os.path.join("data", "reports", "trackers")
        os.makedirs(base_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        raw_id = str(analysis.get("id") or "tracker")
        safe_id = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in raw_id)
        filename = f"tracker_analysis_{safe_id}_{stamp}.{fmt}"
        path = os.path.join(base_dir, filename)
        if fmt == "json":
            payload = json.dumps(analysis, indent=2)
        else:
            payload = self._format_tracker_analysis_md(analysis)
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload)
        return path

    def _format_tracker_analysis_md(self, analysis: dict) -> str:
        tracker_id = analysis.get("id", "unknown")
        loiter = analysis.get("loiter", {}) or {}
        geofences = analysis.get("geofences", {}) or {}
        replay = analysis.get("replay", []) or []
        lines = [
            f"# Tracker Analysis: {tracker_id}",
            "",
            "## Summary",
            f"- Replay window (sec): {analysis.get('window_sec', '-')}",
            f"- Replay points: {analysis.get('point_count', len(replay))}",
            f"- Loiter detected: {loiter.get('detected', False)}",
            "",
            "## Loiter Details",
            f"- Center: {loiter.get('center', {}) or '-'}",
            f"- Max distance km: {loiter.get('max_distance_km', '-')}",
            f"- Duration sec: {loiter.get('duration_sec', '-')}",
            "",
            "## Geofence Events",
        ]
        events = geofences.get("events", []) or []
        if events:
            lines.append("| Time (UTC) | Event | Fence | Distance km |")
            lines.append("| --- | --- | --- | --- |")
            for event in events:
                ts = event.get("ts")
                time_label = "-"
                if ts is not None:
                    try:
                        time_label = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(ts)))
                    except Exception:
                        time_label = str(ts)
                lines.append(
                    f"| {time_label} | {event.get('event', '-')} | {event.get('geofence_label', '-')}"
                    f" | {event.get('distance_km', '-')} |"
                )
        else:
            lines.append("- No geofence transitions recorded.")
        lines.extend(["", "## Replay Trail (last 10)", ""])
        if replay:
            lines.append("| Time (UTC) | Lat | Lon | Speed kts |")
            lines.append("| --- | --- | --- | --- |")
            for point in replay[-10:]:
                ts = point.get("ts")
                time_label = "-"
                if ts is not None:
                    try:
                        time_label = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(ts)))
                    except Exception:
                        time_label = str(ts)
                speed = point.get("speed_kts", "-")
                lines.append(
                    f"| {time_label} | {point.get('lat', '-')}"
                    f" | {point.get('lon', '-')} | {speed} |"
                )
        else:
            lines.append("- No replay history available.")
        warnings = analysis.get("warnings") or []
        if warnings:
            lines.extend(["", "## Warnings"])
            for warn in warnings:
                lines.append(f"- {warn}")
        return "\n".join(lines) + "\n"

    def _tracker_analysis_flow(self, snapshot: dict) -> None:
        selection = InputSafe.get_string("Enter tracker ID for analysis (blank to cancel):").strip()
        if not selection:
            return
        window_raw = InputSafe.get_string("Replay window seconds (default 3600):").strip()
        try:
            window_sec = int(window_raw) if window_raw else 3600
        except ValueError:
            window_sec = 3600
        window_sec = max(60, window_sec)
        radius_raw = InputSafe.get_string("Loiter radius km (default 10):").strip()
        try:
            loiter_radius = float(radius_raw) if radius_raw else 10.0
        except ValueError:
            loiter_radius = 10.0
        loiter_radius = max(0.1, loiter_radius)
        min_raw = InputSafe.get_string("Loiter min minutes (default 20):").strip()
        try:
            loiter_min = float(min_raw) if min_raw else 20.0
        except ValueError:
            loiter_min = 20.0
        loiter_min = max(1.0, loiter_min)

        geofences = []
        add_fence = InputSafe.get_yes_no("Add a geofence?", default=False)
        while add_fence:
            lat_raw = InputSafe.get_string("Geofence latitude (blank to stop):").strip()
            if not lat_raw:
                break
            try:
                lat = float(lat_raw)
            except ValueError:
                self.console.print("[red]Latitude must be numeric.[/red]")
                continue
            lon = InputSafe.get_float("Geofence longitude:")
            radius = InputSafe.get_float("Geofence radius km:", min_val=0.1)
            label = InputSafe.get_string("Geofence label (optional):").strip()
            geofences.append(
                {
                    "label": label or f"Fence {len(geofences) + 1}",
                    "lat": lat,
                    "lon": lon,
                    "radius_km": radius,
                }
            )
            add_fence = InputSafe.get_yes_no("Add another geofence?", default=False)

        analysis = self.trackers.analyze_tracker(
            selection,
            window_sec=window_sec,
            loiter_radius_km=loiter_radius,
            loiter_min_minutes=loiter_min,
            geofences=geofences,
        )
        self._tracker_last_analysis = analysis
        loiter = analysis.get("loiter", {}) or {}
        geofence_payload = analysis.get("geofences", {}) or {}
        events = geofence_payload.get("events", []) or []
        replay = analysis.get("replay", []) or []

        summary = Table.grid(padding=(0, 1))
        summary.add_column(style="bold cyan", width=16)
        summary.add_column(style="white")
        summary.add_row("Tracker", str(analysis.get("id", selection)))
        summary.add_row("Window", f"{analysis.get('window_sec', window_sec)} sec")
        summary.add_row("Replay Points", str(analysis.get("point_count", len(replay))))
        summary.add_row("Loiter", "Detected" if loiter.get("detected") else "None")
        summary.add_row("Geofence Events", str(len(events)))

        loiter_lines = [
            f"Center: {loiter.get('center', '-')}",
            f"Max Distance km: {loiter.get('max_distance_km', '-')}",
            f"Duration sec: {loiter.get('duration_sec', '-')}",
        ]
        loiter_panel = Panel(Text("\n".join(loiter_lines), style="dim"), title="Loiter Detail", border_style="dim")

        replay_table = Table(box=box.SIMPLE, show_header=True)
        replay_table.add_column("Time", width=10)
        replay_table.add_column("Lat", width=8)
        replay_table.add_column("Lon", width=8)
        replay_table.add_column("Spd", width=6)
        for point in replay[-8:]:
            ts = point.get("ts")
            try:
                ts_label = time.strftime("%H:%M:%S", time.localtime(int(ts)))
            except Exception:
                ts_label = str(ts or "-")
            replay_table.add_row(
                ts_label,
                f"{float(point.get('lat', 0.0)):.2f}",
                f"{float(point.get('lon', 0.0)):.2f}",
                "-" if point.get("speed_kts") is None else f"{float(point.get('speed_kts', 0.0)):.0f}",
            )
        if not replay:
            replay_table.add_row("-", "-", "-", "-")
        replay_panel = Panel(replay_table, title="Replay Trail", border_style="dim")

        event_table = Table(box=box.SIMPLE, show_header=True)
        event_table.add_column("Time", width=10)
        event_table.add_column("Event", width=8)
        event_table.add_column("Fence", width=16)
        event_table.add_column("Dist km", width=8)
        for event in events[-8:]:
            ts = event.get("ts")
            try:
                ts_label = time.strftime("%H:%M:%S", time.localtime(int(ts)))
            except Exception:
                ts_label = str(ts or "-")
            event_table.add_row(
                ts_label,
                str(event.get("event", "-")).upper(),
                str(event.get("geofence_label", "-"))[:16],
                f"{float(event.get('distance_km', 0.0)):.2f}",
            )
        if not events:
            event_table.add_row("-", "-", "No geofence events", "-")
        event_panel = Panel(event_table, title="Geofence Events", border_style="dim")

        warnings = analysis.get("warnings", []) or []
        warn_panel = None
        if warnings:
            warn_panel = Panel(Text("\n".join(warnings), style="yellow"), title="Warnings", border_style="yellow")

        layout = Table.grid(expand=True)
        layout.add_column(ratio=1)
        layout.add_row(Panel(summary, title="Tracker Analysis", border_style="cyan"))
        layout.add_row(Group(loiter_panel, event_panel, replay_panel))
        if warn_panel:
            layout.add_row(warn_panel)

        options = {
            "1": "Export JSON",
            "2": "Export Markdown",
            "0": "Back",
        }
        choice = ShellRenderer.render_and_prompt(
            Group(layout),
            context_actions=options,
            valid_choices=list(options.keys()),
            prompt_label=">",
            show_main=True,
            show_back=True,
            show_exit=True,
            show_header=False,
        )
        if choice == "1":
            path = self._export_tracker_analysis(analysis, fmt="json")
            self._show_export_notice(path)
        elif choice == "2":
            path = self._export_tracker_analysis(analysis, fmt="md")
            self._show_export_notice(path)

    def run_global_trackers(self):
        mode = "combined"
        cadence_options = [5, 10, 15, 30]
        cadence_idx = 1
        paused = False
        last_refresh = 0.0
        runtime_settings = self._load_runtime_settings()
        tracker_conf = runtime_settings.get("trackers", {})
        auto_refresh = bool(tracker_conf.get("auto_refresh", True))
        include_commercial = bool(tracker_conf.get("include_commercial_flights", False))
        include_private = bool(tracker_conf.get("include_private_flights", False))
        if include_commercial:
            os.environ["LOTBOOK_INCLUDE_COMMERCIAL"] = "1"
        else:
            os.environ.pop("LOTBOOK_INCLUDE_COMMERCIAL", None)
        if include_private:
            os.environ["LOTBOOK_INCLUDE_PRIVATE"] = "1"
        else:
            os.environ.pop("LOTBOOK_INCLUDE_PRIVATE", None)
        if not auto_refresh:
            paused = True
        snapshot = self._tracker_snapshot(mode, allow_refresh=auto_refresh)
        category_filter = "all"
        scroll_offset = 0

        def _available_categories(data: dict) -> list[str]:
            categories = sorted({str(pt.get("category", "")).lower() for pt in data.get("points", []) if pt.get("category")})
            return ["all"] + categories if categories else ["all"]

        def _clamp_offset(offset: int, total: int, page: int) -> int:
            if total <= 0:
                return 0
            max_offset = max(0, total - page)
            return max(0, min(offset, max_offset))

        try:
            import msvcrt
            use_live = True
        except Exception:
            use_live = False

        if not use_live:
            options = {
                "1": "Flights",
                "2": "Shipping",
                "3": "Combined",
                "4": "Refresh",
                "N": "Next Page",
                "P": "Prev Page",
                "F": "Category Filter",
                "A": "Filter: All",
                "S": "Search Flights",
                "T": "Tracker Analysis",
                "G": "Open GUI Tracker",
                "0": "Back",
            }
            while True:
                compact = compact_for_width(self.console.width)
                compact_height = self.console.height < 32
                compact_view = compact or compact_height
                sidebar = build_sidebar(
                    [("Trackers", {k: v for k, v in options.items() if k not in ("0",)})],
                    show_main=True,
                    show_back=True,
                    show_exit=True,
                    compact=compact,
                ) if not compact_height else None
                status_panel = build_status_header(
                    "Tracker Status",
                    [
                        ("Mode", mode),
                        ("Auto Refresh", "On" if auto_refresh else "Off"),
                        ("Commercial", "On" if include_commercial else "Off"),
                        ("Private", "On" if include_private else "Off"),
                    ],
                    compact=compact,
                ) if not compact_height else None
                footer_text = "N/P page | 1/2/3 mode | 4 refresh | F filter | A all | S search | T analysis | G gui | 0 back | M main | X exit"
                footer_panel = (
                    Text(footer_text, style="dim")
                    if compact_height
                    else Panel(Text(footer_text, style="dim"), box=box.SQUARE, border_style="dim")
                )
                filtered = GlobalTrackers.apply_category_filter(snapshot, category_filter)
                total_rows = len(filtered.get("points", []))

                def _layout(rows: int) -> Group:
                    return self._build_tracker_stack(
                        snapshot=snapshot,
                        mode=mode,
                        category_filter=category_filter,
                        max_rows=rows,
                        row_offset=scroll_offset,
                        sidebar=sidebar,
                        status_panel=status_panel,
                        footer_panel=footer_panel,
                        include_commercial=include_commercial,
                        include_private=include_private,
                        compact_view=compact_view,
                    )

                page_size = fit_renderable_to_height(
                    self.console,
                    _layout,
                    max_items=total_rows if total_rows else 1,
                    min_items=1,
                )
                scroll_offset = _clamp_offset(scroll_offset, total_rows, page_size)
                layout = _layout(page_size)
                choice = ShellRenderer.render_and_prompt(
                    Group(layout),
                    context_actions=options,
                    valid_choices=list(options.keys()),
                    prompt_label=">",
                    show_main=True,
                    show_back=True,
                    show_exit=True,
                    show_header=False,
                    show_sidebar=False,
                )
                key = choice.lower()
                if key in ("0", "m"):
                    return
                if key == "x":
                    Navigator.exit_app()
                if key == "g":
                    self._run_tracker_gui()
                    return
                if key == "1":
                    mode = "flights"
                    snapshot = self._tracker_snapshot(mode, allow_refresh=auto_refresh)
                    category_filter = "all"
                    scroll_offset = 0
                    continue
                if key == "2":
                    mode = "ships"
                    snapshot = self._tracker_snapshot(mode, allow_refresh=auto_refresh)
                    category_filter = "all"
                    scroll_offset = 0
                    continue
                if key == "3":
                    mode = "combined"
                    snapshot = self._tracker_snapshot(mode, allow_refresh=auto_refresh)
                    category_filter = "all"
                    scroll_offset = 0
                    continue
                if key == "4":
                    ShellRenderer.set_busy(1.0)
                    self.trackers.refresh(force=True)
                    snapshot = self.trackers.get_snapshot(mode=mode)
                    scroll_offset = 0
                    continue
                if key == "n":
                    scroll_offset += page_size
                    continue
                if key == "p":
                    scroll_offset = max(0, scroll_offset - page_size)
                    continue
                if key == "f":
                    categories = _available_categories(snapshot)
                    if category_filter not in categories:
                        category_filter = "all"
                    idx = categories.index(category_filter)
                    category_filter = categories[(idx + 1) % len(categories)]
                    scroll_offset = 0
                    continue
                if key == "a":
                    category_filter = "all"
                    scroll_offset = 0
                    continue
                if key == "s":
                    self._tracker_search_flow(snapshot)
                    continue
                if key == "t":
                    self._tracker_analysis_flow(snapshot)
                    continue

        from rich.live import Live
        from rich.table import Table
        from rich.panel import Panel
        from rich.text import Text
        from rich import box

        options = {
            "1": "Flights",
            "2": "Shipping",
            "3": "Combined",
            "4": "Refresh",
            "C": "Cadence",
            "F": "Category Filter",
            "A": "Filter: All",
            "S": "Search Flights",
            "T": "Tracker Analysis",
            "SPC": "Pause/Resume",
            "G": "Open GUI Tracker",
            "0": "Back",
        }

        def _layout_for(page_size: int, offset_override: Optional[int] = None) -> Table:
            nonlocal scroll_offset
            compact = compact_for_width(self.console.width)
            compact_height = self.console.height < 32
            filtered = GlobalTrackers.apply_category_filter(snapshot, category_filter)
            points = filtered.get("points", [])
            if offset_override is None:
                scroll_offset = _clamp_offset(scroll_offset, len(points), page_size)
                offset = scroll_offset
            else:
                offset = _clamp_offset(offset_override, len(points), page_size)
            compact_view = compact or compact_height
            panel = self.trackers.render(
                mode=mode,
                snapshot=filtered,
                filter_label=category_filter,
                max_rows=page_size,
                row_offset=offset,
                compact=compact_view,
            )
            if include_commercial:
                warn = Text(
                    "Commercial flights enabled. High-volume traffic may obscure geopolitical signals.",
                    style="yellow",
                )
                panel = Panel(Group(warn, panel), border_style="yellow", title="Tracker Notice")
            sidebar = build_sidebar(
                [("Trackers", {k: v for k, v in options.items() if k in ("1", "2", "3", "4", "C", "F", "A", "S", "T", "SPC", "G", "0")})],
                show_main=True,
                show_back=True,
                show_exit=True,
                compact=compact,
            ) if not compact_height else None
            status = "PAUSED" if paused else "LIVE"
            cadence = cadence_options[cadence_idx]
            commercial_label = "On (High Volume)" if include_commercial else "Off"
            private_label = "On" if include_private else "Off"
            footer = Text.assemble(
                ("[>]", "dim"),
                (" ", "dim"),
                (status, "bold green" if status == "LIVE" else "bold yellow"),
                (" | Cadence: ", "dim"),
                (f"{cadence}s", "bold cyan"),
                (" | Arrows scroll PgUp/PgDn page | 1/2/3 mode 4 refresh C cadence F filter A all S search T analysis Space pause 0 back M main X exit", "dim"),
            )
            mode_hint = Text.assemble(
                ("Mode: ", "dim"),
                ("1", "bold bright_white"),
                (" Flights  ", "cyan"),
                ("2", "bold bright_white"),
                (" Shipping  ", "cyan"),
                ("3", "bold bright_white"),
                (" Combined", "cyan"),
            )
            footer_panel = (
                Text.assemble(footer, "\n", mode_hint)
                if compact_height
                else Panel(Group(footer, mode_hint), box=box.SQUARE, border_style="dim")
            )

            auto_refresh_label = "On" if auto_refresh else "Off"
            status_panel = build_status_header(
                "Tracker Status",
                [
                    ("Mode", mode),
                    ("Cadence", f"{cadence}s"),
                    ("Auto Refresh", auto_refresh_label),
                    ("Commercial", commercial_label),
                    ("Private", private_label),
                ],
                compact=compact,
            ) if not compact_height else None
            layout = Table.grid(expand=True)
            layout.add_column(ratio=1)
            if status_panel:
                layout.add_row(status_panel)
            body = Table.grid(expand=True)
            body.add_column(ratio=1)
            if sidebar:
                body.add_row(Align.center(sidebar))
            body.add_row(Group(panel))
            layout.add_row(body)
            if footer_panel:
                layout.add_row(footer_panel)
            return layout

        def _page_size() -> int:
            filtered = GlobalTrackers.apply_category_filter(snapshot, category_filter)
            total_rows = len(filtered.get("points", []))
            return fit_renderable_to_height(
                self.console,
                lambda rows: _layout_for(rows, offset_override=0),
                max_items=total_rows if total_rows else 1,
                min_items=1,
            )

        def build_layout():
            return _layout_for(_page_size())

        dirty = True
        with Live(
            build_layout(),
            console=self.console,
            refresh_per_second=4,
            screen=False,
            auto_refresh=False,
        ) as live:
            while True:
                now = time.time()
                cadence = cadence_options[cadence_idx]
                if not paused and (now - last_refresh) >= cadence:
                    ShellRenderer.set_busy(1.0)
                    self.trackers.refresh(force=True)
                    snapshot = self.trackers.get_snapshot(mode=mode)
                    last_refresh = now
                    dirty = True

                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch in ("\x00", "\xe0"):
                        arrow = msvcrt.getwch()
                        page_size = _page_size()
                        if arrow == "H":  # up
                            scroll_offset = max(0, scroll_offset - 1)
                            dirty = True
                        elif arrow == "P":  # down
                            scroll_offset += 1
                            dirty = True
                        elif arrow == "I":  # page up
                            scroll_offset = max(0, scroll_offset - page_size)
                            dirty = True
                        elif arrow == "Q":  # page down
                            scroll_offset += page_size
                            dirty = True
                    elif ch in ("\r", "\n"):
                        pass
                    elif ch == " ":
                        paused = not paused
                        dirty = True
                    else:
                        key = ch.lower()
                        if key == "0":
                            return
                        if key == "m":
                            raise MainMenuRequested()
                        if key == "x":
                            Navigator.exit_app()
                        if key == "1":
                            mode = "flights"
                            snapshot = self._tracker_snapshot(mode, allow_refresh=auto_refresh)
                            category_filter = "all"
                            scroll_offset = 0
                            dirty = True
                        elif key == "2":
                            mode = "ships"
                            snapshot = self._tracker_snapshot(mode, allow_refresh=auto_refresh)
                            category_filter = "all"
                            scroll_offset = 0
                            dirty = True
                        elif key == "3":
                            mode = "combined"
                            snapshot = self._tracker_snapshot(mode, allow_refresh=auto_refresh)
                            category_filter = "all"
                            scroll_offset = 0
                            dirty = True
                        elif key == "4":
                            ShellRenderer.set_busy(1.0)
                            self.trackers.refresh(force=True)
                            snapshot = self.trackers.get_snapshot(mode=mode)    
                            last_refresh = time.time()
                            scroll_offset = 0
                            dirty = True
                        elif key == "c":
                            cadence_idx = (cadence_idx + 1) % len(cadence_options)
                            dirty = True
                        elif key == "f":
                            categories = _available_categories(snapshot)        
                            if category_filter not in categories:
                                category_filter = "all"
                            idx = categories.index(category_filter)
                            category_filter = categories[(idx + 1) % len(categories)]
                            scroll_offset = 0
                            dirty = True
                        elif key == "a":
                            category_filter = "all"
                            scroll_offset = 0
                            dirty = True
                        elif key == "s":
                            self._tracker_search_flow(snapshot)
                            dirty = True
                        elif key == "t":
                            self._tracker_analysis_flow(snapshot)
                            dirty = True
                        elif key == "g":
                            self._run_tracker_gui()
                            return
                if dirty:
                    live.update(build_layout(), refresh=True)
                    dirty = False
                time.sleep(0.1)

    def _run_tracker_gui(self):
        if not launch_tracker_gui and not launch_gui_in_venv:
            msg = Text(
                "GUI tracker unavailable. Install PySide6 + PySide6-WebEngine in a Python 3.12/3.13 venv.",
                style="yellow",
            )
            ShellRenderer.render(Group(Panel(msg, border_style="yellow", title="Tracker GUI")), show_header=False)
            return

        note = Text.assemble(
            ("Tracker updates running in GUI.", "bold white"),
            ("\n\nSetting up GUI environment if needed.", "dim"),
            ("\nProgress will appear below if setup runs.", "dim"),
            ("\nClose the GUI window to return here.", "dim"),
        )
        ShellRenderer.render(
            Group(Panel(note, border_style="cyan", title="Global Trackers")),
            show_header=False,
            show_main=True,
            show_back=True,
            show_exit=True,
        )
        if launch_tracker_gui:
            runtime_settings = self._load_runtime_settings()
            trackers = runtime_settings.get("trackers", {})
            refresh = int(trackers.get("gui_refresh_interval", 10))
            paused = not bool(trackers.get("gui_auto_refresh", True))
            launch_tracker_gui(refresh_seconds=refresh, start_paused=paused)
            return

        if launch_gui_in_venv:
            console = Console()
            status_lines = ["Preparing GUI tracker..."]

            def _status_hook(message: str) -> None:
                status_lines.append(message)
                if len(status_lines) > 6:
                    status_lines.pop(0)
                text = Text("\n".join(status_lines), style="dim")
                live.update(Panel(text, border_style="cyan", title="GUI Setup"), refresh=True)

            from rich.live import Live

            with Live(
                Panel(Text("\n".join(status_lines), style="dim"), border_style="cyan", title="GUI Setup"),
                console=console,
                refresh_per_second=4,
                screen=False,
            ) as live:
                runtime_settings = self._load_runtime_settings()
                trackers = runtime_settings.get("trackers", {})
                refresh = int(trackers.get("gui_refresh_interval", 10))
                paused = not bool(trackers.get("gui_auto_refresh", True))
                err = launch_gui_in_venv(refresh_seconds=refresh, start_paused=paused, status_hook=_status_hook)
            if err:
                msg = Text(err, style="yellow")
                ShellRenderer.render(Group(Panel(msg, border_style="yellow", title="Tracker GUI")), show_header=False)

    def _build_tracker_stack(
        self,
        snapshot: dict,
        mode: str,
        category_filter: str,
        max_rows: int,
        row_offset: int,
        sidebar: Optional[Panel],
        status_panel: Optional[Panel],
        footer_panel: Optional[object],
        include_commercial: bool,
        include_private: bool,
        compact_view: bool = False,
    ) -> Group:
        filtered = GlobalTrackers.apply_category_filter(snapshot, category_filter)
        panel = self.trackers.render(
            mode=mode,
            snapshot=filtered,
            filter_label=category_filter,
            max_rows=max_rows,
            row_offset=row_offset,
            compact=compact_view,
        )
        sections: List = []
        if status_panel:
            sections.append(status_panel)
        if include_commercial:
            warn = Text(
                "Commercial flights enabled. High-volume traffic may obscure geopolitical signals.",
                style="yellow",
            )
            sections.append(Panel(warn, border_style="yellow", title="Tracker Notice"))
        if include_private:
            warn = Text(
                "Private flights enabled. Adds more noise and may reduce signal clarity.",
                style="yellow",
            )
            sections.append(Panel(warn, border_style="yellow", title="Tracker Notice"))
        if sidebar:
            sections.append(sidebar)
        sections.append(panel)
        if footer_panel:
            sections.append(footer_panel)
        return Group(*sections)

    def display_futures(self, view_label="1D"):
        """Renders categorized macro data inside a clean panel with Sparklines."""
        ShellRenderer.set_busy(0.8)
        raw_data = self.yahoo.get_macro_snapshot(
            period=self.current_period,
            interval=self.current_interval
        )

        if not raw_data:
            missing = []
            try:
                missing = self.yahoo.get_last_missing_symbols()
            except Exception:
                pass

            msg = Text("Market data provider returned no rows. ", style="bold yellow")
            msg.append("This is usually a transient Yahoo/yfinance issue.\n", style="yellow")
            if missing:
                msg.append(f"\nSkipped symbols (no data): {', '.join(missing[:20])}", style="dim")
                if len(missing) > 20:
                    msg.append(f" (+{len(missing) - 20} more)", style="dim")

            return Panel(msg, border_style="yellow", title="[bold]Macro Dashboard[/bold]")

        # Define explicit category order
        cat_order = ["Indices", "Big Tech", "US Sectors", "Commodities", "FX", "Rates", "Crypto", "Macro ETFs"]

        def _sort_key(item):
            cat = item.get("category", "Other")
            sub = item.get("subcategory", "")
            tick = item.get("ticker", "")
            rank = cat_order.index(cat) if cat in cat_order else 999
            return (rank, sub, tick)

        raw_data.sort(key=_sort_key)

        table = Table(expand=True, box=box.MINIMAL_DOUBLE_HEAD)
        table.add_column("Trend", justify="center", width=5)
        # FORCE LEFT JUSTIFY HERE
        table.add_column("Ticker", style="cyan", justify="left")
        table.add_column("Price", justify="right")
        table.add_column("Change", justify="right")
        table.add_column("% Chg", justify="right")
        table.add_column("Heat", justify="center", width=6)
        table.add_column(f"Chart ({view_label})", justify="center", width=20, no_wrap=True)
        table.add_column("Vol", justify="right", style="dim")
        table.add_column("Security", min_width=20)

        current_cat = None
        current_subcat = None

        for item in raw_data:
            cat = item.get("category", "Other")
            subcat = item.get("subcategory", "")

            # 1. New Main Category?
            if cat != current_cat:
                table.add_row("", "", "", "", "", "", "", "") # Spacer
                table.add_row("", f"[bold underline gold1]{cat.upper()}[/bold underline gold1]", "", "", "", "", "", "")
                current_cat = cat
                current_subcat = None 

            # 2. New Sub Category?
            if subcat and subcat != current_subcat:
                # Removed leading spaces for flush-left alignment
                table.add_row("", f"[dim italic white]{subcat}[/dim italic white]", "", "", "", "", "", "")
                current_subcat = subcat

            change = float(item.get("change", 0.0) or 0.0)
            pct = float(item.get("pct", 0.0) or 0.0)
            c_color = "green" if change >= 0 else "red"

            trend_arrow = ChartRenderer.get_trend_arrow(change)
            heat_val = min(abs(pct) / 2.0, 1.0)
            heat_bar = ChartRenderer.generate_heatmap_bar(heat_val, width=6)
            history = item.get("history", []) or []
            sparkline = ChartRenderer.generate_sparkline(history, length=20)
            spark_color = "green" if (history and history[-1] >= history[0]) else ("red" if history else "dim")

            table.add_row(
            trend_arrow,
            item.get("ticker", ""),
            f"{float(item.get('price', 0.0) or 0.0):,.2f}",
            f"[{c_color}]{change:+.2f}[/{c_color}]",
            f"[{c_color}]{pct:+.2f}%[/{c_color}]",
                heat_bar,
                f"[{spark_color}]{sparkline}[/{spark_color}]",
                f"{int(item.get('volume', 0) or 0):,}",
                item.get("name", "")
            )

        missing = []
        try:
            missing = self.yahoo.get_last_missing_symbols()
        except Exception:
            pass

        footer = ""
        if missing:
            shown = ", ".join(missing[:12])
            footer = f"[dim]Skipped symbols (no data): {shown}" + ("…[/dim]" if len(missing) > 12 else "[/dim]")

        subtitle = f"[dim]Interval: {view_label} | Period: {self.current_period} | Bars: {self.current_interval} | Heat: abs % change[/dim]"
        ticker_panel = Panel(
            Align.center(table),
            title=f"[bold gold1]MACRO DASHBOARD ([bold green]{view_label}[/bold green])[/bold gold1]",
            border_style="yellow",
            box=box.ROUNDED,
            padding=(0, 2),
            subtitle=subtitle if not footer else f"{subtitle}\n{footer}"
        )

        return ticker_panel

    def run_macro_dashboard(self):
        """Paged macro dashboard to keep the sidebar visible."""
        page = 0
        while True:
            current_label = self.interval_options[self.interval_idx][0]
            panel = self._render_macro_page(view_label=current_label, page=page)
            options = {
                "1": "Next Page",
                "2": "Prev Page",
                "3": "Refresh",
                "4": f"Change Interval ({current_label})",
                "0": "Back",
            }
            sidebar = build_sidebar(
                [("Macro", {
                    "1": "Next Page",
                    "2": "Prev Page",
                    "3": "Refresh",
                    "4": f"Change Interval ({current_label})",
                })],
                show_main=True,
                show_back=True,
                show_exit=True,
                compact=compact_for_width(self.console.width),
            )
            choice = ShellRenderer.render_and_prompt(
                Group(panel),
                context_actions=options,
                valid_choices=list(options.keys()) + ["m", "x"],
                prompt_label=">",
                show_main=True,
                show_back=True,
                show_exit=True,
                show_header=False,
                sidebar_override=sidebar,
            )
            if choice in ("0", "m"):
                return
            if choice == "x":
                Navigator.exit_app()
            if choice == "1":
                page += 1
            if choice == "2":
                page = max(0, page - 1)
            if choice == "3":
                ShellRenderer.set_busy(0.8)
                self.yahoo._FAST_CACHE.clear()
                page = 0
            if choice == "4":
                self.toggle_interval()

    def _render_macro_page(self, view_label: str, page: int = 0) -> Panel:      
        ShellRenderer.set_busy(0.8)
        raw_data = self.yahoo.get_macro_snapshot(
            period=self.current_period,
            interval=self.current_interval
        )

        if not raw_data:
            return self.display_futures(view_label=view_label)

        cat_order = ["Indices", "Big Tech", "US Sectors", "Commodities", "FX", "Rates", "Crypto", "Macro ETFs"]

        def _sort_key(item):
            cat = item.get("category", "Other")
            sub = item.get("subcategory", "")
            tick = item.get("ticker", "")
            rank = cat_order.index(cat) if cat in cat_order else 999
            return (rank, sub, tick)

        raw_data.sort(key=_sort_key)

        def _build_table(view: list[dict]) -> Table:
            table = Table(expand=True, box=box.MINIMAL_DOUBLE_HEAD)
            table.add_column("Trend", justify="center", width=5)
            table.add_column("Ticker", style="cyan", justify="left")
            table.add_column("Price", justify="right")
            table.add_column("Change", justify="right")
            table.add_column("% Chg", justify="right")
            table.add_column("Heat", justify="center", width=6)
            table.add_column(f"Chart ({view_label})", justify="center", width=20, no_wrap=True)
            table.add_column("Vol", justify="right", style="dim")
            table.add_column("Security", min_width=20)

            current_cat = None
            current_subcat = None
            for item in view:
                cat = item.get("category", "Other")
                subcat = item.get("subcategory", "")

                if cat != current_cat:
                    table.add_row("", "", "", "", "", "", "", "", "")
                    table.add_row("", f"[bold underline gold1]{cat.upper()}[/bold underline gold1]", "", "", "", "", "", "", "")
                    current_cat = cat
                    current_subcat = None

                if subcat and subcat != current_subcat:
                    table.add_row("", f"[dim italic white]{subcat}[/dim italic white]", "", "", "", "", "", "", "")
                    current_subcat = subcat

                change = float(item.get("change", 0.0) or 0.0)
                pct = float(item.get("pct", 0.0) or 0.0)
                c_color = "green" if change >= 0 else "red"
                trend_arrow = ChartRenderer.get_trend_arrow(change)
                heat_val = min(abs(pct) / 2.0, 1.0)
                heat_bar = ChartRenderer.generate_heatmap_bar(heat_val, width=6)
                history = item.get("history", []) or []
                sparkline = ChartRenderer.generate_sparkline(history, length=20)
                spark_color = "green" if (history and history[-1] >= history[0]) else ("red" if history else "dim")

                table.add_row(
                    trend_arrow,
                    item.get("ticker", ""),
                    f"{float(item.get('price', 0.0) or 0.0):,.2f}",
                    f"[{c_color}]{change:+.2f}[/{c_color}]",
                    f"[{c_color}]{pct:+.2f}%[/{c_color}]",
                    heat_bar,
                    f"[{spark_color}]{sparkline}[/{spark_color}]",
                    f"{int(item.get('volume', 0) or 0):,}",
                    item.get("name", "")
                )
            return table

        legend = "[dim]Legend: Trend ▲/▼, Heat=|pct|/2, Sparkline=recent history, Cache age shown on dashboard[/dim]"

        def _build_panel_for_rows(row_count: int) -> Panel:
            total = len(raw_data)
            page_count = max(1, (total + row_count - 1) // row_count)
            page_idx = max(0, min(page, page_count - 1))
            start = page_idx * row_count
            end = min(total, start + row_count)
            view = raw_data[start:end]
            subtitle = f"[dim]Interval: {view_label} | Period: {self.current_period} | Bars: {self.current_interval} | Page {page_idx + 1}/{page_count}[/dim]"
            return Panel(
                Align.center(_build_table(view)),
                title=f"[bold gold1]MACRO DASHBOARD ([bold green]{view_label}[/bold green])[/bold gold1]",
                border_style="yellow",
                box=box.ROUNDED,
                padding=(0, 2),
                subtitle=f"{subtitle}\n{legend}",
            )

        rows_per_page = fit_renderable_to_height(
            self.console,
            _build_panel_for_rows,
            max_items=len(raw_data),
            min_items=8,
        )
        return _build_panel_for_rows(rows_per_page)

    def stock_lookup_loop(self):
        """
        Isolated loop for real-time stock ticker analysis.
        Allows interval switching specifically for the viewed ticker.
        """
        while True:
            # 1. Get Ticker
            ticker_input = self.console.input("\n[bold cyan]ENTER TICKER (or '0' to go back):[/bold cyan] ").strip().upper()
            
            if ticker_input == '0' or not ticker_input:
                break
            
            local_interval_idx = 0 
            
            # Inner Loop for interaction with THIS ticker
            while True:
                label, p, i = self.interval_options[local_interval_idx]
                
                self.console.print(f"[dim]Fetching {ticker_input} ({label})...[/dim]")
                ShellRenderer.set_busy(1.0)
                # Fetch detailed data
                data = self.yahoo.get_detailed_quote(ticker_input, period=p, interval=i)

                if "error" in data:
                    self.console.print(f"[red]Error fetching {ticker_input}: {data['error']}[/red]")
                    break 

                # 2. Construct Robust Display
                change = data.get('change', 0.0)
                color = "green" if change >= 0 else "red"
                spark_color = color
                
                grid = Table.grid(expand=True, padding=(0, 2))
                grid.add_column(ratio=1)
                grid.add_column(ratio=2)
                
                stats_table = Table.grid(padding=(0, 2))
                stats_table.add_column(style="dim white")
                stats_table.add_column(style="bold white", justify="right")
                
                hist_data = data.get('history', [])
                open_price = hist_data[0] if hist_data else 0.0
                
                stats_table.add_row("Open", f"{open_price:,.2f}") 
                stats_table.add_row("High", f"{data.get('high', 0):,.2f}")
                stats_table.add_row("Low", f"{data.get('low', 0):,.2f}")
                stats_table.add_row("Volume", f"{data.get('volume', 0):,}")
                if data.get('mkt_cap'):
                    stats_table.add_row("Mkt Cap", f"{data['mkt_cap'] / 1e9:,.2f}B")
                stats_table.add_row("Sector", f"{data.get('sector', 'N/A')}")

                sparkline = ChartRenderer.generate_sparkline(hist_data, length=40)
                
                price_text = Text.assemble(
                    (f"${data.get('price', 0):,.2f}", "bold white"),
                    (f"  {data.get('change', 0):+.2f} ({data.get('pct', 0):+.2f}%)", f"bold {color}")
                )
                
                chart_panel = Panel(
                    Align.center(f"[{spark_color}]{sparkline}[/{spark_color}]"),
                    title=f"Trend ({label})",
                    border_style="dim"
                )

                grid.add_row(
                    stats_table,
                    Align.right(
                        Group(
                            Align.right(price_text), 
                            chart_panel
                        )
                    )
                )

                main_panel = Panel(
                    grid,
                    title=f"[bold gold1]{data.get('name', ticker_input)} ({ticker_input})[/bold gold1]",
                    subtitle=f"[dim]Interval: {label}[/dim]",
                    border_style="blue",
                    box=box.ROUNDED
                )
                
                self.console.clear()
                print("\x1b[3J", end="")
                self.console.print(main_panel)
                
                action = self._prompt_menu(
                    "Ticker Actions",
                    {
                        "I": "Change Interval",
                        "N": "New Search",
                        "0": "Back",
                    },
                    show_back=True,
                ).lower()

                if action == "i":
                    local_interval_idx = (local_interval_idx + 1) % len(self.interval_options)
                    continue
                elif action == "n":
                    break
                elif action == "0":
                    return
                elif action == "m":
                    return
                elif action == "x":
                    Navigator.exit_app()
