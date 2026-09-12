from interfaces.gui_tracker import launch_tracker_gui


if __name__ == "__main__":
    from utils.identity import getenv

    refresh = int(getenv("LOTBOOK_GUI_REFRESH", "10") or "10")
    start_paused = getenv("LOTBOOK_GUI_PAUSED", "0") == "1"
    launch_tracker_gui(refresh_seconds=refresh, start_paused=start_paused)
