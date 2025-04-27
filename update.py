# update.py

import requests
import os
import logging

# ——————————— Configuration ———————————
GITHUB_API_LATEST = "https://api.github.com/repos/TheImaginear/dynamix/releases/latest"
BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE      = os.path.join(BASE_DIR, "VERSION")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_latest_release_info():
    """
    Fetch the latest release metadata from GitHub.
    Returns (tag_name, zipball_url, html_url).
    """
    resp = requests.get(GITHUB_API_LATEST, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data["tag_name"], data["zipball_url"], data["html_url"]

def read_current_version():
    """Read the locally stored version tag from VERSION_FILE."""
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def write_current_version(tag):
    """Persist the new version tag to VERSION_FILE."""
    try:
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            f.write(tag)
        logging.info(f"Wrote new version {tag} to {VERSION_FILE}")
    except Exception as e:
        logging.error(f"Failed to write VERSION_FILE: {e}")

def _version_tuple(v):
    """
    Turn 'v1.2.0' or '1.9.9' into (1,2,0) or (1,9,9) for comparison.
    """
    v = v.lstrip("v")
    parts = v.split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return ()

def is_update_available():
    """
    Return (bool available, str latest_tag, str html_url).
    Only True if latest_tag > current_version.
    """
    try:
        latest_tag, _, html_url = get_latest_release_info()
        current = read_current_version()
        if not current:
            return True, latest_tag, html_url

        if _version_tuple(latest_tag) > _version_tuple(current):
            return True, latest_tag, html_url
        else:
            return False, latest_tag, html_url

    except Exception as e:
        logging.error(f"Update check failed: {e}")
        return False, read_current_version() or "", None

def perform_update():
    """
    Stubbed out—auto-update is disabled.
    """
    logging.info("Auto-update is disabled; skipping perform_update().")
    return False, read_current_version()
