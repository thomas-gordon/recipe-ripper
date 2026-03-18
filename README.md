# Recipe Ripper

Convert any recipe webpage into a clean, metric-unit PDF with one click.

The extension scrapes the recipe from the current tab, converts imperial measurements to metric, and downloads a formatted PDF — all via a local Python server running on your Mac.

---

## How it works

- A browser extension button scrapes the recipe from the active tab
- It sends the content to a local Flask server (`localhost:5050`)
- The server converts units and generates a PDF
- The PDF downloads automatically

---

## 1. Install the backend server

The server runs as a macOS login item (auto-starts on login).

```sh
chmod +x install_service.sh
./install_service.sh
```

The script will:

- Find your Python 3 installation
- Install Flask if it's missing
- Register the server as a launchd agent so it starts automatically

After installation the server runs at `http://localhost:5050`.

### Manage the server

```sh
# Stop
launchctl unload ~/Library/LaunchAgents/com.recipe.pdfserver.plist

# Start
launchctl load ~/Library/LaunchAgents/com.recipe.pdfserver.plist

# View logs
tail -f ~/Library/Logs/RecipePDFServer/server.log

# Uninstall
launchctl unload ~/Library/LaunchAgents/com.recipe.pdfserver.plist
rm ~/Library/LaunchAgents/com.recipe.pdfserver.plist
```

---

## 2. Install the browser extension

### Chrome

1. Open `chrome://extensions`
2. Enable **Developer mode** (toggle in the top-right)
3. Click **Load unpacked**
4. Select the `recipe_extension/` folder from this repo

The "Recipe → Metric PDF" icon will appear in your toolbar.

### Firefox

1. Open `about:debugging#/runtime/this-firefox`
2. Click **Load Temporary Add-on**
3. Navigate to the `recipe_extension/` folder and select `manifest.json`

> Note: Firefox requires the extension to be reloaded after each browser restart unless it is signed and installed permanently. For permanent install, the extension would need to be submitted to [addons.mozilla.org](https://addons.mozilla.org).

---

## Usage

1. Navigate to any recipe page
2. Click the extension icon in your toolbar
3. The PDF will download automatically

---

## Requirements

- macOS (the server uses launchd)
- Python 3
- Flask (installed automatically by the install script)
