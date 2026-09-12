# Platform Service Templates

Use these templates to run the LOTBOOK API as a background service. The web UI can be served by a reverse proxy or by a separate front-end service (Vite in dev).

Notes:
- Use `LOTBOOK_WEB_API_KEY` to gate API access in production and set it in service environments.
- Load `.env` in your service environment if you rely on feed credentials.

## Windows (NSSM)

1) Install NSSM: https://nssm.cc/
2) Create the service:

```powershell
nssm install LotbookApi "C:\Path\To\Python\python.exe" "-m uvicorn web_api.app:app --host 127.0.0.1 --port 8000"
nssm set LotbookApi AppDirectory "C:\Path\To\lotbook"
nssm set LotbookApi AppStdout "C:\Path\To\lotbook\data\logs\api.log"
nssm set LotbookApi AppStderr "C:\Path\To\lotbook\data\logs\api.log"
```

3) Start the service:

```powershell
nssm start LotbookApi
```

## Linux (systemd)

Create `/etc/systemd/system/lotbook-api.service`:

```ini
[Unit]
Description=LOTBOOK API Service
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/lotbook
ExecStart=/usr/bin/python3 -m uvicorn web_api.app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
Environment=LOTBOOK_WEB_API_KEY=change_me

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable lotbook-api
sudo systemctl start lotbook-api
```

## macOS (launchd)

Create `~/Library/LaunchAgents/com.seperet.lotbook-api.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.seperet.lotbook-api</string>
    <key>ProgramArguments</key>
    <array>
      <string>/usr/bin/python3</string>
      <string>-m</string>
      <string>uvicorn</string>
      <string>web_api.app:app</string>
      <string>--host</string>
      <string>127.0.0.1</string>
      <string>--port</string>
      <string>8000</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/you/code/lotbook</string>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/you/code/lotbook/data/logs/api.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/you/code/lotbook/data/logs/api.log</string>
  </dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.seperet.lotbook-api.plist
```
