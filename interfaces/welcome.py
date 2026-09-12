import time
import os
import json
os.environ["TTE_DEBUG"] = "0"

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.align import Align
from rich.rule import Rule

from utils.system import SystemHost

class StartupScreen:
    def __init__(self, movement_speed: float = 1):
        self.console = Console()
        self.speed = movement_speed

    def render(self):

        # --- 1. ASCII Art ---
        ascii_art_lotbook = r"""
██╗      ██████╗ ████████╗██████╗  ██████╗  ██████╗ ██╗  ██╗
██║     ██╔═══██╗╚══██╔══╝██╔══██╗██╔═══██╗██╔═══██╗██║ ██╔╝
██║     ██║   ██║   ██║   ██████╔╝██║   ██║██║   ██║█████╔╝ 
██║     ██║   ██║   ██║   ██╔══██╗██║   ██║██║   ██║██╔═██╗ 
███████╗╚██████╔╝   ██║   ██████╔╝╚██████╔╝╚██████╔╝██║  ██╗
╚══════╝ ╚═════╝    ╚═╝   ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝
"""

        ascii_art_divider = r"""
█████╗█████╗█████╗█████╗█████╗█████╗█████╗█████╗█████╗█████╗█████╗█████╗
╚════╝╚════╝╚════╝╚════╝╚════╝╚════╝╚════╝╚════╝╚════╝╚════╝╚════╝╚════╝
"""

        ascii_art_dash = r"""
█████╗
╚════╝
"""

        # LINKS IN GRID
        links_grid = Table.grid(expand=False, padding=(0, 1))
        links_grid.add_column(style="blue", justify="left", ratio=1)
        links_grid.add_column(style="white", justify="left", ratio=1)

        links_grid.add_row("PROJECT REPO:", 
                           "https://github.com/denv3rr/clear")
        links_grid.add_row("DOCUMENTATION:", 
                           "https://github.com/denv3rr/clear/blob/main/README.md")
        links_grid.add_row("FINNHUB REGISTER:", 
                           "https://finnhub.io/register")
        links_grid.add_row("FINNHUB DASHBOARD:", 
                           "https://finnhub.io/dashboard")

        invisible_link_wrapper = Panel(
            Align.center(links_grid),
            box=box.SIMPLE,
            border_style="",
            padding=(0, 0),
        )

        # --- 4. Main Layout Grid (Three Rows for vertical arrangement) ---
        # This grid ensures all components are centered horizontally.
        main_layout_grid = Table.grid(expand=True)
        main_layout_grid.add_column(justify="center", ratio=1) 

        # Row 1: Centered ASCII Art
        main_layout_grid.add_row(Align.center("[warning]⚠  WORK IN PROGRESS ⚠[/warning]"))
        main_layout_grid.add_row(Align.center(ascii_art_lotbook))
        main_layout_grid.add_row(Align.center("[blue]Prices. Books. Analysis.[/blue]"))

        # --- 5. Encapsulate in a Rich panel with fixed width 200 ---
        panel_width = min(200, max(80, self.console.width - 6))
        subpanel_width = min(100, max(60, panel_width - 10))

        panel = Panel(
            main_layout_grid,
            box=box.ROUNDED,
            border_style="blue",
            title="[bold gold1]https://seperet.com[/bold gold1]",
            padding=(1, 3),
            width=panel_width,
        )

        self.console.print(Align.center(panel))
