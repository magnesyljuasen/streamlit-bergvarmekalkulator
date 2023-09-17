#!/bin/bash

echo "[theme]
primaryColor=\"#383838\"
backgroundColor=\"#fff\"
secondaryBackgroundColor=\"#e5ecf2\"
textColor=\"#383838\"
font=\"sans serif\"

[server] 
headless = true
port = 8501
enableCORS = true 
baseUrlPath = \"/bergvarme-kalk\"

[browser]
serverAddress = \"www.varmepumpeinfo.no\"
gatherUsageStats = false
" > .streamlit/config.toml

sudo podman build -t bergvarme:latest .

sudo systemctl stop bergvarme
sudo podman ps
sudo systemctl start bergvarme