import sys
import subprocess
import importlib.util
import os
import platform
import json
import compileall
from datetime import datetime
from typing import Any, List

from rich.console import Console

console = Console()
console.clear()

# --- 1. Dependency Manager ---
def check_and_install_packages():
    """
    Reads requirements.txt and installs missing packages automatically.
    """
    req_file = "requirements.txt"
    
    print(">> Verifying installs...")
    if not os.path.exists(req_file):
        print(f"Error: {req_file} not found.")
        sys.exit(1)

    with open(req_file, "r") as f:
        packages = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    def _parse_version(text: str):
        return tuple(int(part) for part in text.split(".") if part.isdigit())

    def _marker_allows(line: str) -> bool:
        if ";" not in line:
            return True
        marker = line.split(";", 1)[1].strip()
        if not marker.startswith("python_version"):
            return True
        parts = marker.split()
        if len(parts) != 3:
            return True
        _, op, raw = parts
        version = raw.strip("\"' ")
        py_ver = _parse_version(platform.python_version())
        target = _parse_version(version)
        if op == "<":
            return py_ver < target
        if op == "<=":
            return py_ver <= target
        if op == ">":
            return py_ver > target
        if op == ">=":
            return py_ver >= target
        if op == "==":
            return py_ver == target
        return True

    def _strip_marker(line: str) -> str:
        return line.split(";", 1)[0].strip()

    missing = []
    
    # Map for known discrepancies between pip name and import name
    pkg_map = {
        "python-dotenv": "dotenv",
        "finnhub-python": "finnhub",
        "psutil": "psutil",
        "PySide6-WebEngine": "PySide6.QtWebEngineWidgets",
        "SQLAlchemy": "sqlalchemy",
    }

    for pkg in packages:
        if not _marker_allows(pkg):
            continue
        pkg_name = _strip_marker(pkg).split("=")[0].split(">")[0].split("<")[0]
        import_name = pkg_map.get(pkg_name, pkg_name)

        if importlib.util.find_spec(import_name) is None:
            missing.append(pkg)

    if missing:
        print(f">> Installing missing items: {', '.join(missing)}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print(">> Dependencies installed successfully.")
        except subprocess.CalledProcessError as e:
            print(">> Error installing packages. Please check your internet connection or requirements.txt.")
            sys.exit(1)

# --- 2. Environment Loader ---
def load_environment():
    """Safely loads .env variables."""
    try:
        # Lazy import dotenv
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


# --- 3. Startup Validation ---
def _syntax_check() -> None:
    """
    Compiles local sources to catch syntax errors before boot.
    """
    targets = ["core", "interfaces", "modules", "utils"]
    ok = True
    for folder in targets:
        if os.path.isdir(folder):
            ok = compileall.compile_dir(folder, quiet=1) and ok
    if not ok:
        print(">> Syntax check failed. Fix errors above and re-run.")
        sys.exit(1)


def _validate_settings_json() -> None:
    settings_path = os.path.join(os.getcwd(), "config", "settings.json")
    if not os.path.exists(settings_path):
        return
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            raise ValueError("settings.json must contain a JSON object.")
    except Exception as exc:
        print(f">> WARNING: Invalid config/settings.json ({exc}).")


def _validate_clients_payload(payload: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload, list):
        return ["clients.json must contain a list of clients."]
    for idx, client in enumerate(payload):
        if not isinstance(client, dict):
            errors.append(f"client[{idx}] must be a JSON object.")
            continue
        if "client_id" not in client or "name" not in client:
            errors.append(f"client[{idx}] missing client_id or name.")
        tax_profile = client.get("tax_profile")
        if tax_profile is not None and not isinstance(tax_profile, dict):
            errors.append(f"client[{idx}].tax_profile must be an object.")
        accounts = client.get("accounts", [])
        if accounts is None:
            continue
        if not isinstance(accounts, list):
            errors.append(f"client[{idx}].accounts must be a list.")
            continue
        for aidx, account in enumerate(accounts):
            if not isinstance(account, dict):
                errors.append(f"client[{idx}].accounts[{aidx}] must be a JSON object.")
                continue
            account_id = account.get("account_id")
            account_name = account.get("account_name")
            if not isinstance(account_id, str) or not account_id.strip():
                errors.append(f"client[{idx}].accounts[{aidx}].account_id missing or invalid.")
            if not isinstance(account_name, str) or not account_name.strip():
                errors.append(f"client[{idx}].accounts[{aidx}].account_name missing or invalid.")
            holdings = account.get("holdings", {})
            if holdings is not None and not isinstance(holdings, dict):
                errors.append(f"client[{idx}].accounts[{aidx}].holdings must be an object.")
            if isinstance(holdings, dict):
                for ticker, qty in holdings.items():
                    if not isinstance(ticker, str):
                        errors.append(f"client[{idx}].accounts[{aidx}].holdings has non-string key.")
                        break
                    if qty is not None and not isinstance(qty, (int, float)):
                        errors.append(f"client[{idx}].accounts[{aidx}].holdings[{ticker}] must be numeric.")
                        break
                    if isinstance(qty, (int, float)) and qty < 0:
                        errors.append(f"client[{idx}].accounts[{aidx}].holdings[{ticker}] must be non-negative.")
                        break
            lots = account.get("lots", {})
            if lots is not None and not isinstance(lots, dict):
                errors.append(f"client[{idx}].accounts[{aidx}].lots must be an object.")
            if isinstance(lots, dict):
                for ticker, entries in lots.items():
                    if not isinstance(entries, list):
                        errors.append(f"client[{idx}].accounts[{aidx}].lots[{ticker}] must be a list.")
                        break
                    for lidx, entry in enumerate(entries):
                        if not isinstance(entry, dict):
                            errors.append(f"client[{idx}].accounts[{aidx}].lots[{ticker}][{lidx}] must be an object.")
                            continue
                        qty = entry.get("qty")
                        if qty is not None and not isinstance(qty, (int, float)):
                            errors.append(f"client[{idx}].accounts[{aidx}].lots[{ticker}][{lidx}].qty must be numeric.")
                        if isinstance(qty, (int, float)) and qty <= 0:
                            errors.append(f"client[{idx}].accounts[{aidx}].lots[{ticker}][{lidx}].qty must be positive.")
                        basis = entry.get("basis")
                        if basis is not None and not isinstance(basis, (int, float)):
                            errors.append(f"client[{idx}].accounts[{aidx}].lots[{ticker}][{lidx}].basis must be numeric.")
                        if isinstance(basis, (int, float)) and basis < 0:
                            errors.append(f"client[{idx}].accounts[{aidx}].lots[{ticker}][{lidx}].basis must be non-negative.")
                        ts = entry.get("timestamp")
                        if ts is not None and not isinstance(ts, str):
                            errors.append(f"client[{idx}].accounts[{aidx}].lots[{ticker}][{lidx}].timestamp must be a string.")
                        if isinstance(ts, str) and ts and not _is_iso_timestamp(ts):
                            errors.append(f"client[{idx}].accounts[{aidx}].lots[{ticker}][{lidx}].timestamp is not ISO-8601.")
            manual_holdings = account.get("manual_holdings", [])
            if manual_holdings is not None and not isinstance(manual_holdings, list):
                errors.append(f"client[{idx}].accounts[{aidx}].manual_holdings must be a list.")
            if isinstance(manual_holdings, list):
                for midx, entry in enumerate(manual_holdings):
                    if not isinstance(entry, dict):
                        errors.append(f"client[{idx}].accounts[{aidx}].manual_holdings[{midx}] must be an object.")
                        continue
                    for key in ("quantity", "unit_price", "total_value"):
                        val = entry.get(key)
                        if val is None:
                            continue
                        if not isinstance(val, (int, float)):
                            errors.append(f"client[{idx}].accounts[{aidx}].manual_holdings[{midx}].{key} must be numeric.")
                            continue
                        if val < 0:
                            errors.append(f"client[{idx}].accounts[{aidx}].manual_holdings[{midx}].{key} must be non-negative.")
    return errors


def _is_iso_timestamp(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        datetime.fromisoformat(text)
        return True
    except Exception:
        return False


def _validate_clients_json() -> None:
    clients_path = os.path.join(os.getcwd(), "data", "clients.json")
    if not os.path.exists(clients_path):
        return
    if os.path.getsize(clients_path) == 0:
        return
    try:
        with open(clients_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        print(f">> WARNING: Invalid data/clients.json ({exc}).")
        return
    try:
        from modules.client_mgr.data_handler import DataHandler
        payload, migrated = DataHandler._migrate_clients_payload(payload)
        if migrated:
            with open(clients_path, "w", encoding="utf-8") as wf:
                json.dump(payload, wf, indent=4)
            print(">> INFO: Normalized legacy lot timestamps to ISO-8601.")
    except Exception as exc:
        print(f">> WARNING: Unable to normalize legacy lot timestamps ({exc}).")
    errors = _validate_clients_payload(payload)
    if errors:
        print(">> WARNING: data/clients.json schema issues detected:")
        for err in errors[:12]:
            print(f"   - {err}")

# --- 3. Main Application Launcher ---
if __name__ == "__main__":
    check_and_install_packages()

    load_environment()
    _syntax_check()
    _validate_settings_json()
    _validate_clients_json()


    try:
        from core.app import LotbookApp
        
        session = LotbookApp()
        session.run()
        
    except KeyboardInterrupt:
        if os.name == 'nt':
            _ = os.system('cls')
        else:
            _ = os.system('clear')
        print("\n>> Goodbye.\n")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n>> CRITICAL ERROR: {e}", style="bold red", markup=False)
        sys.exit(1)
