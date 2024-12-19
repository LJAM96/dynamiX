import os
import sys
import time
import threading
import logging
import random
import json
import queue
import traceback
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont

from ttkbootstrap import Style
from plexapi.server import PlexServer
import requests

# ------------------------------ Constants and Configuration ------------------------------

# Define file paths for logs and configuration
LOG_DIR = 'logs'
LOG_FILE = os.path.join(LOG_DIR, 'DynamiX.log')
CONFIG_FILE = 'config.json'
USED_COLLECTIONS_FILE = 'used_collections.json'
USER_EXEMPTIONS_FILE = 'user_exemptions.json'

# Ensure the logs directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Configure logging to file and stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# ------------------------------ Helper Functions ------------------------------

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
    Ensure time_blocks is properly formatted as a dictionary.
    """
    if not isinstance(time_blocks, dict):
        logging.warning(f"Sanitizing time_blocks: expected dict but got {type(time_blocks)}. Resetting to empty.")
        return {}
    sanitized = {}
    for day, blocks in time_blocks.items():
        if not isinstance(blocks, dict):
            logging.warning(f"Invalid blocks for day '{day}': resetting to empty dictionary.")
            sanitized[day] = {}
        else:
            sanitized[day] = blocks
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

    # Sanitize libraries_settings and time_blocks
    libraries_settings = config.get("libraries_settings", {})
    if not isinstance(libraries_settings, dict):
        logging.warning(f"Sanitizing libraries_settings: resetting to empty dictionary.")
        libraries_settings = {}
    for library, settings in libraries_settings.items():
        time_blocks = settings.get("time_blocks", {})
        settings["time_blocks"] = sanitize_time_blocks(time_blocks)
    config["libraries_settings"] = libraries_settings

    # Ensure seasonal_blocks is a list
    if "seasonal_blocks" not in config or not isinstance(config["seasonal_blocks"], list):
        config["seasonal_blocks"] = []

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
                if always_pin_new_episodes and collection.title.lower() == "new episodes":
                    continue  # Skip unpinning 'New Episodes' if always_pin_new_episodes is enabled
                apply_pinning(collection, pinning_targets, action="demote")
                logging.info(f"Collection '{collection.title}' unpinned in '{library_name}'.")
        except Exception as e:
            logging.error(f"Error accessing library '{library_name}': {e}")

def log_and_update_exclusion_list(previous_pinned, used_collections, exclusion_days):
    """
    Log pinned collections and update the exclusion list with their expiration dates.
    """
    current_date = datetime.now().date()
    for collection in previous_pinned:
        expiration_date = (current_date + timedelta(days=exclusion_days)).strftime('%Y-%m-%d')
        used_collections[collection.title] = expiration_date
        logging.info(f"Added '{collection.title}' to exclusion list (expires: {expiration_date}).")
    save_used_collections(used_collections)

def get_current_time_block(config, library_name):
    """
    Determine the current time block and its corresponding limit for a given library.
    """
    now = datetime.now()
    current_day = now.strftime("%A")  # e.g., "Monday"
    current_time = now.strftime("%H:%M")

    library_settings = config.get("libraries_settings", {}).get(library_name, {})
    time_blocks = library_settings.get("time_blocks", {})
    default_limits = config.get("default_limits", {})
    library_default_limit = default_limits.get(library_name, 5)

    day_blocks = time_blocks.get(current_day, {})
    if not isinstance(day_blocks, dict):
        logging.error(f"Invalid time_blocks for day '{current_day}' in library '{library_name}'")
        return "Default", library_default_limit

    for block, details in day_blocks.items():
        if details.get("start_time") <= current_time < details.get("end_time"):
            return block, details.get("limit", library_default_limit)

    return "Default", library_default_limit

def pin_seasonal_blocks(plex, seasonal_blocks):
    """
    Pin specific collections based on active seasonal blocks.
    Month and day are compared without considering the year.
    """
    current_date = datetime.now().date()
    current_month_day = (current_date.month, current_date.day)
    pinned_collections = []

    for block in seasonal_blocks:
        # Parse start and end dates (MM-DD)
        try:
            start_month, start_day = map(int, block["start_date"].split("-"))
            end_month, end_day = map(int, block["end_date"].split("-"))
        except Exception as e:
            logging.error(f"Invalid seasonal block dates for block '{block.get('name', 'Unnamed')}': {e}")
            continue

        start_month_day = (start_month, start_day)
        end_month_day = (end_month, end_day)

        # Handle date ranges that may wrap around the year (e.g., Dec 15 - Jan 10)
        if start_month_day <= end_month_day:
            is_active = (start_month_day <= current_month_day <= end_month_day)
        else:
            # Spans year-end
            is_active = (current_month_day >= start_month_day or current_month_day <= end_month_day)

        if is_active:
            collection_name = block.get("collection")
            libraries = block.get("libraries", [])
            logging.info(f"Activating seasonal block '{block['name']}' for collection '{collection_name}'.")

            for library_name in libraries:
                try:
                    library = plex.library.section(library_name)
                    collection = next((c for c in library.collections() if c.title == collection_name), None)

                    if collection:
                        hub = collection.visibility()
                        hub.promoteHome()
                        hub.promoteShared()
                        logging.info(f"Pinned collection '{collection_name}' in library '{library_name}' due to seasonal block '{block['name']}'.")
                        pinned_collections.append(collection)
                    else:
                        logging.warning(f"Collection '{collection_name}' not found in library '{library_name}'.")
                except Exception as e:
                    logging.error(f"Error processing library '{library_name}': {e}")

    return pinned_collections

# ------------------------------ Main Automation Function ------------------------------

def main(gui_instance=None, stop_event=None):
    logging.info("Starting DynamiX automation...")

    try:
        # Load configuration
        config = load_config()
        if not config:
            logging.error("Configuration could not be loaded. Exiting.")
            return

        logging.info("Configuration loaded successfully.")

        # Connect to Plex server
        plex = connect_to_plex(config)

        # Retrieve configuration settings
        libraries = config.get("libraries", [])
        min_items = config.get("minimum_items", 1)
        exclusion_days = config.get("exclusion_days", 3)
        always_pin_new_episodes = config.get("always_pin_new_episodes", False)
        pinning_interval = config.get("pinning_interval", 30) * 60  # Convert minutes to seconds

        # Seasonal blocks
        seasonal_blocks = config.get("seasonal_blocks", [])

        # Load persistent state
        used_collections = load_used_collections()
        user_exemptions = load_user_exemptions()

        sys_random = random.SystemRandom()

        logging.info("Entering main automation loop.")
        while not stop_event.is_set():
            current_date = datetime.now().date()

            # 1: Clean up expired exclusions
            logging.info("Cleaning up expired exclusions...")
            used_collections = {
                name: date for name, date in used_collections.items()
                if datetime.strptime(date, '%Y-%m-%d').date() > current_date
            }
            save_used_collections(used_collections)
            logging.info("Updated exclusion list.")

            # Retrieve pinning targets from config
            pinning_targets = config.get("pinning_targets", {})

            # Handle 'New Episodes' pinning based on preferences
            handle_new_episodes_pinning(plex, libraries, always_pin_new_episodes, pinning_targets)

            # Unpin collections based on preferences
            unpin_collections(plex, libraries, always_pin_new_episodes, pinning_targets)

            # 4: Pin seasonal blocks (if active)
            pinned_seasonal = pin_seasonal_blocks(plex, seasonal_blocks)
            # Seasonal blocks now do NOT skip normal logic; they are pinned like 'New Episodes'.

            # 5: Proceed with normal time-block based pinning
            logging.info("Proceeding with time block-based pinning after seasonal blocks...")
            previous_pinned = []
            reset_needed = False

            for library_name in libraries:
                try:
                    logging.info(f"Processing library: {library_name}")
                    library = plex.library.section(library_name)
                    collections = library.collections()

                    # Determine the current time block and limit
                    current_block, current_limit = get_current_time_block(config, library_name)
                    logging.info(f"Library '{library_name}' - Time Block: {current_block}, Limit: {current_limit}")

                    # Filter valid collections for pinning
                    valid_collections = [
                        collection for collection in collections
                        if len(collection.items()) >= min_items
                           and collection.title not in used_collections
                           and collection.title not in user_exemptions
                    ]

                    if len(valid_collections) < current_limit:
                        logging.warning(
                            f"Not enough valid collections for '{library_name}'. "
                            f"Required: {current_limit}, Available: {len(valid_collections)}."
                        )
                        continue

                    # Select collections to pin based on the limit
                    collections_to_pin = random.sample(valid_collections, current_limit)

                    for collection in collections_to_pin:
                        apply_pinning(collection, pinning_targets, action="promote")
                        logging.info(f"Collection '{collection.title}' pinned in '{library_name}'.")
                        previous_pinned.append(collection)

                except Exception as e:
                    logging.error(f"Error processing library '{library_name}': {e}")

            if reset_needed:
                if gui_instance:
                    logging.info("Resetting exclusion list due to insufficient collections.")
                    gui_instance.reset_exclusion_list()
                    used_collections = load_used_collections()  # Reload after reset
                else:
                    reset_exclusion_list_file()
                    used_collections = {}

                continue  # Restart loop

            # 6: Log exclusions for normally pinned collections (seasonal blocks are treated like New Episodes and not excluded)
            if previous_pinned:
                log_and_update_exclusion_list(previous_pinned, used_collections, exclusion_days)
            else:
                logging.info("No new normal collections were pinned in this iteration.")

            # GUI update scheduling (if applicable)
            if gui_instance:
                gui_instance.after(0, gui_instance.refresh_exclusion_list)

            # Sleep for the configured pinning interval
            logging.info(f"Sleeping for {pinning_interval // 60} minutes before next iteration.")
            time.sleep(pinning_interval)

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        traceback.print_exc()
    finally:
        logging.info("Automation script terminated.")

# ------------------------------ Custom Logging Handler ------------------------------

class GuiHandler(logging.Handler):
    """
    Custom logging handler for displaying logs in the GUI using a queue.
    """

    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        msg = self.format(record)
        self.log_queue.put(msg)

# ------------------------------ Scrollable Frame Class ------------------------------

class ScrollableFrame(ttk.Frame):
    """
    A scrollable frame that adjusts its content dynamically with mousewheel support.
    """
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Mousewheel binding
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def display_widget(self):
        """
        Returns the frame for adding child widgets.
        """
        return self.scrollable_frame

    def _bind_mousewheel(self, event):
        """
        Binds the mousewheel to the canvas for scrolling.
        """
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        """
        Unbinds the mousewheel to prevent interaction when not in focus.
        """
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        """
        Handles mousewheel scrolling.
        """
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

# ------------------------------ Seasonal Block Dialog ------------------------------

class SeasonalBlockDialog(tk.Toplevel):
    """
    A dialog for adding/editing seasonal blocks with MM-DD date format.
    """

    def __init__(self, parent, title="Add Seasonal Block", block=None, callback=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x300")
        self.resizable(False, False)
        self.block = block
        self.callback = callback
        self.parent = parent

        # Widgets
        ttk.Label(self, text="Block Name:").grid(row=0, column=0, padx=10, pady=5, sticky="e")
        self.name_entry = ttk.Entry(self, width=30)
        self.name_entry.grid(row=0, column=1, padx=10, pady=5)

        ttk.Label(self, text="Start Date (MM-DD):").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.start_date_entry = ttk.Entry(self, width=30)
        self.start_date_entry.grid(row=1, column=1, padx=10, pady=5)

        ttk.Label(self, text="End Date (MM-DD):").grid(row=2, column=0, padx=10, pady=5, sticky="e")
        self.end_date_entry = ttk.Entry(self, width=30)
        self.end_date_entry.grid(row=2, column=1, padx=10, pady=5)

        ttk.Label(self, text="Libraries (comma-separated):").grid(row=3, column=0, padx=10, pady=5, sticky="e")
        self.libraries_entry = ttk.Entry(self, width=30)
        self.libraries_entry.grid(row=3, column=1, padx=10, pady=5)

        ttk.Label(self, text="Collection Name:").grid(row=4, column=0, padx=10, pady=5, sticky="e")
        self.collection_entry = ttk.Entry(self, width=30)
        self.collection_entry.grid(row=4, column=1, padx=10, pady=5)

        # Buttons
        button_frame = ttk.Frame(self)
        button_frame.grid(row=5, column=0, columnspan=2, pady=10)

        ttk.Button(button_frame, text="Save", command=self.save_block).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side="left", padx=5)

        # Pre-fill if editing
        if self.block:
            self.name_entry.insert(0, self.block.get("name", ""))
            self.start_date_entry.insert(0, self.block.get("start_date", ""))
            self.end_date_entry.insert(0, self.block.get("end_date", ""))
            self.libraries_entry.insert(0, ", ".join(self.block.get("libraries", [])))
            self.collection_entry.insert(0, self.block.get("collection", ""))

    def save_block(self):
        name = self.name_entry.get().strip()
        start_date = self.start_date_entry.get().strip()
        end_date = self.end_date_entry.get().strip()
        libs_str = self.libraries_entry.get().strip()
        collection = self.collection_entry.get().strip()

        if not (name and start_date and end_date and collection):
            messagebox.showerror("Error", "Name, Start Date, End Date, and Collection fields are required.")
            return

        # Validate date format MM-DD
        if not self._validate_mm_dd(start_date) or not self._validate_mm_dd(end_date):
            messagebox.showerror("Error", "Invalid date format. Use MM-DD.")
            return

        libraries = [l.strip() for l in libs_str.split(",") if l.strip()]

        new_block = {
            "name": name,
            "start_date": start_date,  # MM-DD format
            "end_date": end_date,      # MM-DD format
            "libraries": libraries,
            "collection": collection
        }

        if self.callback:
            self.callback(new_block)
        self.destroy()

    def _validate_mm_dd(self, date_str):
        try:
            datetime.strptime(date_str, "%m-%d")
            return True
        except ValueError:
            return False

# ------------------------------ GUI Application Class ------------------------------

class DynamiXGUI(tk.Tk):
    """
    The main GUI application for DynamiX - Plex Recommendations Manager.
    """

    def __init__(self):
        super().__init__()
        self.title("DynamiX - Plex Recommendations Manager")
        self.geometry("920x875")
        self.resizable(False, False)

        icon_path = os.path.join("resources", "myicon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)

        self.center_window(920, 875)
        self.style = Style(theme="darkly")
        self.configure(bg="black")

        self.script_thread = None
        self.stop_event = threading.Event()  # Event to signal stopping the script
        self.config = load_config() or {}
        self.user_exemptions = load_user_exemptions() or []
        self.user_exemption_checkboxes = {}
        self.select_all_vars = {}  # Added for "Select All" functionality
        self.plex = None
        self.log_queue = queue.Queue()  # Queue for log messages

        self.default_font = tkfont.Font(family="Segoe UI", size=30)

        self.create_widgets()
        self.refresh_user_exemptions()
        self.refresh_exclusion_list()

    def center_window(self, width, height):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x_position = (screen_width // 2) - (width // 2)
        y_position = (screen_height // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x_position}+{y_position}")

    def create_widgets(self):
        self.tab_control = ttk.Notebook(self)

        self.server_tab = ttk.Frame(self.tab_control)
        self.settings_tab = ttk.Frame(self.tab_control)
        self.logs_tab = ttk.Frame(self.tab_control)
        self.exclusion_tab = ttk.Frame(self.tab_control)
        self.user_exemptions_tab = ttk.Frame(self.tab_control)

        if self._has_missing_fields():
            self.missing_info_tab = ttk.Frame(self.tab_control)
            self.tab_control.add(self.missing_info_tab, text="Missing Configuration Information")
            self._create_missing_info_tab()

        self.tab_control.add(self.logs_tab, text="Logs")
        self.tab_control.add(self.exclusion_tab, text="Dynamic Exclusions")
        self.tab_control.add(self.user_exemptions_tab, text="User-Set Exemptions")
        self.tab_control.add(self.server_tab, text="Plex Server Config")
        self.tab_control.add(self.settings_tab, text="Settings")

        self.tab_control.pack(expand=True, fill="both")

        self._create_server_tab()
        self._create_settings_tab()
        self._create_logs_tab()
        self._create_exclusion_tab()
        self._create_user_exemptions_tab()

    def _has_missing_fields(self):
        required_fields = ["plex_url", "plex_token", "libraries", "pinning_interval"]
        for field in required_fields:
            if field not in self.config or not self.config[field]:
                return True
        return False

    def _create_missing_info_tab(self):
        frame = ttk.Frame(self.missing_info_tab, padding=10)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Fill in Missing Configuration Fields", font=("Segoe UI", 16, "bold")).pack(pady=10)
        self.missing_fields_frame = ttk.Frame(frame)
        self.missing_fields_frame.pack(fill="both", expand=True, pady=10)

        self.missing_entries = {}
        self._populate_missing_fields()

        if "plex_token" in self.missing_entries:
            plex_token_explanation = (
                "\nHow to Find Your Plex Token (Easier Method):\n\n"
                "1. Open the Plex Web App in your browser and log into your Plex server.\n"
                "2. Select any movie or episode.\n"
                "3. Click the 'Get Info' button (3 dot icon) for that item.\n"
                "4. Select 'View XML'.\n"
                "5. Your Plex token appears at the end of the URL after 'X-Plex-Token='.\n"
            )
            explanation_frame = ttk.Frame(frame)
            explanation_frame.pack(expand=True, fill="both", pady=(0, 10))
            ttk.Label(
                explanation_frame, text=plex_token_explanation,
                font=("Segoe UI", 9, "italic"), foreground="yellow",
                wraplength=800, justify="center", anchor="center"
            ).pack(expand=True, fill="both", anchor='center')

        save_button = ttk.Button(frame, text="Save Missing Information", command=self._save_missing_fields)
        save_button.pack(pady=10)

    def _populate_missing_fields(self):
        for widget in self.missing_fields_frame.winfo_children():
            widget.destroy()
        self.missing_entries = {}

        required_fields = {
            "plex_url": "URL of your Plex server (Can't be 'localhost')",
            "plex_token": "Token for accessing your Plex server",
            "libraries": "Comma-separated list of libraries to manage",
            "pinning_interval": "Time interval (in minutes) for pinning"
        }

        self.missing_fields_frame.grid_columnconfigure(0, weight=1)
        self.missing_fields_frame.grid_columnconfigure(1, weight=2)
        self.missing_fields_frame.grid_columnconfigure(2, weight=1)

        row = 0
        for key, description in required_fields.items():
            if key not in self.config or not self.config[key]:
                ttk.Label(
                    self.missing_fields_frame,
                    text=f"{key.replace('_', ' ').title()}:",
                    font=("Segoe UI", 12)
                ).grid(row=row, column=1, sticky="w", pady=5, padx=50)

                entry = ttk.Entry(self.missing_fields_frame, width=40)
                entry.grid(row=row, column=1, pady=5, padx=50)
                entry.configure(justify="center")

                ttk.Label(
                    self.missing_fields_frame,
                    text=f"({description})",
                    font=("Segoe UI", 10, "italic"),
                    foreground="gray"
                ).grid(row=row + 1, column=1, sticky="w", pady=2, padx=50)

                self.missing_entries[key] = entry
                row += 2

        if not self.missing_entries:
            ttk.Label(
                self.missing_fields_frame,
                text="No missing configuration fields detected!",
                font=("Segoe UI", 12, "italic")
            ).grid(row=row, column=1, pady=20)

    def _save_missing_fields(self):
        try:
            for key, widget in self.missing_entries.items():
                value = widget.get().strip()
                if key == "libraries":
                    self.config[key] = [lib.strip() for lib in value.split(",") if lib.strip()]
                elif key == "pinning_interval":
                    self.config[key] = int(value) if value.isdigit() else 30
                else:
                    self.config[key] = value

            save_config(self.config)
            messagebox.showinfo("Success", "Missing information saved successfully! Restarting the application...")
            logging.info("Missing configuration fields updated. Restarting...")
            self.restart_program()
        except Exception as e:
            logging.error(f"Error saving missing configuration fields: {e}")
            messagebox.showerror("Error", f"Failed to save missing information: {e}")

    def _create_server_tab(self):
        frame = ttk.Frame(self.server_tab, padding="10", style="TFrame")
        frame.pack(fill="both", expand=True)

        for i in range(7):
            frame.grid_rowconfigure(i, weight=0)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_rowconfigure(6, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        ttk.Label(
            frame,
            text="Plex Server Configuration",
            font=("Segoe UI", 30, "bold"),
            bootstyle="warning"
        ).grid(row=1, column=0, columnspan=2, pady=10)

        ttk.Label(frame, text="Plex URL (Can't be 'localhost'):", font=("Segoe UI", 12)).grid(row=2, column=0, sticky="e", padx=10, pady=5)
        self.plex_url_entry = ttk.Entry(frame, width=50)
        self.plex_url_entry.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        self.plex_url_entry.insert(0, self.config.get("plex_url", ""))

        ttk.Label(frame, text="Plex Token:", font=("Segoe UI", 12)).grid(row=3, column=0, sticky="e", padx=10, pady=5)
        self.plex_token_entry = ttk.Entry(frame, width=50, show="*")
        self.plex_token_entry.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        self.plex_token_entry.insert(0, self.config.get("plex_token", ""))

        plex_token_explanation = (
            "\nHow to Find Your Plex Token:\n\n"
            "1. In the Plex Web App, navigate to a movie or TV episode.\n"
            "2. Click 'Get Info', then 'View XML'.\n"
            "3. Your token is at the end of the URL after 'X-Plex-Token='."
        )
        explanation_label = ttk.Label(
            frame,
            text=plex_token_explanation,
            font=("Segoe UI", 9, "italic"),
            foreground="yellow",
            wraplength=600,
            justify="center",
            anchor="center"
        )
        explanation_label.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 20))

        ttk.Button(
            frame,
            text="Save Configuration",
            command=self._save_and_refresh_server_name,
            bootstyle="warning"
        ).grid(row=5, column=0, columnspan=2, pady=20)

        self.server_name_label = ttk.Label(
            frame,
            text="Server Name: Fetching...",
            font=("Segoe UI", 20, "bold"),
            bootstyle="warning"
        )
        self.server_name_label.grid(row=6, column=0, columnspan=2, pady=10)

        self._fetch_and_display_server_name()

    def _save_and_refresh_server_name(self):
        self.save_server_config()
        self._fetch_and_display_server_name()

    def save_server_config(self):
        try:
            plex_url = self.plex_url_entry.get().strip()
            plex_token = self.plex_token_entry.get().strip()
            if not plex_url or not plex_token:
                messagebox.showerror("Error", "Plex URL and Token cannot be empty.")
                return

            self.config["plex_url"] = plex_url
            self.config["plex_token"] = plex_token
            save_config(self.config)
            messagebox.showinfo("Success", "Plex server configuration saved successfully.")
            logging.info("Plex server configuration saved.")
        except Exception as e:
            logging.error(f"Error saving Plex server configuration: {e}")
            messagebox.showerror("Error", f"Failed to save Plex server configuration: {e}")

    def _fetch_and_display_server_name(self):
        plex_url = self.plex_url_entry.get()
        plex_token = self.plex_token_entry.get()

        if plex_url and plex_token:
            try:
                response = requests.get(f"{plex_url}/?X-Plex-Token={plex_token}", timeout=10)
                if response.status_code == 200:
                    root = ET.fromstring(response.content)
                    server_name = root.attrib.get("friendlyName", "Unknown Server")
                    self.server_name_label.config(text=f"Server Name: {server_name}")
                else:
                    self.server_name_label.config(text="Server Name: Unable to fetch")
            except Exception as e:
                self.server_name_label.config(text=f"Server Name: Error fetching ({str(e)})")
        else:
            self.server_name_label.config(text="Server Name: Missing URL or Token")

    def _add_general_field(self, parent_frame, label_text, start_row, config_key, explanation=""):
        ttk.Label(parent_frame, text=label_text).grid(row=start_row, column=0, sticky="w", padx=10, pady=5)
        value = self.config.get(config_key, "")
        if config_key == "libraries" and isinstance(value, list):
            value = ", ".join(value)

        entry = ttk.Entry(parent_frame, width=50)
        entry.grid(row=start_row, column=1, sticky="w", padx=10, pady=5)
        entry.insert(0, value)
        setattr(self, f"{config_key}_entry", entry)

        next_row = start_row + 1
        if explanation:
            ttk.Label(
                parent_frame,
                text=explanation,
                font=("Segoe UI", 9, "italic"),
                foreground="yellow",
                wraplength=600
            ).grid(row=next_row, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))
            next_row += 1
        else:
            next_row += 1
        return next_row

    def _create_settings_tab(self):
        container = ttk.Frame(self.settings_tab)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        canvas.create_window((0, 0), window=scrollable_frame, anchor="n", width=900)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(-1 * (event.delta // 120), "units")

        canvas.bind("<Enter>",
                    lambda e: self.exemptions_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: self.exemptions_canvas.unbind_all("<MouseWheel>"))

        ttk.Label(scrollable_frame, text="Settings", font=("Segoe UI", 24, "bold")).pack(pady=20)

        save_settings_button = ttk.Button(
            scrollable_frame,
            text="Save Settings",
            command=self.save_settings,
            bootstyle="warning"
        )
        save_settings_button.pack(pady=10, padx=20, fill="x")

        # General Config
        general_config_frame = ttk.LabelFrame(scrollable_frame, text="General Configuration", padding=10)
        general_config_frame.pack(fill="x", padx=20, pady=10)
        current_row = 0
        current_row = self._add_general_field(
            general_config_frame,
            "Library Names (comma-separated):",
            current_row,
            "libraries",
            explanation="A comma-separated list of Plex libraries to manage."
        )

        current_row = self._add_general_field(
            general_config_frame,
            "Pinning Program Run Interval (minutes):",
            current_row,
            "pinning_interval",
            explanation="How often the script attempts to pin/unpin collections."
        )

        current_row = self._add_general_field(
            general_config_frame,
            "Days to Exclude Collections after Pinning:",
            current_row,
            "exclusion_days",
            explanation="Number of days a pinned collection is excluded from re-pinning."
        )

        current_row = self._add_general_field(
            general_config_frame,
            "Minimum Items for Valid Collection:",
            current_row,
            "minimum_items",
            explanation="Minimum items required in a collection to be considered for pinning."
        )

        self.new_episodes_var = tk.BooleanVar(value=self.config.get("always_pin_new_episodes", False))
        ttk.Checkbutton(
            general_config_frame,
            text="Always Pin 'New Episodes' if Available as a Collection",
            variable=self.new_episodes_var
        ).grid(row=current_row, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        current_row += 1
        ttk.Label(
            general_config_frame,
            text="If checked, 'New Episodes' will always be pinned if present.",
            font=("Segoe UI", 9, "italic"),
            foreground="yellow",
            wraplength=600
        ).grid(row=current_row, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))
        current_row += 1

        pinning_targets_frame = ttk.LabelFrame(scrollable_frame, text="Pinning Target Configuration", padding=10)
        pinning_targets_frame.pack(fill="x", padx=20, pady=10)

        # Add an explanatory label
        ttk.Label(
            pinning_targets_frame,
            text=(
                "Select where pinned collections will be configured:"
            ),
            font=("Segoe UI", 9, "italic"),
            wraplength=600,
            justify="left",
            foreground="yellow",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))

        # Add the checkboxes for the pinning targets
        self.library_recommended_var = tk.BooleanVar(
            value=self.config.get("pinning_targets", {}).get("library_recommended", True))
        self.home_var = tk.BooleanVar(value=self.config.get("pinning_targets", {}).get("home", True))
        self.shared_home_var = tk.BooleanVar(value=self.config.get("pinning_targets", {}).get("shared_home", True))

        ttk.Checkbutton(
            pinning_targets_frame,
            text="Library Recommended: Shows collections in the 'Recommended' section of a library.",
            variable=self.library_recommended_var
        ).grid(row=1, column=0, sticky="w", padx=10, pady=5)

        ttk.Checkbutton(
            pinning_targets_frame,
            text="Home: Displays collections on the main Home screen.",
            variable=self.home_var
        ).grid(row=2, column=0, sticky="w", padx=10, pady=5)

        ttk.Checkbutton(
            pinning_targets_frame,
            text="Shared Home: Visible to shared users on their Home screen.",
            variable=self.shared_home_var
        ).grid(row=3, column=0, sticky="w", padx=10, pady=5)

        # Default Limits
        default_limits_frame = ttk.LabelFrame(scrollable_frame, text="Library Default Limits", padding=10)
        default_limits_frame.pack(fill="x", padx=20, pady=10)
        ttk.Label(
            default_limits_frame,
            text="Set default pinning limits for each library when no time block applies:",
            font=("Segoe UI", 9, "italic"), foreground="yellow", wraplength=600
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        self.default_limit_entries = {}
        libraries = self.config.get("libraries", [])
        dl_current_row = 1
        for library in libraries:
            ttk.Label(default_limits_frame, text=f"{library}:").grid(row=dl_current_row, column=0, padx=5, pady=5,
                                                                     sticky="w")
            entry = ttk.Entry(default_limits_frame, width=10)
            entry.grid(row=dl_current_row, column=1, padx=5, pady=5, sticky="w")
            entry.insert(0, self.config.get("default_limits", {}).get(library, 5))
            self.default_limit_entries[library] = entry
            dl_current_row += 1

        # Time Block Config
        time_block_frame = ttk.LabelFrame(scrollable_frame, text="Dynamic Library Time Block Configuration", padding=10)
        time_block_frame.pack(fill="x", padx=20, pady=10)
        ttk.Label(
            time_block_frame,
            text="Configure different pinning limits by day/time.",
            font=("Segoe UI", 9, "italic"),
            foreground="yellow",
            wraplength=600
        ).grid(row=0, column=0, columnspan=7, pady=5, sticky="n")

        ttk.Label(time_block_frame, text="Select Library:").grid(row=1, column=0, columnspan=7, pady=5, sticky="n")
        self.selected_library = tk.StringVar()
        self.library_dropdown = ttk.Combobox(
            time_block_frame,
            textvariable=self.selected_library,
            values=self.config.get("libraries", []),
            state="readonly"
        )
        self.library_dropdown.grid(row=2, column=0, columnspan=7, padx=10, pady=5, sticky="ew")
        self.library_dropdown.bind("<<ComboboxSelected>>", self._on_library_selected)

        days_frame = ttk.LabelFrame(time_block_frame, text="Select Days", padding=10)
        days_frame.grid(row=3, column=0, columnspan=7, pady=10, sticky="ew")
        ttk.Label(
            days_frame,
            text="Choose which days these time blocks apply:",
            font=("Segoe UI", 9, "italic"),
            wraplength=600
        ).grid(row=0, column=0, columnspan=7, sticky="w", padx=10, pady=5)
        for i in range(7):
            days_frame.grid_columnconfigure(i, weight=1)
        self.day_vars = {}
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for idx, day in enumerate(days):
            var = tk.BooleanVar(value=False)
            chk = ttk.Checkbutton(days_frame, text=day, variable=var)
            chk.grid(row=1, column=idx, padx=5, pady=5, sticky="w")
            self.day_vars[day] = var

        ttk.Label(
            time_block_frame,
            text="Define start/end times (HH:MM) and pin limits for each block.",
            font=("Segoe UI", 9, "italic"), foreground="yellow", wraplength=600
        ).grid(row=4, column=0, columnspan=7, padx=10, pady=(0, 10), sticky="w")

        self.time_block_entries = {}
        blocks = ["Morning", "Afternoon", "Evening"]
        for idx, block_name in enumerate(blocks):
            ttk.Label(time_block_frame, text=f"{block_name} Start:").grid(row=5 + idx, column=1, padx=5, pady=5,
                                                                          sticky="w")
            start_entry = ttk.Entry(time_block_frame, width=10)
            start_entry.grid(row=5 + idx, column=2, padx=5, pady=5, sticky="w")

            ttk.Label(time_block_frame, text="End:").grid(row=5 + idx, column=3, padx=5, pady=5, sticky="w")
            end_entry = ttk.Entry(time_block_frame, width=10)
            end_entry.grid(row=5 + idx, column=4, padx=5, pady=5, sticky="w")

            ttk.Label(time_block_frame, text="Limit:").grid(row=5 + idx, column=5, padx=5, pady=5, sticky="w")
            limit_entry = ttk.Entry(time_block_frame, width=5)
            limit_entry.grid(row=5 + idx, column=6, padx=5, pady=5, sticky="w")

            self.time_block_entries[block_name] = {
                "start_time": start_entry,
                "end_time": end_entry,
                "limit": limit_entry
            }

        save_time_blocks_button = ttk.Button(
            time_block_frame,
            text="Save Time Blocks",
            command=self._apply_time_blocks_to_days,
            bootstyle="warning"
        )
        save_time_blocks_button.grid(row=5 + len(blocks), column=0, columnspan=7, pady=10, sticky="ew", padx=5)

        self.schedule_summary_frame = ttk.LabelFrame(scrollable_frame, text="Current Time Blocks", padding=10)
        self.schedule_summary_frame.pack(fill="both", padx=20, pady=10)

        ttk.Label(
            self.schedule_summary_frame,
            text="A summary of your configured time blocks:",
            font=("Segoe UI", 9, "italic"),
            wraplength=600
        ).pack(anchor="w", pady=5, padx=10)

        self._refresh_schedule_summary()

        # Seasonal Blocks Section
        self._create_seasonal_blocks_section(scrollable_frame)

    def _create_seasonal_blocks_section(self, scrollable_frame):
        seasonal_frame = ttk.LabelFrame(scrollable_frame, text="Seasonal Blocks Configuration", padding=10)
        seasonal_frame.pack(fill="x", padx=20, pady=10)

        ttk.Label(
            seasonal_frame,
            text="Define blocks of time during which a specific collection is pinned.",
            font=("Segoe UI", 9, "italic"),
            foreground="yellow",
            wraplength=600,
        ).grid(row=0, column=0, columnspan=5, sticky="w", padx=10, pady=5)

        ttk.Button(
            seasonal_frame,
            text="Add Seasonal Block",
            bootstyle="warning",
            command=self._add_seasonal_block
        ).grid(row=1, column=0, padx=10, pady=5, sticky="w")

        self.seasonal_blocks_table = ttk.Treeview(
            seasonal_frame,
            columns=("Name", "Start Date", "End Date", "Libraries", "Collection"),
            show="headings",
            height=10,
        )
        self.seasonal_blocks_table.grid(row=2, column=0, columnspan=5, padx=10, pady=5, sticky="nsew")

        self.seasonal_blocks_table.heading("Name", text="Block Name")
        self.seasonal_blocks_table.heading("Start Date", text="Start Date")
        self.seasonal_blocks_table.heading("End Date", text="End Date")
        self.seasonal_blocks_table.heading("Libraries", text="Libraries")
        self.seasonal_blocks_table.heading("Collection", text="Collection")

        for col in ("Name", "Start Date", "End Date", "Libraries", "Collection"):
            self.seasonal_blocks_table.column(col, width=120, stretch=True)

        ttk.Button(
            seasonal_frame,
            text="Edit Selected",
            bootstyle="warning",
            command=self._edit_seasonal_block
        ).grid(row=3, column=0, padx=5, pady=10, sticky="w")

        ttk.Button(
            seasonal_frame,
            text="Delete Selected",
            bootstyle="warning",
            command=self._delete_seasonal_block
        ).grid(row=3, column=1, padx=5, pady=10, sticky="w")

        self._refresh_seasonal_blocks_table()

    def _refresh_seasonal_blocks_table(self):
        for row in self.seasonal_blocks_table.get_children():
            self.seasonal_blocks_table.delete(row)

        seasonal_blocks = self.config.get("seasonal_blocks", [])
        for block in seasonal_blocks:
            self.seasonal_blocks_table.insert(
                "",
                "end",
                values=(block.get("name"), block.get("start_date"), block.get("end_date"),
                        ", ".join(block.get("libraries", [])), block.get("collection"))
            )

    def _add_seasonal_block(self):
        SeasonalBlockDialog(self, title="Add Seasonal Block", callback=self._save_new_seasonal_block)

    def _save_new_seasonal_block(self, new_block):
        self.config.setdefault("seasonal_blocks", []).append(new_block)
        save_config(self.config)
        self._refresh_seasonal_blocks_table()
        messagebox.showinfo("Success", "Seasonal block added successfully.")

    def _edit_seasonal_block(self):
        selected = self.seasonal_blocks_table.selection()
        if not selected:
            messagebox.showwarning("Warning", "No block selected.")
            return

        values = self.seasonal_blocks_table.item(selected[0], "values")
        name = values[0]
        seasonal_blocks = self.config.get("seasonal_blocks", [])
        block = next((b for b in seasonal_blocks if b.get("name") == name), None)
        if not block:
            messagebox.showerror("Error", "Block not found in config.")
            return

        SeasonalBlockDialog(self, title="Edit Seasonal Block", block=block, callback=self._save_edited_seasonal_block)

    def _save_edited_seasonal_block(self, edited_block):
        seasonal_blocks = self.config.get("seasonal_blocks", [])
        # Replace old block with edited block
        for i, b in enumerate(seasonal_blocks):
            if b["name"] == edited_block["name"]:
                seasonal_blocks[i] = edited_block
                break
        save_config(self.config)
        self._refresh_seasonal_blocks_table()
        messagebox.showinfo("Success", "Seasonal block edited successfully.")

    def _delete_seasonal_block(self):
        selected = self.seasonal_blocks_table.selection()
        if not selected:
            messagebox.showwarning("Warning", "No block selected.")
            return

        seasonal_blocks = self.config.get("seasonal_blocks", [])
        for sel in selected:
            values = self.seasonal_blocks_table.item(sel, "values")
            seasonal_blocks = [block for block in seasonal_blocks if block.get("name") != values[0]]

        self.config["seasonal_blocks"] = seasonal_blocks
        save_config(self.config)
        self._refresh_seasonal_blocks_table()
        messagebox.showinfo("Success", "Selected seasonal blocks deleted.")

    def save_settings(self):
        try:
            self.config["minimum_items"] = int(self.minimum_items_entry.get())
            self.config["exclusion_days"] = int(self.exclusion_days_entry.get())
            self.config["always_pin_new_episodes"] = self.new_episodes_var.get()
            self.config["libraries"] = [lib.strip() for lib in self.libraries_entry.get().split(",") if lib.strip()]
            self.config["pinning_interval"] = int(self.pinning_interval_entry.get())

            self.config["default_limits"] = {}
            for library, entry in self.default_limit_entries.items():
                self.config["default_limits"][library] = int(entry.get())

            # Save new pinning target preferences
            self.config["pinning_targets"] = {
                "library_recommended": self.library_recommended_var.get(),
                "home": self.home_var.get(),
                "shared_home": self.shared_home_var.get()
            }

            save_config(self.config)
            messagebox.showinfo("Success", "Settings saved successfully!")
            logging.info("Settings saved.")
        except ValueError:
            messagebox.showerror("Error", "Invalid input. Please enter valid integers.")
            logging.error("Invalid input in settings tab.")
        except Exception as e:
            messagebox.showerror("Error", f"Error saving settings: {e}")
            logging.error(f"Error saving settings: {e}")

    def _apply_time_blocks_to_days(self):
        selected_days = [day for day, var in self.day_vars.items() if var.get()]
        library_name = self.selected_library.get()

        if not library_name:
            messagebox.showwarning("Warning", "No library selected.")
            return

        for day in selected_days:
            time_blocks = {}
            for block_name, entries in self.time_block_entries.items():
                start_time = entries["start_time"].get().strip()
                end_time = entries["end_time"].get().strip()
                limit = entries["limit"].get().strip()

                if self._validate_time_format(start_time) and self._validate_time_format(end_time) and limit.isdigit():
                    time_blocks[block_name] = {
                        "start_time": start_time,
                        "end_time": end_time,
                        "limit": int(limit)
                    }
                else:
                    messagebox.showerror(
                        "Error",
                        f"Invalid input in {block_name} block for {day}. Ensure time is HH:MM and limit is a number."
                    )
                    return

            self.config.setdefault("libraries_settings", {}).setdefault(library_name, {}).setdefault("time_blocks", {})[
                day] = time_blocks

        save_config(self.config)
        self._refresh_schedule_summary()
        messagebox.showinfo("Success", "Time blocks applied to selected days.")

    def _refresh_schedule_summary(self):
        for widget in self.schedule_summary_frame.winfo_children():
            widget.destroy()

        library_name = self.selected_library.get()
        if not library_name:
            ttk.Label(self.schedule_summary_frame, text="No library selected.").pack()
            return

        library_settings = self.config.get("libraries_settings", {}).get(library_name, {})
        time_blocks = library_settings.get("time_blocks", {})

        days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for day in days_of_week:
            ttk.Label(self.schedule_summary_frame, text=f"{day}", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=2)
            day_blocks = time_blocks.get(day, {})
            if not day_blocks:
                ttk.Label(self.schedule_summary_frame, text="  No blocks configured").pack(anchor="w", padx=10, pady=1)
            else:
                for block_name, details in day_blocks.items():
                    if not isinstance(details, dict):
                        logging.warning(f"Invalid time block format for {block_name} in {day}. Skipping.")
                        continue
                    start_time = details.get("start_time", "N/A")
                    end_time = details.get("end_time", "N/A")
                    limit = details.get("limit", "N/A")
                    summary = f"  {block_name}: {start_time} - {end_time} (Limit: {limit})"
                    ttk.Label(self.schedule_summary_frame, text=summary).pack(anchor="w", padx=20, pady=1)

    def _create_logs_tab(self):
        frame = ttk.Frame(self.logs_tab, padding=20)
        frame.pack(expand=True, fill="both")

        ttk.Label(frame, text="Activity Logs", font=("Segoe UI", 30, "bold")).pack(pady=10)
        self.logs_text = tk.Text(
            frame,
            wrap="word",
            state="disabled",
            bg="black",
            fg="white",
            height=20,
            width=80,
            font=("Consolas", 10),
        )
        self.logs_text.pack(expand=True, fill="both", padx=10, pady=10)

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.logs_text.yview)
        self.logs_text["yscrollcommand"] = scrollbar.set
        scrollbar.pack(side="right", fill="y")

        button_frame = ttk.Frame(frame)
        button_frame.pack(pady=10)

        self.run_main_button = ttk.Button(button_frame, text="Run Main Function", bootstyle="warning", command=self.start_script)
        self.run_main_button.pack(side="left", padx=10)

        self.restart_button = ttk.Button(button_frame, text="Restart Program", bootstyle="warning", command=self.restart_program)
        self.restart_button.pack(side="left", padx=10)

        gui_handler = GuiHandler(self.log_queue)
        gui_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        logging.getLogger().addHandler(gui_handler)
        self.after(100, self.process_log_queue)

    def process_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.logs_text.config(state="normal")
            self.logs_text.insert(tk.END, msg + "\n")
            self.logs_text.config(state="disabled")
            self.logs_text.see(tk.END)
        self.after(100, self.process_log_queue)

    def _create_exclusion_tab(self):
        frame = ttk.Frame(self.exclusion_tab, padding="10")
        frame.pack(fill="both", expand=True)

        center_frame = ttk.Frame(frame)
        center_frame.pack(fill="none", expand=True, anchor="center")

        self.exclusion_listbox = tk.Listbox(center_frame, height=50, width=100)
        self.exclusion_listbox.pack(side="left", fill="y", padx=10, pady=10)

        exclusion_scrollbar = ttk.Scrollbar(center_frame, orient="vertical", command=self.exclusion_listbox.yview)
        exclusion_scrollbar.pack(side="left", fill="y")
        self.exclusion_listbox.config(yscrollcommand=exclusion_scrollbar.set)

        button_frame = ttk.Frame(center_frame)
        button_frame.pack(side="left", fill="y", padx=10, pady=10)

        ttk.Button(button_frame, text="Refresh", bootstyle="warning", command=self.refresh_exclusion_list).pack(fill="x", pady=5)
        ttk.Button(button_frame, text="Remove Selected", bootstyle="warning", command=self.remove_exclusion_list_item).pack(fill="x", pady=5)
        ttk.Button(button_frame, text="Reset List", bootstyle="warning", command=self.reset_exclusion_list).pack(fill="x", pady=5)

        self.refresh_exclusion_list()

    def remove_exclusion_list_item(self):
        selected_items = self.exclusion_listbox.curselection()
        if not selected_items:
            messagebox.showwarning("Warning", "No collection selected.")
            return

        used_collections = load_used_collections()
        for index in selected_items:
            item_text = self.exclusion_listbox.get(index)
            collection_name = item_text.split(" (")[0]
            if collection_name in used_collections:
                del used_collections[collection_name]

        save_used_collections(used_collections)
        self.refresh_exclusion_list()
        messagebox.showinfo("Success", "Selected collections removed from the exclusion list.")

    def reset_exclusion_list(self):
        try:
            reset_exclusion_list_file()
            self.refresh_exclusion_list()
        except Exception as e:
            logging.error(f"Error resetting exclusion list: {e}")
            messagebox.showerror("Error", "Failed to reset the exclusion list.")

    def refresh_exclusion_list(self):
        logging.info("Refreshing Exclusion List tab.")
        self.exclusion_listbox.delete(0, tk.END)
        used_collections = load_used_collections()
        for collection_name, expiration_date in used_collections.items():
            self.exclusion_listbox.insert(tk.END, f"{collection_name} (Expires: {expiration_date})")

    def _create_user_exemptions_tab(self):
        frame = ttk.Frame(self.user_exemptions_tab, padding="10")
        frame.pack(fill="both", expand=True)

        save_button = ttk.Button(frame, text="Save Exemptions", bootstyle="warning", command=self.save_user_exemptions_gui)
        save_button.pack(anchor="center", pady=(0, 10))

        explanation_label = ttk.Label(
            frame,
            text="Checkbox States: ✓ = User Exemption, Empty = Eligible for Pinning",
            font=("Segoe UI", 10, "italic"),
            wraplength=900,
            justify="center",
        )
        explanation_label.pack(anchor="center", pady=(0, 10))

        scrollable_frame = ttk.Frame(frame)
        scrollable_frame.pack(fill="both", expand=True)

        self.exemptions_canvas = tk.Canvas(scrollable_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scrollable_frame, orient="vertical", command=self.exemptions_canvas.yview)
        self.exemptions_canvas.configure(yscrollcommand=scrollbar.set)

        self.exemptions_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.libraries_frame = ttk.Frame(self.exemptions_canvas)
        self.canvas_window = self.exemptions_canvas.create_window((0, 0), window=self.libraries_frame, anchor="n")

        def on_frame_configure(event):
            self.exemptions_canvas.configure(scrollregion=self.exemptions_canvas.bbox("all"))

        self.libraries_frame.bind("<Configure>", on_frame_configure)

        def _on_mousewheel(event):
            self.exemptions_canvas.yview_scroll(-1 * (event.delta // 120), "units")

        self.exemptions_canvas.bind("<Enter>",
                                    lambda e: self.exemptions_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        self.exemptions_canvas.bind("<Leave>", lambda e: self.exemptions_canvas.unbind_all("<MouseWheel>"))

        self.refresh_user_exemptions()

    def save_user_exemptions_gui(self):
        try:
            exemptions = []
            for library_name, checkboxes in self.user_exemption_checkboxes.items():
                for collection_name, var in checkboxes.items():
                    if var.get() == 1:
                        exemptions.append(collection_name)

            self.user_exemptions = exemptions
            save_user_exemptions(exemptions)
            logging.info("User exemptions saved successfully.")
        except Exception as e:
            logging.error(f"Error saving user exemptions: {e}")
            messagebox.showerror("Error", "Failed to save user exemptions.")

    def refresh_user_exemptions(self):
        for widget in self.libraries_frame.winfo_children():
            widget.destroy()
        self.user_exemption_checkboxes = {}

        if not self.plex:
            try:
                self.plex = connect_to_plex(self.config)
            except Exception as e:
                logging.error("Error connecting to Plex server.")
                return

        row, col = 0, 0
        for library_name in self.config.get("libraries", []):
            try:
                library_frame = ttk.LabelFrame(self.libraries_frame, text=library_name, padding=10)
                library_frame.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
                self.user_exemption_checkboxes[library_name] = {}

                # Add "Select All" checkbox
                select_all_var = tk.IntVar()
                library_collections = [collection.title for collection in self.plex.library.section(library_name).collections()]
                library_exemptions = [c for c in self.user_exemptions if c in library_collections]
                if library_collections and all(c in self.user_exemptions for c in library_collections):
                    select_all_var.set(1)
                else:
                    select_all_var.set(0)

                select_all_cb = ttk.Checkbutton(
                    library_frame,
                    text="Select All",
                    variable=select_all_var,
                    command=lambda lib=library_name, var=select_all_var: self._toggle_select_all(lib, var)
                )
                select_all_cb.pack(anchor="w", padx=5, pady=5)

                self.select_all_vars[library_name] = select_all_var  # Store the variable

                # Add a search bar for filtering collections
                search_var = tk.StringVar()
                search_entry = ttk.Entry(library_frame, textvariable=search_var)
                search_entry.pack(anchor="w", padx=5, pady=5)
                search_entry.insert(0, "")

                # Frame to hold the collection checkboxes
                collection_frame = ttk.Frame(library_frame)
                collection_frame.pack(fill="both", expand=True)

                # Bind search functionality
                search_var.trace_add("write", self._create_filter_callback(library_name, collection_frame, search_var))

                # Populate collections initially
                self._populate_collections(library_name, collection_frame)

                col += 1
                if col >= 3:
                    col = 0
                    row += 1

            except Exception as e:
                logging.error(f"Error loading library '{library_name}': {e}")
                messagebox.showerror("Error", f"Error loading library '{library_name}': {e}")

    def _populate_collections(self, library_name, parent_frame, query=""):
        library = self.plex.library.section(library_name)
        for idx, collection in enumerate(library.collections()):
            if query and query not in collection.title.lower():
                continue
            var = tk.IntVar(value=1 if collection.title in self.user_exemptions else 0)
            bg_color = "white" if idx % 2 == 0 else "lightgray"
            cb = tk.Checkbutton(
                parent_frame,
                text=collection.title,
                variable=var,
                anchor="w",
                bg=bg_color,
                command=lambda lib=library_name: self._update_select_all(lib)
            )
            cb.pack(fill="x", padx=20, pady=2)
            self.user_exemption_checkboxes[library_name][collection.title] = var

    def _create_filter_callback(self, library_name, collection_frame, search_var):
        def filter_collections(*args):
            query = search_var.get().lower()
            for widget in collection_frame.winfo_children():
                widget.destroy()
            self._populate_collections(library_name, collection_frame, query)

        return filter_collections

    def _toggle_select_all(self, library_name, select_all_var):
        new_state = 1 if select_all_var.get() else 0
        for collection_title, var in self.user_exemption_checkboxes[library_name].items():
            var.set(new_state)
        self.save_user_exemptions_gui()  # Automatic save after toggling "Select All"

    def _update_select_all(self, library_name):
        all_selected = all(var.get() == 1 for var in self.user_exemption_checkboxes[library_name].values())
        self.select_all_vars[library_name].set(1 if all_selected else 0)
        self.save_user_exemptions_gui()  # Automatic save after individual checkbox toggling

    def _on_library_selected(self, event=None):
        self._populate_library_time_blocks()
        self._refresh_schedule_summary()

    def _populate_library_time_blocks(self):
        library_name = self.selected_library.get()
        if not library_name:
            return

        for block in self.time_block_entries.values():
            for field in block.values():
                field.delete(0, "end")

        library_settings = self.config.get("libraries_settings", {}).get(library_name, {})
        time_blocks = library_settings.get("time_blocks", {})

        if not isinstance(time_blocks, dict):
            logging.error(f"Invalid time_blocks for library '{library_name}': {time_blocks}")
            return

        for block_name, entries in self.time_block_entries.items():
            # We'll just clear and ignore if not present
            block_data = {}
            # We don't store block-level keys by block_name directly,
            # user applies them via _apply_time_blocks_to_days()
            # So no direct mapping. It's done day-by-day.
            # No predefined data to load here because they are day-dependent.
            # This is just a placeholder if needed.
            start_val = block_data.get("start_time", "")
            end_val = block_data.get("end_time", "")
            limit_val = block_data.get("limit", "")

            entries["start_time"].insert(0, start_val)
            entries["end_time"].insert(0, end_val)
            entries["limit"].insert(0, str(limit_val))

    def _validate_time_format(self, time_str):
        try:
            datetime.strptime(time_str, "%H:%M")
            return True
        except ValueError:
            return False

    def start_script(self, show_message=True):
        if not self.script_thread or not self.script_thread.is_alive():
            self.stop_event.clear()
            self.script_thread = threading.Thread(target=main, args=(self, self.stop_event), daemon=True)
            self.script_thread.start()
            self.run_main_button.config(state="disabled")
            logging.info("Automation script started.")
        else:
            logging.warning("Script is already running.")

    def stop_script(self):
        if self.script_thread and self.script_thread.is_alive():
            logging.info("Stopping the automation script...")
            self.stop_event.set()  # Signal the thread to stop
            try:
                self.script_thread.join(timeout=10)  # Wait for the thread to finish
                logging.info("Automation script stopped.")
                self.script_thread = None
            except Exception as e:
                logging.error(f"Error stopping the script: {e}")
            finally:
                self.run_main_button.config(state="normal")
                self.stop_main_button.config(state="disabled")
        else:
            logging.warning("No script is currently running.")

    def restart_program(self):
        logging.info("Restarting the program...")
        print("Restarting the program...")
        if self.script_thread and self.script_thread.is_alive():
            logging.info("Stopping the automation script before restarting...")
            print("Stopping the automation script before restarting...")
            self.stop_script()
            self.script_thread.join()
            logging.info("Automation script stopped.")
            print("Automation script stopped.")
        try:
            python = sys.executable
            os.execl(python, python, *sys.argv)
        except Exception as e:
            logging.error(f"Failed to restart the program: {e}")
            print(f"Failed to restart the program: {e}")
            messagebox.showerror("Error", f"Failed to restart the program: {e}")

# ------------------------------ Application Entry Point ------------------------------

if __name__ == "__main__":
    try:
        app = DynamiXGUI()
        app.mainloop()
    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        traceback.print_exc()
