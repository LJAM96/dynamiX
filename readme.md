# 🎥 DynamiX - Plex Recommendations Manager

**DynamiX** is an automation tool for dynamically managing Plex collections pinning. It pins and unpins library collections based on configurable time blocks, ensuring fresh and relevant content is featured. This repository includes the Python script and its packaged `.exe` version for easier execution. It is important to note that CURRENTLY this tool does not actually create collections, that feature will be available soon!

---

Find the latest release of the .exe on the releases page https://github.com/TheImaginear/dynamiX/releases

## 🚀 **Features**

- **Dynamic Pinning**: Automatically pin collections based on time and day configurations.
- **Exclusion Handling**: Avoid re-pinning the same collection for a configurable period.
- **User Exemptions**: Allow manual exclusion of specific collections.
- **GUI Control**: Includes an intuitive graphical interface for configuration and monitoring.
- **Robust Logging**: Provides clear logs of actions and issues.

---

## 🔧 **Requirements**

- **Python 3.8+** *(for running the script)*
- **Plex Media Server**
- **Plex API Token** *(to authenticate and access the server)*
- Required Libraries: `plexapi`, `requests`, and `ttkbootstrap`

---

## 🛠️ **Installation**

### Option 1: Run the `.exe` File (Windows Only Right Now) *(Recommended for Non-Developers)*
1. Download the latest `script.exe` from the [Releases Page](https://github.com/TheImaginear/DynamiX/releases).
2. Place it in a directory of your choice.
3. Double-click the `script.exe` to launch the application.

### Option 2: Run the Python Script
1. Clone this repository:
   ```bash
   git clone https://github.com/YourUsername/DynamiX.git
   cd DynamiX
   ```
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the script:
   ```bash
   python src/script.py
   ```

### Option 3: Offical Docker Image:
1a. Grab the latest docker image:
   ```bash
   docker pull clharrel/dynamix:latest
   ```
1b. Grab it from the Repo Page:
(https://hub.docker.com/repository/docker/clharrel/dynamix/general)

2. Configure the config.json file with your preferences:
I highly recommend using the windows application with GUI to generate your config files! The docker build is the exact functions of the application version without the gui and an automatic run on start!


---

## 📃 **Configuration**

### Initial Setup
Upon the first run, the application will prompt you to fill in required configuration details:

- **Plex URL**: The address of your Plex Media Server (e.g., `http://<server_ip>:32400`).
- **Plex Token**: A valid Plex API Token (refer to instructions below).
- **Libraries**: Comma-separated list of Plex libraries to manage (e.g., `Movies, TV Shows`).
- **Pinning Interval**: How often the program pins/unpins collections (in minutes).

### Configuration Files
The following files are generated and updated dynamically:

- `config.json` - Stores the main configuration settings.
- `used_collections.json` - Tracks recently pinned collections to avoid immediate repeats.
- `user_exemptions.json` - Maintains a list of collections manually exempted by the user.

---

## 💡 **Finding Your Plex Token**

To access the Plex API, you need a valid token. Follow these steps to retrieve it:

1. Open the Plex Web App and log in to your Plex server.
2. Select any media item (e.g., a movie or TV episode).
3. Click the `Get Info` button (3-dot menu) and choose `View XML`.
4. A new tab will open. In the URL, find the part after `X-Plex-Token=`.
5. Copy the token and paste it into the configuration.

---

## 💥 **Usage**

1. Launch the application (`script.exe` or `python src/script.py`).
2. Use the intuitive GUI to:
   - Configure Plex server details and dynamic pinning settings.
   - Manage exclusions and user exemptions.
   - View activity logs in real-time.
3. Start the automation process by clicking **"Run Main Function"** on the **Logs** tab.

The running program:

![image](https://github.com/user-attachments/assets/ba23b7e0-a80e-46ad-a249-5a4f9a989af0)

Dynamic Exclusions list updated in the GUI:

![image](https://github.com/user-attachments/assets/dc492e99-27dd-40c6-99d7-7cdc8677a49a)

User-Set Exemptions:

![image](https://github.com/user-attachments/assets/b8be6f61-5f2a-4275-9593-223ef4623047)

Server Configuration Tab:

![image](https://github.com/user-attachments/assets/f943674f-f6c8-43e3-8094-31514a1eec58)

Settings Tab:

![image](https://github.com/user-attachments/assets/af8490ce-4bcb-469a-9839-cace22a4b524)
![image](https://github.com/user-attachments/assets/a5de59cc-0866-4396-8032-2c84d59abd53)


### Tabs Overview
| **Tab**              | **Description**                                                                       |
|----------------------|---------------------------------------------------------------------------------------|
| **Plex Server**      | Configure Plex server URL and API token. Display server name for confirmation.       |
| **Settings**         | Configure libraries, time blocks, and pinning settings.                             |
| **Logs**             | View real-time activity logs for debugging and monitoring.                           |
| **Dynamic Exclusions** | Manage collections that are temporarily excluded after being pinned.                |
| **User Exemptions**  | Manually exempt specific collections from being pinned.                              |

---

## 💰 **Features in Detail**

### Dynamic Time Blocks
Customize the number of collections pinned during specific times of the day. For example:
| **Day**       | **Time Block** | **Start Time** | **End Time** | **Limit** |
|---------------|---------------|---------------|-------------|-----------|
| Monday        | Morning       | 06:00         | 12:00       | 3         |
| Monday        | Evening       | 18:00         | 22:00       | 5         |

### Exclusion and Reset
- Collections that are pinned are excluded for a configurable number of days.
- If not enough valid collections are found, the exclusion list can be reset.

### User Exemptions
Manually exempt specific collections from being pinned using the **User Exemptions** tab.

---

## 📅 **Changelog**

### **v1.0.0** - *2024-06-01*
- **Initial Release**
   - Introduced dynamic pinning of Plex collections.
   - Added exclusion handling and user exemption management.
   - Provided a GUI for configuration and log monitoring.

---

## 📚 **Dependencies**

Required libraries are listed in `requirements.txt`:

```plaintext
plexapi
requests
ttkbootstrap
```

Install them with:
```bash
pip install -r requirements.txt
```

---

## 📈 **Contributing**

We welcome contributions! Please follow these steps:

1. Fork the repository.
2. Create a feature branch:
   ```bash
   git checkout -b feature-branch-name
   ```
3. Commit your changes with descriptive messages.
4. Push your changes:
   ```bash
   git push origin feature-branch-name
   ```
5. Open a Pull Request with details about your changes.

See the full contributing guidelines in [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 🔓 **License**

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 📢 **Support**

If you encounter issues, please open a ticket in the [Issues](https://github.com/TheImaginear/DynamiX/issues) section.

For general questions and feedback, feel free to reach out!
