# Recipe Ripper

Convert any recipe webpage into a clean, metric-unit PDF or Apple Note with one click.

The extension scrapes the recipe from the current tab, converts imperial measurements to metric, and lets you download a formatted PDF or save directly to Apple Notes — all via a local Python server running on your Mac.

---

## How it works

- A browser extension button scrapes the recipe from the active tab
- It sends the content to a local Flask server (`localhost:5050`)
- The server converts US measurements to metric weight
- Choose to download a PDF or save as an Apple Note

---

## 1. Install prerequisites

### Xcode command line tools

```sh
xcode-select --install
```

### Homebrew

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Build dependencies (required for compiling Python)

```sh
brew install openssl readline sqlite3 xz tcl-tk@8 libb2 zstd zlib pkgconfig
```

---

## 2. Install Python 3.14 via pyenv

pyenv lets you install and manage Python versions without touching your system Python.

```sh
# Install pyenv (via Homebrew)
brew install pyenv

# Add pyenv to your shell (add these lines to ~/.zshrc or ~/.bash_profile)
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
echo 'eval "$(pyenv init -)"' >> ~/.zshrc
source ~/.zshrc

# Install Python 3.14
pyenv install 3.14

# Verify
python3 --version  # should show 3.14.x

# Ensure pip is available
python3 -m ensurepip --upgrade
```

The repo includes a `.python-version` file that tells pyenv to automatically use Python 3.14 whenever you're in this directory.

---

## 3. Install the backend server

The server runs as a macOS login item (auto-starts on login).

```sh
chmod +x install_service.sh
./install_service.sh
```

The script will:

- Find your Python 3 installation
- Install all dependencies from `requirements.txt`
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

## 4. Install the browser extension

### Chrome

1. Open `chrome://extensions`
2. Enable **Developer mode** (toggle in the top-right)
3. Click **Load unpacked**
4. Select the `chrome_extension/` folder from this repo

The "Recipe → Metric PDF" icon will appear in your toolbar.

### Firefox

1. Open `about:debugging#/runtime/this-firefox`
2. Click **Load Temporary Add-on**
3. Navigate to the `firefox_extension/` folder and select `manifest.json`

> Note: Firefox requires the extension to be reloaded after each browser restart unless it is signed and installed permanently. For permanent install, the extension would need to be submitted to [addons.mozilla.org](https://addons.mozilla.org).

---

## Usage

1. Navigate to any recipe page
2. Click the extension icon in your toolbar
3. The PDF will download automatically

---

## Requirements

- macOS (the server uses launchd)
- Xcode command line tools
- Homebrew
- Python 3.14 (via pyenv — see above)
- Flask (installed automatically by the install script)
