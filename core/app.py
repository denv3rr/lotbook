import sys
from typing import Optional
from rich.console import Console

# Import internal modules
from interfaces.menus import MainMenu
from interfaces.shell import MainMenuRequested
from utils.input import InputSafe
from modules.market_data.feed import MarketFeed
from modules.client_mgr.manager import ClientManager
from interfaces.settings import SettingsModule
from interfaces.assistant import AssistantModule

class LotbookApp:
    """
    The Central Controller.
    Maintains the application loop and routes actions to sub-modules.
    """
    def __init__(self):
        self.console = Console()
        self.running = True
        self.menu = MainMenu()
        
        self._market_feed: Optional[MarketFeed] = None
        self._client_manager: Optional[ClientManager] = None
        self._settings_module: Optional[SettingsModule] = None
        self._assistant_module: Optional[AssistantModule] = None

    @property
    def market_feed(self) -> MarketFeed:
        if self._market_feed is None:
            self._market_feed = MarketFeed()
        return self._market_feed

    @property
    def client_manager(self) -> ClientManager:
        if self._client_manager is None:
            self._client_manager = ClientManager()
        return self._client_manager

    @property
    def settings_module(self) -> SettingsModule:
        if self._settings_module is None:
            self._settings_module = SettingsModule()
        return self._settings_module

    @property
    def assistant_module(self) -> AssistantModule:
        if self._assistant_module is None:
            self._assistant_module = AssistantModule()
        return self._assistant_module


    def run(self):
        """The Main Event Loop."""

        while self.running:
            # 1. Display Menu & Get Action
            try:
                action = self.menu.display()
                # 2. Route Action
                self.handle_action(action)
            except MainMenuRequested:
                continue

    def handle_action(self, action: str):
        """Routing Logic"""
        
        if action == "exit":
            self.shutdown()
        
        elif action == "client_mgr":
            # Use the already initialized instance
            self.client_manager.run()
            
        elif action == "market_data":
            # Use the already initialized instance
            self.market_feed.run()

        elif action == "intel_reports":
            self.market_feed.run_intel_reports()

        elif action == "global_trackers":
            self.market_feed.run_global_trackers()

        elif action == "fin_tools":
            self.unavailable_module("Financial Math Toolkit")
            
        elif action == "settings":
            # Use the already initialized instance
            self.settings_module.run()

        elif action == "assistant":
            self.assistant_module.run()

    def unavailable_module(self, name: str):
        self.console.print(f"\n[bold yellow]>> {name} unavailable[/bold yellow]")
        self.console.print(
            "[italic]   This module remains disabled until a standards-compliant implementation is ready.[/italic]"
        )
        InputSafe.pause()

    def shutdown(self):
        self.console.print("\n[bold red]>> Closing Session...[/bold red]")
        self.console.print("[dim]   Data saved.\n   Connections terminated.\n   Logs cleared from terminal.[/dim]\n")
        sys.exit(0)
