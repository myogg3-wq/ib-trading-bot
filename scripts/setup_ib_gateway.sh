#!/bin/bash
# ============================================
# IB Gateway + IBC (IB Controller) Auto-Install
# Run on VPS after initial setup
# ============================================

set -e

echo "=== IB Gateway + IBC Installation ==="

# --- Variables ---
IBC_VERSION="3.18.0"
IB_GATEWAY_VERSION="10.30"  # Update to latest stable
INSTALL_DIR="$HOME/ibc"
IB_DIR="$HOME/Jts"

# --- 1. Install prerequisites ---
echo ">>> Installing prerequisites..."
sudo apt-get update
sudo apt-get install -y \
    default-jre \
    xvfb \
    x11vnc \
    unzip \
    wget

# --- 2. Download and install IB Gateway ---
echo ">>> Downloading IB Gateway..."
mkdir -p "$IB_DIR"
cd /tmp

# IB Gateway offline installer
wget -q "https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh" \
    -O ibgateway-installer.sh || {
    echo "Direct download failed. Please download IB Gateway manually from:"
    echo "https://www.interactivebrokers.com/en/trading/ibgateway-stable.php"
    echo "Then run: bash ibgateway-*-linux-x64.sh -q -dir $IB_DIR"
}

if [ -f ibgateway-installer.sh ]; then
    chmod +x ibgateway-installer.sh
    bash ibgateway-installer.sh -q -dir "$IB_DIR"
    echo "IB Gateway installed to $IB_DIR"
fi

# --- 3. Download and install IBC ---
echo ">>> Downloading IBC v${IBC_VERSION}..."
cd /tmp
wget -q "https://github.com/IbcAlpha/IBC/releases/download/${IBC_VERSION}/IBCLinux-${IBC_VERSION}.zip" \
    -O ibc.zip || {
    echo "Download failed. Get latest from: https://github.com/IbcAlpha/IBC/releases"
    exit 1
}

mkdir -p "$INSTALL_DIR"
unzip -o ibc.zip -d "$INSTALL_DIR"
chmod +x "$INSTALL_DIR"/*.sh
rm ibc.zip

echo "IBC installed to $INSTALL_DIR"

# --- 4. Create IBC config ---
echo ">>> Creating IBC configuration..."
mkdir -p "$INSTALL_DIR"

cat > "$INSTALL_DIR/config.ini" << 'EOF'
# IBC Configuration
# See: https://github.com/IbcAlpha/IBC/blob/master/userguide.md

# Login credentials (fill these in!)
IbLoginId=YOUR_IB_USERNAME
IbPassword=YOUR_IB_PASSWORD
TradingMode=paper

# Auto-accept incoming API connections
AcceptIncomingConnectionAction=accept

# Prevent auto-logoff
AcceptNonBrokerageAccountWarning=yes
ExistingSessionDetectedAction=primary

# API Settings
OverrideTwsApiPort=4002
ReadOnlyLogin=no

# Auto-restart
AutoRestartTime=01:00

# Don't close IB Gateway
ClosedownAt=
EOF

echo ""
echo "IMPORTANT: Edit $INSTALL_DIR/config.ini"
echo "Fill in IbLoginId and IbPassword"

# --- 5. Create startup script ---
cat > "$HOME/start_ib_gateway.sh" << EOF
#!/bin/bash
# Start IB Gateway with IBC and virtual display

export DISPLAY=:1

# Start virtual display (for headless server)
Xvfb :1 -screen 0 1024x768x24 &
sleep 2

# Start IBC with IB Gateway
cd $INSTALL_DIR
bash gatewaystart.sh -inline \\
    --gateway \\
    --mode=paper \\
    --tws-path=$IB_DIR \\
    --ibc-path=$INSTALL_DIR \\
    --ibc-ini=$INSTALL_DIR/config.ini
EOF

chmod +x "$HOME/start_ib_gateway.sh"

# --- 6. Create systemd service ---
echo ">>> Creating systemd service..."
sudo cat > /tmp/ib-gateway.service << EOF
[Unit]
Description=IB Gateway with IBC
After=network.target

[Service]
Type=simple
User=$USER
ExecStart=$HOME/start_ib_gateway.sh
Restart=always
RestartSec=30
Environment=DISPLAY=:1

[Install]
WantedBy=multi-user.target
EOF

sudo mv /tmp/ib-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ib-gateway

echo ""
echo "=== IB Gateway + IBC Installation Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit IBC config:  nano $INSTALL_DIR/config.ini"
echo "   - Set IbLoginId=YOUR_USERNAME"
echo "   - Set IbPassword=YOUR_PASSWORD"
echo "   - Set TradingMode=paper (or live)"
echo ""
echo "2. Start IB Gateway:"
echo "   sudo systemctl start ib-gateway"
echo ""
echo "3. Check status:"
echo "   sudo systemctl status ib-gateway"
echo ""
echo "4. View logs:"
echo "   journalctl -u ib-gateway -f"
echo ""
echo "5. For VNC access (to see IB Gateway UI):"
echo "   x11vnc -display :1 -rfbport 5900 -passwd your_vnc_password"
echo "   Then connect with VNC viewer to your_vps_ip:5900"
