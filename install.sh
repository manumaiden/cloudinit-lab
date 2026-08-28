#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/bin"
TARGET="$BIN_DIR/cloudinit-lab"

mkdir -p "$BIN_DIR"

if [ -L "$TARGET" ] || [ -e "$TARGET" ]; then
    echo "Removing existing $TARGET"
    rm -f "$TARGET"
fi

ln -s "$SCRIPT_DIR/cloudinit-lab.py" "$TARGET"
chmod +x "$SCRIPT_DIR/cloudinit-lab.py"
echo "Symlinked $TARGET -> $SCRIPT_DIR/cloudinit-lab.py"

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    RC_FILE="$HOME/.bashrc"
    [ -n "${ZSH_VERSION:-}" ] && RC_FILE="$HOME/.zshrc"
    echo "export PATH=\"\$HOME/bin:\$PATH\"" >> "$RC_FILE"
    echo "Added $BIN_DIR to PATH in $RC_FILE — run 'source $RC_FILE' or open a new shell"
fi

USER_CONFIG="$HOME/.cloudinit-lab.conf"
if [ ! -f "$USER_CONFIG" ]; then
    cp "$SCRIPT_DIR/configs/lab.conf" "$USER_CONFIG"
    echo "Copied default config to $USER_CONFIG"
else
    echo "$USER_CONFIG already exists, leaving it untouched"
fi

echo ""
echo "Install dependencies with:"
echo "  pip install -r $SCRIPT_DIR/requirements.txt"
echo ""
echo "Done. Run 'cloudinit-lab' to get started."
