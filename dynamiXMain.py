from plexapi.server import PlexServer
from flask import Flask, render_template, jsonify, request, redirect, url_for, Response, flash
import os
import sys
import time
import threading
import random
import json
import traceback
from datetime import datetime
import logging
from update import is_update_available

# ——————————— Absolute paths & Logging Setup ———————————
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
library_lock = threading.Lock()
LOG_DIR  = os.path.join(BASE_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'dynamix.log')
CONFIG_FILE           = os.path.join(BASE_DIR, 'config.json')
USED_COLLECTIONS_FILE = os.path.join(BASE_DIR, 'used_collections.json')
USER_EXEMPTIONS_FILE  = os.path.join(BASE_DIR, 'user_exemptions.json')
RUN_STATE_FILE        = os.path.join(BASE_DIR, 'run_state.json')
CURRENT_ROLL_FILE     = 'current_roll.txt'

# Create logs directory if missing
os.makedirs(LOG_DIR, exist_ok=True)

for h in logging.root.handlers[:]:
    logging.root.removeHandler(h)

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)

# ----------------------- Default Seasonal Blocks -----------------------
import calendar
from datetime import date, timedelta
from enum import Enum

class HolidayType(Enum):
    STATIC       = 1    # fixed MM-DD each year
    EASTER       = 2    # compute via algorithm
    NTH_WEEKDAY  = 3    # nth weekday in a month

# ----------------------- Default Seasonal Blocks -----------------------
DEFAULT_SEASONAL_BLOCKS = [
    # — Static holidays —
    { "name": "New Year’s Day",      "type": HolidayType.STATIC,      "start": "01-01", "end": "01-01" },
    { "name": "Valentine’s Day",      "type": HolidayType.STATIC,      "start": "02-14", "end": "02-14" },
    { "name": "St. Patrick’s Day",    "type": HolidayType.STATIC,      "start": "03-17", "end": "03-17" },
    { "name": "April Fool’s Day",     "type": HolidayType.STATIC,      "start": "04-01", "end": "04-01" },
    { "name": "Earth Day",            "type": HolidayType.STATIC,      "start": "04-22", "end": "04-22" },
    { "name": "Cinco de Mayo",        "type": HolidayType.STATIC,      "start": "05-05", "end": "05-05" },
    { "name": "Juneteenth",           "type": HolidayType.STATIC,      "start": "06-19", "end": "06-19" },
    { "name": "Independence Day",     "type": HolidayType.STATIC,      "start": "07-04", "end": "07-04" },
    { "name": "Halloween",            "type": HolidayType.STATIC,      "start": "10-31", "end": "10-31" },
    { "name": "Veterans Day",         "type": HolidayType.STATIC,      "start": "11-11", "end": "11-11" },
    { "name": "Christmas",        "type": HolidayType.STATIC,      "start": "12-10", "end": "12-26" },
    { "name": "New Year’s Eve",       "type": HolidayType.STATIC,      "start": "12-27", "end": "12-31" },

    # — Month-long observance —
    { "name": "Pride Month",          "type": HolidayType.STATIC,      "start": "06-01", "end": "06-30" },

    # — Computed Easter-week (±2 days around Easter Sunday) —
    { "name": "Easter Week",         "type": HolidayType.EASTER,      "offset_start": -2, "offset_end": 2 },

    # — Major award-show weeks (nth Sunday, lasting 7 days) —
    { "name": "Golden Globes Week",  "type": HolidayType.NTH_WEEKDAY, "month": 1,  "weekday": 6, "nth": 1,  "duration_days": 7 },
    { "name": "SAG Awards Week",     "type": HolidayType.NTH_WEEKDAY, "month": 1,  "weekday": 6, "nth": 3,  "duration_days": 7 },
    { "name": "Grammy Awards Week",  "type": HolidayType.NTH_WEEKDAY, "month": 1,  "weekday": 6, "nth": 2,  "duration_days": 7 },
    { "name": "Academy Awards Week", "type": HolidayType.NTH_WEEKDAY, "month": 2,  "weekday": 6, "nth": -1, "duration_days": 7 },
    { "name": "Tony Awards Week",    "type": HolidayType.NTH_WEEKDAY, "month": 6,  "weekday": 6, "nth": 1,  "duration_days": 7 },
    { "name": "Emmy Awards Week",    "type": HolidayType.NTH_WEEKDAY, "month": 9,  "weekday": 6, "nth": 2,  "duration_days": 7 },

    # — U.S. “Nth-weekday” observances —
    { "name": "Memorial Day",        "type": HolidayType.NTH_WEEKDAY, "month": 5,  "weekday": 0, "nth": -1, "duration_days": 1 },  # Last Monday in May
    { "name": "Labor Day Week",      "type": HolidayType.NTH_WEEKDAY, "month": 9,  "weekday": 0, "nth": 1,  "duration_days": 7 },  # First Monday in Sept
    { "name": "Thanksgiving Week",   "type": HolidayType.NTH_WEEKDAY, "month": 11, "weekday": 3, "nth": 4,  "duration_days": 7 },  # 4th Thursday in Nov
    { "name": "Super Bowl Sunday",   "type": HolidayType.NTH_WEEKDAY, "month": 2,  "weekday": 6, "nth": 1,  "duration_days": 1 },  # First Sunday in Feb
]

# ----------------------- Keyword mappings for suggestion API -----------------------
HOLIDAY_KEYWORDS = {
    "New Year’s Day": [
        "new year", "new year's", "new years", "new year's day", "new years day", "nyd"
    ],
    "Valentine’s Day": [
        "valentine", "valentines", "valentine's", "valentine's day", "vday", "valentine day"
    ],
    "St. Patrick’s Day": [
        "st patrick", "st patricks", "st patrick's", "saint patrick", "saint patrick's day", "st patty's day"
    ],
    "April Fool’s Day": [
        "april fool", "april fools", "april fool's", "april fools' day", "april fool day"
    ],
    "Earth Day": [
        "earth day", "earthday"
    ],
    "Cinco de Mayo": [
        "cinco de mayo"
    ],
    "Juneteenth": [
        "juneteenth", "juneteenth day", "june 19", "june nineteenth"
    ],
    "Independence Day": [
        "independence day", "4th of july", "fourth of july", "july 4th", "july fourth"
    ],
    "Halloween": [
        "halloween", "halloween night"
    ],
    "Veterans Day": [
        "veterans day", "veteran's day", "veteransday"
    ],
    "Christmas": [
        "christmas", "xmas", "christmas day", "holiday"
    ],
    "New Year’s Eve": [
        "new year's eve", "new years eve", "nye", "best of"
    ],
    "Pride Month": [
        "pride month", "pride", "lgbt pride", "lgbtq pride"
    ],
    "Easter Week": [
        "easter week", "easter", "easter sunday", "good friday", "easter monday"
    ],
    "Golden Globes Week": [
        "golden globes", "golden globe awards", "goldenglobes"
    ],
    "SAG Awards Week": [
        "sag awards", "sag", "screen actors guild"
    ],
    "Grammy Awards Week": [
        "grammy awards", "grammys", "grammy"
    ],
    "Academy Awards Week": [
        "academy awards", "academy award", "oscars"
    ],
    "Tony Awards Week": [
        "tony awards", "tony", "tonys"
    ],
    "Emmy Awards Week": [
        "emmy awards", "emmy", "emmys"
    ],
    "Memorial Day": [
        "memorial day"
    ],
    "Labor Day Week": [
        "labor day", "labour day", "laborday"
    ],
    "Thanksgiving Week": [
        "thanksgiving", "thanksgiving day", "turkey day"
    ],
    "Super Bowl Sunday": [
        "super bowl sunday", "super bowl", "superbowl"
    ],
}

KOMETA_DEFAULT_TYPES = {
    # Awards & Separators
    "separator_award": ["movie", "show"],
    "bafta":           ["movie", "show"],
    "berlinale":       ["movie", "show"],
    "cannes":          ["movie", "show"],
    "cesar":           ["movie", "show"],
    "choice":          ["movie", "show"],
    "emmy":            ["movie", "show"],
    "golden":          ["movie", "show"],
    "oscars":          ["movie", "show"],
    "razzie":          ["movie", "show"],
    "sag":             ["movie", "show"],
    "spirit":          ["movie", "show"],
    "sundance":        ["movie", "show"],
    "tiff":            ["movie", "show"],
    "venice":          ["movie", "show"],

    # Charts
    "separator_chart": ["movie", "show"],
    "basic":           ["movie", "show"],
    "imdb":            ["movie", "show"],
    "letterboxd":      ["movie", "show"],
    "tmdb":            ["movie", "show"],
    "trakt":           ["movie", "show"],
    "tautulli":        ["movie", "show"],
    "anilist":         ["movie", "show"],
    "myanimelist":     ["movie", "show"],
    "other_chart":     ["movie", "show"],

    # Content
    "genre":           ["movie", "show"],
    "franchise":       ["movie", "show"],
    "universe":        ["movie", "show"],
    "based":           ["movie", "show"],
    "collectionless":  ["movie", "show"],

    # Ratings
    "content_rating_us": ["movie", "show"],
    "content_rating_uk": ["movie", "show"],
    "content_rating_de": ["movie", "show"],
    "content_rating_au": ["movie", "show"],
    "content_rating_nz": ["movie", "show"],
    "content_rating_mal": ["movie", "show"],
    "content_rating_cs":  ["movie", "show"],

    # Location
    "country":         ["movie", "show"],
    "region":          ["movie", "show"],
    "continent":       ["movie", "show"],

    # Media
    "aspect":          ["movie", "show"],
    "resolution":      ["movie", "show"],
    "audio_language":  ["movie", "show"],
    "subtitle_language":["movie", "show"],

    # People
    "actor":           ["movie", "show"],
    "director":        ["movie"],    # some are show-only
    "producer":        ["movie"],
    "writer":          ["movie"],

    # Production
    "network":         ["show"],
    "streaming":       ["movie", "show"],
    "studio":          ["movie", "show"],

    # Time
    "seasonal":        ["movie", "show"],
    "year":            ["movie", "show"],
    "decade":          ["movie", "show"],
}

SHARED_TEMPLATE_VARS = [
    # Sync modes
    "sync_mode", "sync_mode_<key>",
    # Visibility & ordering
    "collection_mode", "collection_section", "sort_prefix", "sort_title",
    # Enable/disable
    "use_all", "use_<key>", "delete_collections_named",
    # Backgrounds & posters
    "file_background", "file_background_<key>",
    "url_background",  "url_background_<key>",
    "file_poster",     "file_poster_<key>",
    "url_poster",      "url_poster_<key>",
    # Filtering & counts
    "minimum_items",   "minimum_items_<key>",
    "ignore_ids",      "ignore_imdb_ids",
    # Naming & mapping
    "name_mapping",    "name_<key>",
    "order_<key>",     "collection_order", "collection_order_<key>",
    # Language & locale
    "language",
    # External-tool overrides (Radarr/Sonarr)
    "radarr_add_missing",     "radarr_add_missing_<key>",
    "radarr_folder",          "radarr_folder_<key>",
    "radarr_monitor_existing","radarr_monitor_existing_<key>",
    "radarr_search",          "radarr_search_<key>",
    "radarr_tag",             "radarr_tag_<key>",
    "radarr_upgrade_existing","radarr_upgrade_existing_<key>",
    "sonarr_add_missing",     "sonarr_add_missing_<key>",
    "sonarr_folder",          "sonarr_folder_<key>",
    "sonarr_monitor_existing","sonarr_monitor_existing_<key>",
    "sonarr_search",          "sonarr_search_<key>",
    "sonarr_tag",             "sonarr_tag_<key>",
    "sonarr_upgrade_existing","sonarr_upgrade_existing_<key>",
    # Item-level tagging
    "item_radarr_tag",        "item_radarr_tag_<key>",
    "item_sonarr_tag",        "item_sonarr_tag_<key>",
    # Scheduling & data
    "schedule",               "schedule_<key>",
    "data",                   "append_data", "remove_data", "exclude",
    # Plex visibility pins
    "visible_home",           "visible_home_<key>",
    "visible_library",        "visible_library_<key>",
    "visible_shared",         "visible_shared_<key>",
]

# 2. Any defaults that expose additional, file-specific knobs:
FILE_SPECIFIC_VARS = {
    "oscars":    ["start_year", "end_year"],
    "imdb":      ["min_rating", "max_rating"],
    "genre":     ["include_unknown", "genre_list"],
    "year":      ["min_year", "max_year"],
    # …if you discover any others on their individual pages, add them here…
}

KOMETA_DEFAULT_VARS = {
    key: SHARED_TEMPLATE_VARS + FILE_SPECIFIC_VARS.get(key, [])
    for key in KOMETA_DEFAULT_TYPES
}

# Stores the current active pre-roll block name
CURRENT_ROLL_FILE = 'current_roll.txt'

# ------------------------------ Helper Functions ------------------------------

def process_library(plex, library_name, config, used_collections,
                    user_exemptions, pinning_targets, always_pin_new_episodes,
                    seasonal_blocks, pinned_collections, exclusion_days,
                    all_recently_pinned):
    """
    Do everything you were doing in the per-library loop:
    - build a list of titles that actually exist in this library
    - unpin old items (except “New Episodes” when enabled)
    - pin new ones
    - update exclusions
    - collect titles into all_recently_pinned
    """
    actual_pins = []

    try:
        # Fetch this library’s section once up-front
        lib_section = plex.library.section(library_name)
        available_titles = {c.title for c in lib_section.collections()}

        # (A) “New Episodes” if present
        if always_pin_new_episodes and "New Episodes" in available_titles:
            actual_pins.append("New Episodes")

        # (B) Always-pinned collections
        for pc in pinned_collections:
            title = pc.get("title", "")
            if library_name in pc.get("libraries", []) and title in available_titles:
                actual_pins.append(title)

        # (C) Seasonal blocks
        for b in pin_seasonal_blocks_for_library(library_name, seasonal_blocks):
            title = b["title"]
            if title in available_titles:
                actual_pins.append(title)

        # (D) Time-block/random picks
        time_picks = gather_time_block_items_for_library(
            plex, library_name, config, used_collections, user_exemptions
        )
        for item in time_picks:
            title = item["title"]
            if title in available_titles:
                actual_pins.append(title)

        # — Unpin everything (except “New Episodes” when needed) —
        for coll in lib_section.collections():
            if not (always_pin_new_episodes and coll.title == "New Episodes"):
                apply_pinning(coll, pinning_targets, action="demote")

        # — Pin each verified title —
        for title in actual_pins:
            coll = next((c for c in lib_section.collections() if c.title == title), None)
            if coll:
                apply_pinning(coll, pinning_targets, action="promote")

    except Exception as e:
        logging.error(f"Error in thread for '{library_name}': {e}")

    # — Update exclusion list & shared run-state with only the pins we actually did —
    with library_lock:
        log_and_update_exclusion_list(actual_pins, used_collections, exclusion_days)
        all_recently_pinned.extend(f"{t} ({library_name})" for t in actual_pins)


def compute_easter(year):
    # Anonymous Gregorian algorithm
    a = year % 19
    b = year // 100; c = year % 100
    d = (19*a + b - b//4 - ((b - (b+8)//25 +1)//3) +15) % 30
    e = (32 + 2*(b%4) + 2*(c//4) - d - (c%4)) % 7
    f = d + e - 7*((a + 11*d + 22*e)//451) + 114
    month = f//31
    day   = (f % 31) + 1
    return date(year, month, day)

def find_nth_weekday(year, month, weekday, nth):
    # weekday: Mon=0…Sun=6; nth: 1=first, 2=second, … -1=last
    cal = calendar.monthcalendar(year, month)
    if nth > 0:
        week = cal[nth-1]
        if week[weekday] == 0:
            week = cal[nth]  # fallback
        return date(year, month, week[weekday])
    else:
        for week in reversed(cal):
            if week[weekday]:
                return date(year, month, week[weekday])

def apply_pinning(collection, pinning_targets, action="promote"):
    """
    Apply pinning or unpinning based on user-selected targets.
    :param collection: The Plex collection object.
    :param pinning_targets: A dictionary indicating the selected pinning targets.
    :param action: Either 'promote' or 'demote'.
    """
    try:
        hub = collection.visibility()
        if action == "promote":
            if pinning_targets.get("library_recommended", False):
                hub.promoteRecommended()
            if pinning_targets.get("home", False):
                hub.promoteHome()
            if pinning_targets.get("shared_home", False):
                hub.promoteShared()
        elif action == "demote":
            if pinning_targets.get("library_recommended", False):
                hub.demoteRecommended()
            if pinning_targets.get("home", False):
                hub.demoteHome()
            if pinning_targets.get("shared_home", False):
                hub.demoteShared()
    except Exception as e:
        logging.error(f"Error during {action} for collection '{collection.title}': {e}")

def sanitize_time_blocks(time_blocks):
    """
    Ensure time_blocks is properly formatted as a list of dictionaries.
    """
    if not isinstance(time_blocks, list):
        logging.warning(f"Sanitizing time_blocks: expected list but got {type(time_blocks)}. Resetting to empty.")
        return []
    sanitized = []
    for block in time_blocks:
        if not isinstance(block, dict):
            logging.warning(f"Invalid block format: expected dict but got {type(block)}. Skipping.")
            continue
        required_keys = {"name", "start_time", "end_time", "limit", "days", "libraries"}
        if not required_keys.issubset(block.keys()):
            logging.warning(f"Block missing required keys: {block}. Skipping.")
            continue
        if not isinstance(block["days"], list) or not isinstance(block["libraries"], list):
            logging.warning(f"Invalid types in block: {block}. Skipping.")
            continue
        sanitized.append(block)
    return sanitized

def load_config():
    """
    Load configuration from the CONFIG_FILE.
    """
    if not os.path.exists(CONFIG_FILE):
        logging.error(f"Configuration file '{CONFIG_FILE}' not found. Creating a default configuration.")
        return {}

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError:
        logging.error(f"Configuration file '{CONFIG_FILE}' is empty or invalid. Resetting to default.")
        return {}

    # Ensure libraries_settings is a dictionary
    libraries_settings = config.get("libraries_settings", {})
    if not isinstance(libraries_settings, dict):
        logging.warning(f"Sanitizing libraries_settings: resetting to empty dictionary.")
        libraries_settings = {}
    config["libraries_settings"] = libraries_settings

    # Sanitize time_blocks as a global list
    time_blocks = config.get("time_blocks", [])
    config["time_blocks"] = sanitize_time_blocks(time_blocks)

    # Ensure seasonal_blocks is a list
    if "seasonal_blocks" not in config or not isinstance(config["seasonal_blocks"], list):
        config["seasonal_blocks"] = []

    # Ensure pinned_collections is a list
    if "pinned_collections" not in config or not isinstance(config["pinned_collections"], list):
        config["pinned_collections"] = []

    # Ensure pre_roll_folder is a string
    if "pre_roll_folder" not in config or not isinstance(config["pre_roll_folder"], str):
        config["pre_roll_folder"] = ""

    # Ensure preroll_blocks is a list
    if "preroll_blocks" not in config or not isinstance(config["preroll_blocks"], list):
        config["preroll_blocks"] = []

    # Ensure default_preroll_filename is a string
    if "default_preroll_filename" not in config or not isinstance(config["default_preroll_filename"], str):
        config["default_preroll_filename"] = ""

    # Ensure auth settings exist
    if "auth_enabled" not in config or not isinstance(config["auth_enabled"], bool):
        config["auth_enabled"] = False
    if "auth_username" not in config or not isinstance(config["auth_username"], str):
        config["auth_username"] = ""
    if "auth_password" not in config or not isinstance(config["auth_password"], str):
        config["auth_password"] = ""

    return config

def save_config(config):
    """
    Save the configuration dictionary to CONFIG_FILE.
    """
    try:
        logging.info(f"Final configuration to save: {json.dumps(config, indent=4)}")
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        logging.info("Configuration file saved successfully.")
    except Exception as e:
        logging.error(f"Error saving configuration file: {e}")
        raise

def load_used_collections():
    """
    Load used collections from USED_COLLECTIONS_FILE.
    """
    if not os.path.exists(USED_COLLECTIONS_FILE):
        return {}
    with open(USED_COLLECTIONS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_pin_cycle_once():
    config = load_config()
    plex = connect_to_plex(config)
    libraries = config.get("libraries", [])
    pinning_targets = config.get("pinning_targets", {})
    always_pin = config.get("always_pin_new_episodes", False)
    exclusion_days = config.get("exclusion_days", 3)
    separate = config.get("separate_pinning", False)
    seasonal_blocks = config.get("seasonal_blocks", [])
    pinned_cols = config.get("pinned_collections", [])
    used = load_used_collections()
    ex = load_user_exemptions()
    all_pinned = []

    if not separate:
        threads = []
        for lib in libraries:
            t = threading.Thread(
                target=process_library,
                args=(plex, lib, config, used, ex, pinning_targets,
                      always_pin, seasonal_blocks, pinned_cols,
                      exclusion_days, all_pinned),
                daemon=True
            )
            t.start(); threads.append(t)
        for t in threads: t.join()
    else:
        # Phase 1: library only
        lib_targets = { "library_recommended": pinning_targets.get("library_recommended", False),
                        "home": False, "shared_home": False }
        threads = []
        for lib in libraries:
            t = threading.Thread(
                target=process_library,
                args=(plex, lib, config, used, ex, lib_targets,
                      always_pin, seasonal_blocks, pinned_cols,
                      exclusion_days, all_pinned),
                daemon=True
            )
            t.start(); threads.append(t)
        for t in threads: t.join()

        # Phase 2: home/shared only
        home_targets = { "library_recommended": False,
                         "home": pinning_targets.get("home", False),
                         "shared_home": pinning_targets.get("shared_home", False) }
        threads = []
        for lib in libraries:
            t = threading.Thread(
                target=process_library,
                args=(plex, lib, config, used, ex, home_targets,
                      always_pin, seasonal_blocks, pinned_cols,
                      exclusion_days, all_pinned),
                daemon=True
            )
            t.start(); threads.append(t)
        for t in threads: t.join()

    # Update run_state
    state = load_run_state()
    now = datetime.now()
    state["last_run"]    = now.strftime("%Y-%m-%d %H:%M:%S")
    state["next_run"]    = (now + timedelta(seconds=config.get("pinning_interval",30)*60))\
                             .strftime("%Y-%m-%d %H:%M:%S")
    state["pinned_today"] = state.get("pinned_today", 0) + len(all_pinned)
    state["recently_pinned"] = sorted(set(all_pinned))
    save_run_state(state)
    return all_pinned

def save_used_collections(used_collections):
    """
    Save used collections to USED_COLLECTIONS_FILE.
    """
    with open(USED_COLLECTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(used_collections, f, ensure_ascii=False, indent=4)
    logging.info("Used collections file saved.")

def load_user_exemptions():
    """
    Load user exemptions from USER_EXEMPTIONS_FILE.
    """
    if not os.path.exists(USER_EXEMPTIONS_FILE):
        return []
    with open(USER_EXEMPTIONS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_user_exemptions(user_exemptions):
    """
    Save user exemptions to USER_EXEMPTIONS_FILE.
    """
    with open(USER_EXEMPTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(user_exemptions, f, ensure_ascii=False, indent=4)
    logging.info("User exemptions file saved.")

def reset_exclusion_list_file():
    """
    Reset the exclusion list by clearing USED_COLLECTIONS_FILE.
    """
    with open(USED_COLLECTIONS_FILE, 'w', encoding='utf-8') as f:
        f.write("{}")
    logging.info("Exclusion list file has been reset.")

def connect_to_plex(config):
    """
    Connect to the Plex server using the provided configuration.
    """
    logging.info("Connecting to Plex server...")
    plex = PlexServer(config['plex_url'], config['plex_token'])
    logging.info("Connected to Plex server successfully.")
    return plex

def handle_new_episodes_pinning(plex, libraries, always_pin_new_episodes, pinning_targets):
    """
    Handle pinning or unpinning of 'New Episodes' collections based on configuration.
    """
    logging.info("Handling 'New Episodes' collections...")
    for library_name in libraries:
        try:
            library = plex.library.section(library_name)
            for collection in library.collections():
                if collection.title.lower() == "new episodes":
                    if always_pin_new_episodes:
                        apply_pinning(collection, pinning_targets, action="promote")
                        logging.info(f"'New Episodes' collection pinned in '{library_name}'.")
                    else:
                        apply_pinning(collection, pinning_targets, action="demote")
                        logging.info(f"'New Episodes' collection unpinned in '{library_name}'.")
                    break
        except Exception as e:
            logging.error(f"Error accessing library '{library_name}': {e}")

def unpin_collections(plex, libraries, always_pin_new_episodes, pinning_targets):
    """
    Unpin all collections except 'New Episodes' if always_pin_new_episodes is True.
    """
    logging.info("Unpinning currently pinned collections...")
    for library_name in libraries:
        try:
            library = plex.library.section(library_name)
            for collection in library.collections():
                # Skip unpinning 'New Episodes' if always_pin_new_episodes is enabled
                if always_pin_new_episodes and collection.title.lower() == "new episodes":
                    continue
                apply_pinning(collection, pinning_targets, action="demote")
                logging.info(f"Collection '{collection.title}' unpinned in '{library_name}'.")
        except Exception as e:
            logging.error(f"Error accessing library '{library_name}': {e}")

def log_and_update_exclusion_list(pinned_titles, used_collections, exclusion_days):
    """
    Log pinned collection titles and update the exclusion list with their expiration dates.
    Instead of expecting a list of Plex collection objects, we just expect a list of strings.
    """
    current_date = datetime.now().date()
    for title in pinned_titles:
        expiration_date = (current_date + timedelta(days=exclusion_days)).strftime('%Y-%m-%d')
        used_collections[title] = expiration_date
        logging.info(f"Added '{title}' to exclusion list (expires: {expiration_date}).")

    save_used_collections(used_collections)

def get_current_time_block(config, library_name):
    """
    Determine the current time block (and limit) for a given library,
    based on the global time blocks that specify which libraries/days they apply to.
    """
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    today_abbrev = now.strftime("%a")  # e.g. "Mon", "Tue", ...

    default_limits = config.get("default_limits", {})
    library_default_limit = default_limits.get(library_name, 5)

    global_time_blocks = config.get("time_blocks", [])

    matching_blocks = []
    for block in global_time_blocks:
        if library_name not in block.get("libraries", []):
            continue
        if today_abbrev not in block.get("days", []):
            continue
        if block.get("start_time") <= current_time < block.get("end_time"):
            matching_blocks.append(block)

    if matching_blocks:
        block = matching_blocks[0]
        return block.get("name", "Default"), block.get("limit", library_default_limit)
    else:
        return "Default", library_default_limit

def pin_seasonal_blocks_for_library(library_name, seasonal_blocks):
    """
    Return a list of dictionaries for active seasonal blocks.
    Each dict has { "title": <collection_name> } if the block is active
    and includes 'library_name' in its libraries list.
    """
    current_date = datetime.now().date()
    current_month_day = (current_date.month, current_date.day)

    pinned_items = []

    for block in seasonal_blocks:
        if library_name not in block.get("libraries", []):
            continue

        # Parse start/end, supporting YYYY-MM-DD or MM-DD
        try:
            # Start date
            sd_parts = block["start_date"].split("-")
            if len(sd_parts) == 3:
                _, sm, sd = sd_parts
            else:
                sm, sd = sd_parts
            start_month, start_day = int(sm), int(sd)

            # End date
            ed_parts = block["end_date"].split("-")
            if len(ed_parts) == 3:
                _, em, ed = ed_parts
            else:
                em, ed = ed_parts
            end_month, end_day = int(em), int(ed)
        except Exception as e:
            logging.error(
                f"Invalid seasonal block format for '{block.get('name','Unnamed')}': {e}"
            )
            continue

        start_md = (start_month, start_day)
        end_md   = (end_month, end_day)

        # Check if current day is within [start_md, end_md], accounting for wrap-around
        if start_md <= end_md:
            is_active = (start_md <= current_month_day <= end_md)
        else:
            # E.g., crosses New Year's (12-30 to 01-05)
            is_active = (
                current_month_day >= start_md
                or current_month_day <= end_md
            )

        if is_active:
            collection_name = block.get("collection", "")
            pinned_items.append({
                "title": collection_name
            })

    return pinned_items

def gather_time_block_items_for_library(plex, library_name, config, used_collections, user_exemptions):
    """
    Check which time block is active for `library_name`,
    then pick collections that meet the limit, min_items, etc.
    Return a list of dicts { "title": <collection_title> }.

    If there aren’t enough valid collections to meet `current_limit`, the dynamic
    exclusion list is reset and the function retries once. If still not enough,
    it returns an empty list.
    """

    library = plex.library.section(library_name)
    all_collections = library.collections()

    block_name, current_limit = get_current_time_block(config, library_name)
    logging.info(f"Time Block for '{library_name}': {block_name}, limit={current_limit}")

    min_items = config.get("minimum_items", 1)

    def find_valid_collections(allow_used=True):
        # If allow_used == True, we exclude anything in used_collections
        # If allow_used == False, we ignore used_collections
        return [
            c for c in all_collections
            if len(c.items()) >= min_items
               and c.title not in user_exemptions
               and (c.title not in used_collections if allow_used else True)
        ]

    valid = find_valid_collections(allow_used=True)

    # Not enough the first time? Reset and retry
    if len(valid) < current_limit:
        logging.warning(
            f"Not enough valid collections in '{library_name}' for limit={current_limit}. "
            f"Only {len(valid)} available. RESETTING dynamic exclusion list and RETRYING..."
        )

        # 2) Reset dynamic exclusions
        reset_exclusion_list_file()
        used_collections.clear()
        used_collections.update(load_used_collections())  # Optionally reload if needed

        # 3) Now try again without excluding any used_collections
        valid = find_valid_collections(allow_used=False)

        if len(valid) < current_limit:
            logging.warning(
                f"Even after reset, still not enough collections. "
                f"Found {len(valid)} but need {current_limit}. Returning empty."
            )
            return []

    # 4) We have enough valid collections; pick randomly
    selected = random.sample(valid, current_limit)

    pinned_items = []
    for c in selected:
        pinned_items.append({"title": c.title})

    return pinned_items

def pin_library_in_order(plex, library_name, pinned_items, pinning_targets, always_pin_new_episodes):
    """
    Remove all pinned items from this library (except 'New Episodes' if always_pin_new_episodes),
    then pin each item in pinned_items. (Pin order logic removed.)
    """
    logging.info(f"Unpinning items in library '{library_name}' (except 'New Episodes').")
    try:
        library = plex.library.section(library_name)
        for collection in library.collections():
            if always_pin_new_episodes and collection.title.lower() == "new episodes":
                continue
            apply_pinning(collection, pinning_targets, action="demote")
            logging.info(f"Collection '{collection.title}' unpinned in '{library_name}'.")
    except Exception as e:
        logging.error(f"Error unpinning in '{library_name}': {e}")
        return

    # Now just pin each item in any arbitrary order
    for item in pinned_items:
        title = item["title"]
        try:
            collection = next(
                (c for c in library.collections() if c.title == title),
                None
            )
            if collection:
                apply_pinning(collection, pinning_targets, action="promote")
                logging.info(f"Collection '{title}' pinned in '{library_name}'.")
                # If needed, sleep to give Plex time to reflect changes
                time.sleep(1)
            else:
                logging.warning(
                    f"Collection '{title}' not found in '{library_name}'."
                )
        except Exception as e:
            logging.error(f"Error pinning '{title}' in '{library_name}': {e}")

def pin_defined_collections_global(plex, pinned_collections, pinning_targets):
    """
    Pins an always-present set of collections across specified libraries.
    (Pin order logic removed.)
    """
    logging.info("Pinning always-pinned collections (from 'pinned_collections')...")

    for idx, pinned_item in enumerate(pinned_collections, start=1):
        title = pinned_item.get("title", "Unnamed Collection")
        libs = pinned_item.get("libraries", [])
        logging.info(f"({idx}) Pinning '{title}' for libraries: {libs}")

        for lib in libs:
            try:
                library = plex.library.section(lib)
                collection = next(
                    (c for c in library.collections() if c.title == title),
                    None
                )
                if collection:
                    apply_pinning(collection, pinning_targets, action="promote")
                    logging.info(f"Pinned '{title}' in '{lib}'.")
                else:
                    logging.warning(f"Collection '{title}' not found in library '{lib}'.")
            except Exception as e:
                logging.error(f"Error pinning '{title}' in '{lib}': {e}")

RUN_STATE_FILE = "run_state.json"

def load_run_state():
    """
    Load the run state (last_run, next_run, pinned_today, recently_pinned, state).
    If the last_run date is before today, reset pinned_today.
    Ensure we always have a 'state' key.
    """
    if not os.path.exists(RUN_STATE_FILE):
        return {
            "last_run": None,
            "next_run": None,
            "pinned_today": 0,
            "recently_pinned": [],
            "state": "stopped"
        }

    with open(RUN_STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)

    # Reset daily counters if last_run in a prior day
    last_run_str = state.get("last_run")
    if last_run_str:
        try:
            last_run_date = datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S").date()
            today = datetime.now().date()
            if last_run_date < today:
                state["pinned_today"] = 0
                with open(RUN_STATE_FILE, "w", encoding="utf-8") as wf:
                    json.dump(state, wf, indent=4, ensure_ascii=False)
        except Exception:
            pass

    # Guarantee we have a 'state' field
    state.setdefault("state", "waiting" if state.get("running", False) else "stopped")
    return state


def save_run_state(state):
    with open(RUN_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)


# ------------------------------ Pre-Roll Management ------------------------------

def manage_prerolls(config):
    """
    Checks if today's date falls into any pre-roll date block.
    If it does, rename the corresponding file to 'PlexMainPreRoll.<ext>', if not already set.
    If no Time block is active, set the pre-roll to the default file.
    Store the 'current' roll file name in current_roll.txt. If the correct roll is already set, do nothing.

    Instead of deleting an existing 'PlexMainPreRoll', we rename it to <current_roll_filename><ext>.
    """
    folder = config.get("pre_roll_folder", "")
    if not folder or not os.path.exists(folder):
        # Folder might not be set or doesn't exist; skip quietly.
        logging.info("Pre-roll folder not set or doesn't exist. Skipping pre-roll management.")
        return

    # Load the currently active roll file name from current_roll.txt
    current_roll_path = os.path.join(folder, CURRENT_ROLL_FILE)
    current_roll_filename = ""
    if os.path.exists(current_roll_path):
        try:
            with open(current_roll_path, 'r', encoding='utf-8') as f:
                current_roll_filename = f.read().strip()
        except Exception as e:
            logging.warning(f"Could not read current_roll file: {e}")

    # Determine if there is an active preroll block (the first block that matches today's date)
    now = datetime.now().date()
    mmdd = (now.month, now.day)
    active_block = None

    for block in config.get("preroll_blocks", []):
        try:
            start_month, start_day = map(int, block["start_date"].split("-"))
            end_month, end_day = map(int, block["end_date"].split("-"))
        except Exception as e:
            logging.error(f"Invalid preroll block dates for block '{block.get('name','Unnamed')}': {e}")
            continue

        start_md = (start_month, start_day)
        end_md = (end_month, end_day)

        if start_md <= end_md:
            is_active = (start_md <= mmdd <= end_md)
        else:
            # handle wrap-around (e.g., 12-30 to 01-05)
            is_active = (mmdd >= start_md or mmdd <= end_md)

        if is_active:
            active_block = block
            break

    if active_block:
        target_filename = active_block.get("filename", "")
        if not target_filename:
            logging.warning(f"Active block has no 'filename' specified. Cannot set pre-roll.")
            return

        target_file_path = os.path.join(folder, target_filename)
        _, file_ext = os.path.splitext(target_filename)
        plexmain_file_path = os.path.join(folder, f"PlexMainPreRoll{file_ext}")

        # If the correct file is already set, do nothing
        if current_roll_filename == target_filename:
            logging.info(f"Pre-roll '{target_filename}' is already active. No action needed.")
            return

        # Rename existing PlexMainPreRoll if it exists
        if os.path.exists(plexmain_file_path):
            try:
                if current_roll_filename:
                    old_file_new_path = os.path.join(folder, current_roll_filename)
                    os.rename(plexmain_file_path, old_file_new_path)
                    logging.info(f"Renamed old PlexMainPreRoll to '{current_roll_filename}'.")
                else:
                    # If there's no known previous roll file name, remove the file
                    os.remove(plexmain_file_path)
                    logging.info(f"No previous roll file name found. Removed old PlexMainPreRoll: {plexmain_file_path}")
            except Exception as e:
                logging.warning(f"Could not rename old 'PlexMainPreRoll': {e}")

        # Now rename the target file -> PlexMainPreRoll
        if os.path.exists(target_file_path):
            try:
                new_name = f"PlexMainPreRoll{file_ext}"
                new_path = os.path.join(folder, new_name)
                os.rename(target_file_path, new_path)
                logging.info(f"Renamed '{target_filename}' -> '{new_name}' for active pre-roll block.")
            except Exception as e:
                logging.error(f"Failed to rename '{target_file_path}' to 'PlexMainPreRoll': {e}")
                return
        else:
            logging.error(f"Target file '{target_filename}' not found in folder '{folder}'. Cannot set pre-roll.")
            return

        # Save the new current_roll_filename
        try:
            with open(current_roll_path, 'w', encoding='utf-8') as f:
                f.write(target_filename)
            logging.info(f"Updated current_roll.txt with '{target_filename}'.")
        except Exception as e:
            logging.error(f"Failed to write current_roll.txt: {e}")

    else:
        # No active pre-roll block; use default pre-roll
        default_filename = config.get("default_preroll_filename", "")
        if not default_filename:
            logging.warning("No Time block active and no default pre-roll file configured.")
            return

        default_file_path = os.path.join(folder, default_filename)
        _, file_ext = os.path.splitext(default_filename)
        plexmain_file_path = os.path.join(folder, f"PlexMainPreRoll{file_ext}")

        # Check if default is already set
        if current_roll_filename == default_filename:
            logging.info("Default pre-roll is already active. No action needed.")
            return

        # Rename existing PlexMainPreRoll if it exists
        if os.path.exists(plexmain_file_path):
            try:
                if current_roll_filename:
                    old_file_new_path = os.path.join(folder, current_roll_filename)
                    os.rename(plexmain_file_path, old_file_new_path)
                    logging.info(f"Renamed old PlexMainPreRoll to '{current_roll_filename}'.")
                else:
                    # If there's no known previous roll file name, remove the file
                    os.remove(plexmain_file_path)
                    logging.info(f"No previous roll file name found. Removed old PlexMainPreRoll: {plexmain_file_path}")
            except Exception as e:
                logging.warning(f"Could not rename old 'PlexMainPreRoll': {e}")

        # Now rename the default file -> PlexMainPreRoll
        if os.path.exists(default_file_path):
            try:
                new_name = f"PlexMainPreRoll{file_ext}"
                new_path = os.path.join(folder, new_name)
                os.rename(default_file_path, new_path)
                logging.info(f"Renamed '{default_filename}' -> '{new_name}' as default pre-roll.")
            except Exception as e:
                logging.error(f"Failed to rename '{default_file_path}' to 'PlexMainPreRoll': {e}")
                return
        else:
            logging.error(f"Default pre-roll file '{default_filename}' not found in folder '{folder}'. Cannot set pre-roll.")
            return

        # Save the new current_roll_filename as default
        try:
            with open(current_roll_path, 'w', encoding='utf-8') as f:
                f.write(default_filename)
            logging.info(f"Updated current_roll.txt with '{default_filename}'.")
        except Exception as e:
            logging.error(f"Failed to write current_roll.txt: {e}")

# ------------------------------ Main Automation Function ------------------------------

def main(gui_instance=None, stop_event=None):
    logging.info("Starting DynamiX automation...")

    try:
        config = load_config()
        if not config:
            logging.error("Configuration could not be loaded. Exiting.")
            return
        logging.info("Configuration loaded successfully.")

        plex = connect_to_plex(config)
        libraries = config.get("libraries", [])
        pinning_targets = config.get("pinning_targets", {})
        pinning_interval = config.get("pinning_interval", 30) * 60
        always_pin_new_episodes = config.get("always_pin_new_episodes", False)
        exclusion_days = config.get("exclusion_days", 3)
        separate_pinning = config.get("separate_pinning", False)

        seasonal_blocks = config.get("seasonal_blocks", [])
        pinned_collections = config.get("pinned_collections", [])

        used_collections = load_used_collections()
        user_exemptions = load_user_exemptions()

        logging.info("Entering main automation loop.")

        while not stop_event.is_set():
            run_state = load_run_state()
            run_state["state"] = "running"
            save_run_state(run_state)
            # 1) Clean up expired exclusions
            current_date = datetime.now().date()
            used_collections = {
                name: date
                for name, date in used_collections.items()
                if datetime.strptime(date, '%Y-%m-%d').date() > current_date
            }
            save_used_collections(used_collections)
            if stop_event.is_set():
                break

            # 2) Manage Pre-Rolls
            manage_prerolls(config)
            if stop_event.is_set():
                break

            all_recently_pinned = []
            if not separate_pinning:
                # ── old single pass ──
                threads = []
                for lib in libraries:
                    if stop_event.is_set(): break
                    t = threading.Thread(
                        target=process_library,
                        args=(
                            plex, lib, config,
                            used_collections, user_exemptions,
                            pinning_targets, always_pin_new_episodes,
                            seasonal_blocks, pinned_collections,
                            exclusion_days, all_recently_pinned
                        ),
                        daemon=True
                    )
                    t.start()
                    threads.append(t)
                for t in threads: t.join()

            else:
                # ── Phase 1: library‐recommended only ──
                lib_targets = {
                    "library_recommended": pinning_targets.get("library_recommended", False),
                    "home": False,
                    "shared_home": False
                }
                threads = []
                for lib in libraries:
                    if stop_event.is_set(): break
                    t = threading.Thread(
                        target=process_library,
                        args=(
                            plex, lib, config,
                            used_collections, user_exemptions,
                            lib_targets, always_pin_new_episodes,
                            seasonal_blocks, pinned_collections,
                            exclusion_days, all_recently_pinned
                        ),
                        daemon=True
                    )
                    t.start()
                    threads.append(t)
                for t in threads: t.join()

                # ── Phase 2: home/shared‐home only ──
                home_targets = {
                    "library_recommended": False,
                    "home": pinning_targets.get("home", False),
                    "shared_home": pinning_targets.get("shared_home", False)
                }
                threads = []
                for lib in libraries:
                    if stop_event.is_set(): break
                    t = threading.Thread(
                        target=process_library,
                        args=(
                            plex, lib, config,
                            used_collections, user_exemptions,
                            home_targets, always_pin_new_episodes,
                            seasonal_blocks, pinned_collections,
                            exclusion_days, all_recently_pinned
                        ),
                        daemon=True
                    )
                    t.start()
                    threads.append(t)
                for t in threads: t.join()

            # 6) GUI callback
            if gui_instance and not stop_event.is_set():
                gui_instance.after(0, gui_instance.refresh_exemptions_and_exclusions)

            # Track run timing
            run_state = load_run_state()
            now = datetime.now()
            run_state["last_run"] = now.strftime("%Y-%m-%d %H:%M:%S")
            run_state["next_run"] = (now + timedelta(seconds=pinning_interval)).strftime("%Y-%m-%d %H:%M:%S")
            run_state["pinned_today"] = run_state.get("pinned_today", 0) + len(all_recently_pinned)
            run_state["recently_pinned"] = sorted(set(all_recently_pinned))
            run_state["state"] = "waiting"
            save_run_state(run_state)

            logging.info(f"Waiting up to {pinning_interval // 60} minutes or until stopped.")

            if stop_event.wait(pinning_interval):
                logging.info("Stop signal received — exiting main loop.")
                break

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        traceback.print_exc()
    finally:
        logging.info("Automation script terminated.")

# ------------------------------ Web UI Section ------------------------------

app = Flask(__name__)

automation_thread = None
stop_event = threading.Event()

@app.route("/dashboard_data")
def dashboard_data():
    cfg    = load_config()
    used   = load_used_collections()
    ex     = load_user_exemptions()
    run_st = load_run_state()

    # 1) Compute total collections
    try:
        plex = connect_to_plex(cfg)
        total = sum(len(plex.library.section(lib).collections())
                    for lib in cfg.get("libraries", []))
    except Exception:
        total = "—"

    # 2) Build summaries
    libs = cfg.get("libraries", [])
    active = []
    for lib in libs:
        name, limit = get_current_time_block(cfg, lib)
        active.append(f"{lib}: {name} ({limit})")
    seasonal = []
    for lib in libs:
        for item in pin_seasonal_blocks_for_library(lib, cfg.get("seasonal_blocks", [])):
            seasonal.append(f"{lib}: {item['title']}")

    # 3) Read the real current pre-roll filename
    folder = cfg.get("pre_roll_folder", "")
    current_roll = ""
    current_path = os.path.join(folder, CURRENT_ROLL_FILE)
    if os.path.exists(current_path):
        try:
            with open(current_path, 'r', encoding='utf-8') as f:
                current_roll = f.read().strip()
        except Exception:
            current_roll = ""

    # 4) Return everything in one JSON
    return jsonify({
        "total_collections":  total,
        "pinned_today":       run_st.get("pinned_today", 0),
        "exclusions_active":  len(used),
        "exemptions_count":   len(ex),
        "last_run":           run_st.get("last_run", "—"),
        "next_run":           run_st.get("next_run", "—"),
        "state":              run_st.get("state", "stopped"),
        "active_time_block":  active,
        "library_limits":     [f"{lib}: {cfg.get('default_limits',{}).get(lib,'?')}" for lib in libs],
        "seasonal_blocks":    seasonal,
        "pinned_collections": run_st.get("recently_pinned", []),
        "current_roll":       current_roll
    })

@app.route("/update/check")
def web_update_check():
    available, latest_tag, html_url = is_update_available()
    return jsonify(
        update_available=available,
        latest_version=latest_tag,
        release_url=html_url
    )

@app.route('/service-worker.js')
def service_worker():
    return app.send_static_file('js/service-worker.js')


@app.before_request
def require_basic_auth():
    cfg = load_config()
    # Skip auth when disabled or for static assets
    if not cfg.get("auth_enabled", False) or request.endpoint == 'static':
        return
    auth = request.authorization
    user = cfg.get("auth_username","")
    pwd  = cfg.get("auth_password","")
    if not auth or auth.username != user or auth.password != pwd:
        return Response(
            'Authentication required', 401,
            {'WWW-Authenticate': 'Basic realm="DynamiX"'}
        )


@app.route("/")
def index():
    config = load_config()
    used_collections = load_used_collections()
    user_exemptions = load_user_exemptions()
    run_state = load_run_state()
    recently_pinned = run_state.get("recently_pinned", [])

    libraries = config.get("libraries", [])
    default_limits = config.get("default_limits", {})
    seasonal_blocks = config.get("seasonal_blocks", [])

    # Build active time-block & seasonal summaries
    active_blocks = []
    seasonal_summary = []
    for lib in libraries:
        try:
            block_name, limit = get_current_time_block(config, lib)
            active_blocks.append(f"{lib}: {block_name} ({limit})")
            for item in pin_seasonal_blocks_for_library(lib, seasonal_blocks):
                seasonal_summary.append(f"{lib}: {item['title']}")
        except Exception as e:
            logging.warning(f"Error computing blocks for '{lib}': {e}")

    # Compute total collections
    try:
        plex = connect_to_plex(config)
        total_collections_count = sum(
            len(plex.library.section(lib).collections())
            for lib in libraries
        )
    except Exception as e:
        logging.error(f"Error connecting to Plex in index(): {e}")
        total_collections_count = "—"

    # Read current active pre-roll filename
    current_roll_filename = ""
    folder = config.get("pre_roll_folder", "")
    path = os.path.join(folder, CURRENT_ROLL_FILE)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                current_roll_filename = f.read().strip()
        except Exception as e:
            logging.warning(f"Could not read current_roll.txt: {e}")

    # Determine initial badge state:
    #  - if persisted state is "one-off", show that
    #  - else if thread is alive, honor persisted ("running"/"waiting")
    #  - otherwise force "stopped"
    persisted = run_state.get("state", "stopped")
    if persisted == "one-off":
        display_state = "one-off"
    elif automation_thread and automation_thread.is_alive():
        display_state = persisted
    else:
        display_state = "stopped"

    if display_state == "one-off":
        initial_state = "One-Off…"
        initial_badge_class = "badge bg-info"
    elif display_state == "running":
        initial_state = "Running"
        initial_badge_class = "badge bg-success"
    elif display_state == "waiting":
        initial_state = "Waiting"
        initial_badge_class = "badge bg-info"
    else:
        initial_state = "Stopped"
        initial_badge_class = "badge bg-secondary"

    return render_template(
        "index.html",
        initial_state=initial_state,
        initial_badge_class=initial_badge_class,
        last_run=run_state.get("last_run", "—"),
        next_run=run_state.get("next_run", "—"),
        total_collections=total_collections_count,
        pinned_today=run_state.get("pinned_today", 0),
        exclusions_active=len(used_collections),
        exemptions_count=len(user_exemptions),
        active_time_block=", ".join(active_blocks) or "None",
        library_limits=", ".join(f"{lib}: {default_limits.get(lib, '?')}" for lib in libraries),
        seasonal_blocks=", ".join(seasonal_summary) or "None",
        pinned_collections=", ".join(recently_pinned) or "None",
        current_roll_filename=current_roll_filename,
    )

@app.route("/run_state")
def web_run_state():
    """
    Return last_run, next_run and the actual state—
    but never override "one-off" until the cycle completes.
    """
    state = load_run_state()
    rs = state.get("state", "stopped")
    is_running = bool(automation_thread and automation_thread.is_alive())

    # Only force to 'stopped' if we're NOT in a one-off and the thread is dead
    if rs != "one-off" and not is_running and rs != "stopped":
        state["state"] = "stopped"
        save_run_state(state)
        rs = "stopped"

    return jsonify({
        "last_run": state.get("last_run", "—"),
        "next_run": state.get("next_run", "—"),
        "running":  is_running,
        "state":    rs
    })

@app.route("/clear_pins", methods=["POST"])
def clear_pins():
    config = load_config()
    try:
        plex = connect_to_plex(config)
        libraries = config.get("libraries", [])
        pinning_targets = config.get("pinning_targets", {})
        always_pin_new_episodes = config.get("always_pin_new_episodes", False)
        unpin_collections(plex, libraries, always_pin_new_episodes, pinning_targets)
        return jsonify(status="success")
    except Exception as e:
        logging.error(f"Clear pins failed: {e}")
        return jsonify(status="error", message=str(e))

@app.route("/start", methods=["POST"])
def web_start():
    global automation_thread, stop_event
    if not automation_thread or not automation_thread.is_alive():
        # Start the loop
        stop_event.clear()
        automation_thread = threading.Thread(target=main, args=(None, stop_event), daemon=True)
        automation_thread.start()

        # Persist “waiting” since the loop is now running and idle until its next cycle
        state = load_run_state()
        state["state"] = "waiting"
        save_run_state(state)

        return jsonify(status="started")
    return jsonify(status="already running")

@app.route("/stop", methods=["POST"])
def web_stop():
    global automation_thread, stop_event
    if automation_thread and automation_thread.is_alive():
        stop_event.set()
        automation_thread.join(timeout=10)
        # Persist “stopped” immediately
        state = load_run_state()
        state["state"] = "stopped"
        save_run_state(state)
        return jsonify(status="stopped")
    return jsonify(status="not running")

@app.route("/run-once", methods=["POST"])
def web_run_once():
    try:
        # 1) Mark “one-off” in run_state so the badge updates immediately
        state = load_run_state()
        state["state"] = "one-off"
        save_run_state(state)

        # 2) Execute exactly one pinning cycle
        pinned = run_pin_cycle_once()

        # 3) When complete, always mark as stopped (no auto-restarts)
        state = load_run_state()
        state["state"] = "stopped"
        save_run_state(state)

        return jsonify(status="success", pinned=pinned)
    except Exception as e:
        logging.error(f"Run-once failed: {e}")
        return jsonify(status="error", message=str(e)), 500

@app.route("/status")
def web_status():
    running = bool(automation_thread and automation_thread.is_alive())
    return jsonify(running=running)

@app.route("/recently_pinned_data")
def pinned_data():
    run_state = load_run_state()
    return jsonify({
        "recently_pinned": run_state.get("recently_pinned", [])
    })

# ————————————————
# SETTINGS
# ————————————————
@app.route("/settings", methods=["GET", "POST"])
def web_settings():
    from dynamiXMain import load_config, save_config, connect_to_plex
    cfg = load_config()
    if request.method == "POST":
        # General
        cfg['plex_url']  = request.form['plex_url']
        cfg['plex_token']= request.form['plex_token']
        cfg['libraries']= [l.strip() for l in request.form['libraries'].split(',') if l.strip()]
        cfg['pinning_interval']    = int(request.form['pinning_interval'])
        cfg['exclusion_days']      = int(request.form['exclusion_days'])
        cfg['minimum_items']       = int(request.form['minimum_items'])
        cfg['always_pin_new_episodes'] = ('always_pin' in request.form)
        cfg['pre_roll_folder'] = request.form.get('pre_roll_folder', '').strip()
        cfg['auth_enabled'] = ('auth_enabled' in request.form)
        cfg['auth_username'] = request.form.get('auth_username', '').strip()
        cfg['auth_password'] = request.form.get('auth_password', '')

        # Pinning targets
        cfg.setdefault('pinning_targets', {})
        cfg['pinning_targets']['library_recommended'] = ('pt_library' in request.form)
        cfg['pinning_targets']['home']               = ('pt_home' in request.form)
        cfg['pinning_targets']['shared_home']        = ('pt_shared' in request.form)
        # Separate pinning setting
        cfg['separate_pinning'] = ('separate_pinning' in request.form)

        # Default limits per library
        cfg.setdefault('default_limits', {})
        for lib in cfg['libraries']:
            key = f"limit_{lib}"
            if key in request.form:
                cfg['default_limits'][lib] = int(request.form[key])

        save_config(cfg)
        return redirect(url_for('web_settings'))

    import logging
    # --- GET: fetch collection titles per library for the Seasonal Blocks dropdown ---
    available_collections_by_lib = {}
    try:
        plex = connect_to_plex(cfg)
        for lib_name in cfg.get("libraries", []):
            titles = []
            try:
                section = plex.library.section(lib_name)
                for coll in section.collections():
                    titles.append(coll.title)
            except Exception as e:
                logging.error(f"Could not load library '{lib_name}': {e}")
            available_collections_by_lib[lib_name] = sorted(set(titles))
    except Exception as e:
        logging.error(f"Error fetching collections for settings page: {e}")

    # ——— Compute dynamic defaults for this year ———
    from datetime import datetime

    year = datetime.now().year
    computed_defaults = []
    for d in DEFAULT_SEASONAL_BLOCKS:
        if d["type"] == HolidayType.STATIC:
            m1, day1 = map(int, d["start"].split("-"))
            m2, day2 = map(int, d["end"].split("-"))
            sd = date(year, m1, day1)
            ed = date(year, m2, day2)
        elif d["type"] == HolidayType.EASTER:
            eas = compute_easter(year)
            sd = eas + timedelta(days=d.get("offset_start", 0))
            ed = eas + timedelta(days=d.get("offset_end", 0))
        else:  # NTH_WEEKDAY
            sd = find_nth_weekday(year, d["month"], d["weekday"], d["nth"])
            ed = sd + timedelta(days=d["duration_days"] - 1)
        computed_defaults.append({
            "name": d["name"],
            "start_date": sd.strftime("%Y-%m-%d"),
            "end_date": ed.strftime("%Y-%m-%d")
        })

    # after you build computed_defaults…
    weekly_defaults = [
        b for b in computed_defaults
        if b["name"].lower().endswith("week")
    ]
    # ——————— Preroll context for Settings sub-tab ———————
    # 1) Load blocks and files
    blocks = cfg.get("preroll_blocks", [])
    folder = cfg.get("pre_roll_folder", "")
    if folder and os.path.isdir(folder):
        files = sorted(os.listdir(folder))
    else:
        files = []
    # Exclude the marker and any already-applied PlexMainPreRoll
    files = [f for f in files if f != CURRENT_ROLL_FILE and not f.startswith("PlexMainPreRoll")]

    # 2) Read the current active preroll filename
    current_roll_filename = ""
    current_roll_path = os.path.join(folder, CURRENT_ROLL_FILE)
    if os.path.exists(current_roll_path):
        with open(current_roll_path, 'r', encoding='utf-8') as rf:
            current_roll_filename = rf.read().strip()

    # Ensure the active pre-roll appears as an option
    if current_roll_filename and current_roll_filename not in files:
        files.insert(0, current_roll_filename)

    # 3) Build Quick-Add defaults (±3 days around each holiday)
    year = datetime.now().year
    quick_defaults = []
    for d in DEFAULT_SEASONAL_BLOCKS:
        if d["type"] == HolidayType.STATIC:
            m1, day1 = map(int, d["start"].split("-"))
            m2, day2 = map(int, d["end"].split("-"))
            sd = date(year, m1, day1)
            ed = date(year, m2, day2)
        elif d["type"] == HolidayType.EASTER:
            eas = compute_easter(year)
            sd = eas + timedelta(days=d.get("offset_start", 0))
            ed = eas + timedelta(days=d.get("offset_end", 0))
        else:  # NTH_WEEKDAY
            sd = find_nth_weekday(year, d["month"], d["weekday"], d["nth"])
            ed = sd + timedelta(days=d["duration_days"] - 1)
        # expand single-day blocks ±3 days
        if sd == ed:
            sd -= timedelta(days=3)
            ed += timedelta(days=3)
        quick_defaults.append({
            "name":    d["name"],
            "start_md": sd.strftime("%m-%d"),
            "end_md":   ed.strftime("%m-%d")
        })
    # ————————————————————————————————————————————

    return render_template(
        "settings.html",
        config=cfg,
        available_collections_by_lib=available_collections_by_lib,
        default_blocks=computed_defaults,
        weekly_defaults=weekly_defaults,
        # —— new preroll context ——
        blocks=blocks,
        files=files,
        current_roll_filename=current_roll_filename,
        default_preroll_filename=cfg.get("default_preroll_filename", ""),
        quick_defaults=quick_defaults,
    )


@app.route("/kometa-collections", methods=["GET", "POST"])
def web_kometa_collections():
    import yaml
    config = load_config()
    plex = connect_to_plex(config)

    # 1) Discover each library’s section type
    libraries       = config.get("libraries", [])
    library_types   = {}
    for lib in libraries:
        try:
            section = plex.library.section(lib)
            library_types[lib] = section.type   # "movie" or "show"
        except Exception:
            library_types[lib] = None

    # 2) Build per-library defaults list
    defaults_by_library = {
        lib: [
            key for key, types in KOMETA_DEFAULT_TYPES.items()
            if library_types[lib] in types
        ]
        for lib in libraries
    }

    message = None
    if request.method == "POST":
        # 3) Read selections and folder
        selections   = request.form.getlist("defaults")  # e.g. "Movies|oscars"
        output_folder = request.form["output_folder"].strip()

        # 4) Build the per-library config structure
        libraries_config = {}
        for sel in selections:
            lib, key = sel.split("|", 1)
            # Prepare each entry
            entry = {"default": key}
            # Gather template_vars
            vars_dict = {}
            for var in KOMETA_DEFAULT_VARS.get(key, []):
                form_name = f"{lib}__{key}__{var}"
                val = request.form.get(form_name, "").strip()
                if val:
                    vars_dict[var] = val
            if vars_dict:
                entry["template_variables"] = vars_dict

            libraries_config.setdefault(lib, []).append(entry)

        # 5) Compose full YAML
        config_data = {"libraries": {}}
        for lib, entries in libraries_config.items():
            config_data["libraries"][lib] = {"collection_files": entries}

        # 6) Write file
        try:
            os.makedirs(output_folder, exist_ok=True)
            path = os.path.join(output_folder, "config.yml")
            with open(path, "w", encoding="utf-8") as f:
                yaml.safe_dump(config_data, f, sort_keys=False)
            message = f"Written <code>config.yml</code> to <strong>{path}</strong>."
        except Exception as e:
            message = f"Error: {e}"

    return render_template(
        "kometa_collections.html",
        libraries=libraries,
        defaults_by_library=defaults_by_library,
        default_vars=KOMETA_DEFAULT_VARS,
        message=message
    )

import re
@app.route("/settings/seasonal-blocks/suggest-collections")
def suggest_seasonal_collections():
    holiday = request.args.get('holiday', '').strip()
    cfg     = load_config()
    plex    = connect_to_plex(cfg)

    # pick the list of keywords for this holiday, or fallback to the raw name
    keywords = HOLIDAY_KEYWORDS.get(holiday, [holiday.lower()])

    suggestions = {}
    for lib in cfg.get('libraries', []):
        libsugg = []
        try:
            section = plex.library.section(lib)
            for coll in section.collections():
                title_lower = coll.title.lower()
                # if ANY of the keywords appears in the title, include it
                if any(kw in title_lower for kw in keywords):
                    libsugg.append(coll.title)
        except Exception as e:
            logging.error(f"Error fetching collections in '{lib}': {e}")
        suggestions[lib] = libsugg

    return jsonify(suggestions)

@app.route("/settings/seasonal-blocks/add-defaults",
           methods=["POST"],
           endpoint="add_default_seasonal_blocks_defaults")
def add_default_seasonal_blocks_handler():
    cfg = load_config()
    name  = request.form['default_name']
    start = request.form['sb_start_date']  # "YYYY-MM-DD"
    end   = request.form['sb_end_date']

    for lib in cfg.get("libraries", []):
        if f"include_{lib}" not in request.form:
            continue
        raw = request.form.get(f"collections_{lib}", "")
        for coll in [c.strip() for c in raw.split(",") if c.strip()]:
            cfg.setdefault("seasonal_blocks", []).append({
                "name":       name,
                "start_date": start,
                "end_date":   end,
                "libraries":  [lib],
                "collection": coll
            })

    save_config(cfg)
    return redirect(url_for("web_settings"))


# ————————————————
# EXCLUSIONS
# ————————————————
@app.route("/exclusions", methods=["GET"])
def web_exclusions():
    from dynamiXMain import load_used_collections
    exclusions = load_used_collections()
    return render_template("exclusions.html", exclusions=exclusions)

@app.route("/exclusions/delete", methods=["POST"])
def delete_exclusion():
    from dynamiXMain import load_used_collections, save_used_collections
    title = request.form['title']
    used = load_used_collections()
    used.pop(title, None)
    save_used_collections(used)
    return redirect(url_for('web_exclusions'))

@app.route("/exclusions/reset", methods=["POST"])
def reset_exclusions():
    from dynamiXMain import reset_exclusion_list_file
    reset_exclusion_list_file()
    return redirect(url_for('web_exclusions'))


# ————————————————
# EXEMPTIONS
# ————————————————
@app.route("/exemptions", methods=["GET"])
def web_exemptions():
    from dynamiXMain import load_user_exemptions
    exemptions = load_user_exemptions()
    return render_template("exemptions.html", exemptions=exemptions)

@app.route("/exemptions/add", methods=["POST"])
def add_exemption():
    from dynamiXMain import load_user_exemptions, save_user_exemptions
    title = request.form['exemption'].strip()
    ex = load_user_exemptions()
    if title and title not in ex:
        ex.append(title)
        save_user_exemptions(ex)
    return redirect(url_for('web_exemptions'))

@app.route("/exemptions/delete", methods=["POST"])
def delete_exemption_user():
    from dynamiXMain import load_user_exemptions, save_user_exemptions
    title = request.form['title']
    ex = load_user_exemptions()
    if title in ex:
        ex.remove(title)
        save_user_exemptions(ex)
    return redirect(url_for('web_exemptions'))


@app.route("/logs")
def web_logs():
    level = request.args.get("level", "base")
    lines = []
    try:
        with open(LOG_FILE) as f:
            all_lines = f.readlines()[-500:]
    except:
        all_lines = []
    for line in all_lines:
        if level == "base" and ("DEBUG" in line or "HTTP/" in line):
            continue
        lines.append(line.rstrip())
    return render_template("logs.html", logs=lines, level=level)

@app.route("/logs_data")
def logs_data():
    level = request.args.get("level", "base")
    try:
        with open(LOG_FILE) as f:
            all_lines = f.readlines()
    except:
        all_lines = []
    filtered = []
    for ln in all_lines:
        if level == "base" and ("DEBUG" in ln or "HTTP/" in ln):
            continue
        filtered.append(ln.rstrip())
    return jsonify(logs=filtered)

# ————————————————
# PRE-ROLL MANAGER
# ————————————————

@app.route("/preroll/default", methods=["POST"])
def set_default_preroll():
    cfg = load_config()
    chosen = request.form.get("default_preroll_filename", "").strip()
    cfg["default_preroll_filename"] = chosen
    save_config(cfg)
    next_url = request.form.get("next")
    return redirect(next_url or url_for("web_preroll"))


@app.route("/preroll/add", methods=["POST"])
def add_preroll_block():
    cfg = load_config()
    block = {
        "name":       request.form["name"],
        "start_date": request.form["start_date"],
        "end_date":   request.form["end_date"],
        "filename":   request.form["filename"]
    }
    cfg.setdefault("preroll_blocks", []).append(block)
    save_config(cfg)
    next_url = request.form.get("next")
    return redirect(next_url or url_for("web_preroll"))


@app.route("/preroll/delete", methods=["POST"])
def delete_preroll_block():
    cfg = load_config()
    name = request.form["name"]
    cfg["preroll_blocks"] = [b for b in cfg.get("preroll_blocks", []) if b["name"] != name]
    save_config(cfg)
    next_url = request.form.get("next")
    return redirect(next_url or url_for("web_preroll"))


@app.route("/preroll", methods=["GET"])
def web_preroll():
    config = load_config()
    blocks = config.get("preroll_blocks", [])

    # Gather files in pre-roll folder
    folder = config.get("pre_roll_folder", "")
    if folder and os.path.isdir(folder):
        files = sorted(os.listdir(folder))
    else:
        files = []

    # Exclude internal marker and PlexMainPreRoll
    files = [f for f in files if f != CURRENT_ROLL_FILE and not f.startswith("PlexMainPreRoll")]

    # Read current active preroll filename
    current_roll = ""
    current_roll_path = os.path.join(folder, CURRENT_ROLL_FILE)
    if os.path.exists(current_roll_path):
        try:
            with open(current_roll_path, 'r', encoding='utf-8') as rf:
                current_roll = rf.read().strip()
        except Exception:
            current_roll = ""

    # Ensure current_roll and saved default appear in dropdown
    default = config.get("default_preroll_filename", "")
    for name in (current_roll, default):
        if name and name not in files:
            files.insert(0, name)

    # Compute quick-add defaults (month-day only, ±3 days wrap)
    year = datetime.now().year
    quick = []
    for d in DEFAULT_SEASONAL_BLOCKS:
        if d["type"] == HolidayType.STATIC:
            m1, day1 = map(int, d["start"].split("-"))
            m2, day2 = map(int, d["end"].split("-"))
            sd = date(year, m1, day1)
            ed = date(year, m2, day2)
        elif d["type"] == HolidayType.EASTER:
            eas = compute_easter(year)
            sd = eas + timedelta(days=d.get("offset_start",0))
            ed = eas + timedelta(days=d.get("offset_end",0))
        else:
            sd = find_nth_weekday(year, d["month"], d["weekday"], d["nth"])
            ed = sd + timedelta(days=d["duration_days"]-1)
        if sd == ed:
            sd -= timedelta(days=3)
            ed += timedelta(days=3)
        quick.append({
            "name":    d["name"],
            "start_md": sd.strftime("%m-%d"),
            "end_md":   ed.strftime("%m-%d")
        })

    return render_template(
        "preroll.html",
        blocks=blocks,
        files=files,
        default_preroll_filename=default,
        current_roll_filename=current_roll,
        quick_defaults=quick,
        message=request.args.get("message"),
        message_type=request.args.get("message_type", "info")
    )

@app.route("/preroll/run", methods=["POST"])
def run_preroll_once():
    cfg = load_config()
    try:
        manage_prerolls(cfg)
    except Exception as e:
        logging.error(f"Error running pre-roll once: {e}")
    # Redirect back to wherever the form told us to go (dashboard), defaulting to /preroll
    next_url = request.form.get('next')
    return redirect(next_url or url_for("web_preroll"))

# ————————————————
# TIME BLOCKS
# ————————————————
@app.route("/settings/time-blocks/add", methods=["POST"])
def add_time_block():
    cfg = load_config()
    block = {
        "name":        request.form["tb_name"],
        "start_time":  request.form["tb_start_time"],
        "end_time":    request.form["tb_end_time"],
        "limit":       int(request.form["tb_limit"]),
        "days":        request.form.getlist("tb_days"),
        "libraries":   request.form.getlist("tb_libs")
    }
    cfg.setdefault("time_blocks", []).append(block)
    save_config(cfg)
    return redirect(url_for("web_settings"))

@app.route("/settings/time-blocks/delete", methods=["POST"])
def delete_time_block():
    name = request.form["name"]
    cfg = load_config()
    cfg["time_blocks"] = [b for b in cfg.get("time_blocks", []) if b["name"] != name]
    save_config(cfg)
    return redirect(url_for("web_settings"))


# ————————————————
# SEASONAL BLOCKS
# ————————————————
@app.route("/settings/seasonal-blocks/add-defaults", methods=["POST"])
def add_default_seasonal_blocks():
    cfg = load_config()
    # Single holiday name from dropdown
    name       = request.form['default_name']
    start_date = request.form['sb_start_date']
    end_date   = request.form['sb_end_date']

    # For each library, if its include-box was checked, split its collections
    for lib in cfg.get("libraries", []):
        if f"include_{lib}" not in request.form:
            continue
        raw = request.form.get(f"collections_{lib}", "")
        for coll in [c.strip() for c in raw.split(",") if c.strip()]:
            block = {
                "name":       name,
                "start_date": start_date,
                "end_date":   end_date,
                "libraries":  [lib],
                "collection": coll
            }
            cfg.setdefault("seasonal_blocks", []).append(block)

    save_config(cfg)
    return redirect(url_for("web_settings"))


@app.route("/settings/seasonal-blocks/add", methods=["POST"])
def add_seasonal_block():
    cfg = load_config()
    block = {
        "name":       request.form["sb_name"],
        "start_date": request.form["sb_start_date"],
        "end_date":   request.form["sb_end_date"],
        "libraries":  request.form.getlist("sb_libs"),
        "collection": request.form["sb_collection"]
    }
    cfg.setdefault("seasonal_blocks", []).append(block)
    save_config(cfg)
    return redirect(url_for("web_settings"))

@app.route("/settings/seasonal-blocks/delete", methods=["POST"])
def delete_seasonal_block():
    name = request.form["name"]
    cfg = load_config()
    cfg["seasonal_blocks"] = [
        b for b in cfg.get("seasonal_blocks", [])
        if b["name"] != name or b.get("library_specific_id") != request.form.get("id")
    ]
    save_config(cfg)
    return redirect(url_for("web_settings"))


# ————————————————
# PINNED COLLECTIONS
# ————————————————
@app.route("/settings/pinned-collections/add", methods=["POST"])
def add_pinned_collection():
    cfg = load_config()
    pc = {
        "title":     request.form["pc_title"],
        "libraries": request.form.getlist("pc_libs")
    }
    cfg.setdefault("pinned_collections", []).append(pc)
    save_config(cfg)
    return redirect(url_for("web_settings"))

@app.route("/settings/pinned-collections/delete", methods=["POST"])
def delete_pinned_collection():
    title = request.form["title"]
    cfg = load_config()
    cfg["pinned_collections"] = [p for p in cfg.get("pinned_collections", []) if p["title"] != title]
    save_config(cfg)
    return redirect(url_for("web_settings"))




# ------------------------------ Application Entry Point ------------------------------

if __name__ == "__main__":
    # Launch the web UI on port 1166
    app.run(host="0.0.0.0", port=1166, threaded=True)
