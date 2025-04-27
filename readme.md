# dynamiX – Plex Recommendations Manager

**Version**: 2.0.0

A web-based automation tool for dynamically managing Plex collections pinning and seasonal pre-rolls.  
Pins and unpins library collections based on configurable time blocks, seasonal schedules, manual overrides, and even handles pre-roll video management.

---

## 🚀 Features

- **Web UI & PWA**  
  Accessible at port `1166`, with offline support via service worker ([manifest.json](static/manifest.json)).  
- **Multi-threaded Pinning**  
  Speed up pinning loops by handling libraries in parallel.  
- **Dynamic Pinning**  
  Schedule by time blocks, seasonal/holiday blocks, and “always-pinned” collections.
- **Pin by Library**  
  Pin on any combination of home/shared home/recommended and optionally generate seperate sets of pins for home and library recommended.
- **Pre-Roll Management**  
  Automatically rename pre-roll videos based on date blocks (see `settings → Pre-Roll`).  
- **Exclusions & Exemptions**  
  Avoid re-pinning recently pinned items and manually exempt specific collections.  
- **Quick-Add & Manual Blocks**  
  Fast holiday presets or fully custom date ranges for pinning and pre-rolls (managed seperate).  
- **HTTP Basic Auth**  
  Optional for secure local or public deployments.  
- **Update Notifications**  
  Checks GitHub for new releases (auto-update is stubbed out for now).

---

## Preview

- All-New Dashboard
![image](https://github.com/user-attachments/assets/09e26112-dc6f-4c66-9738-35120c02d5b3)

- Settings
![image](https://github.com/user-attachments/assets/712c278c-2032-471c-8da1-894aae9610df)
![image](https://github.com/user-attachments/assets/50af3bb4-4ad0-46ed-87d4-fb3986307740)
![image](https://github.com/user-attachments/assets/7c515248-a6c8-497a-94c4-ab3bdabbc626)
![image](https://github.com/user-attachments/assets/ddb7d90c-ce8c-450b-a630-6b87f696864d)
![image](https://github.com/user-attachments/assets/9988fdc5-46b2-4634-af6b-5b0fe00f6481)

- Exclusions
![image](https://github.com/user-attachments/assets/624e8718-5d4c-4f32-854c-082e13791412)

- Exemptions
![image](https://github.com/user-attachments/assets/0be45493-63b2-4198-be72-162ce90728ca)

- Logs
![image](https://github.com/user-attachments/assets/ae820ec6-198a-416d-bc07-7eb0b4a7d6ad)

## 📦 Installation

### Prerequisites

- Python 3.8+  
- Plex server URL & Token ([How to find your token][plex-token])  

### Setting Up Pre-Rolls ###

1. Make sure all of your Pre-Rolls are in one folder with no other media
![image](https://github.com/user-attachments/assets/e7dc4b4f-a094-4d1d-8a89-e1712740004a)
2. Point Plex to that path ending with /PlexMainPreRoll.mp4 For Example:
```bash
P:\Movie Roll\PlexMainPreRoll.mp4
```
![image](https://github.com/user-attachments/assets/df3f97d5-7a99-49d7-a6e1-598f7a702e37)
3. Point dynamix to the folder (DO NOT Include /PlexMainPreRoll.mp4 here)
![image](https://github.com/user-attachments/assets/0b29e67e-0622-4c78-9e63-46ea64b5233c)

4. Set your default pre-roll and configure some season blocks
![image](https://github.com/user-attachments/assets/ffe4c4fe-5e6c-4622-b82c-2616c729976f)

### From the Releases Page ###

1. **Get the Latest Release**
   - https://github.com/TheImaginear/dynamiX/releases/latest
2. **Unzip the package**
3. **Open a command prompt and navigate to the dynamiX folder**
4. **Run the main script to start**
   ```bash
   pip install -r requirements.txt 
5. **Run the main script to start**
   ```bash
   py dynamixmain.py
6. **Visit http://127.0.0.1:1166/**

### Through Docker ###

**Get the Latest Release**
```bash
docker pull clharrel/dynamix:latest

docker run -d --name dynamix -p 1166:1166 `
  -v "${PWD}\config.json:/app/config.json" `
  -v "${PWD}\user_exemptions.json:/app/user_exemptions.json" `
  -v "${PWD}\used_collections.json:/app/used_collections.json" `
  -v "${PWD}\run_state.json:/app/run_state.json" `
  -v "${PWD}\logs:/app/logs" `
  clharrel/dynamix:latest
