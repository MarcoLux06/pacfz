#!/usr/bin/env bash
# Exit on unexpected errors, but allow interactive prompts to pass
set -e

BIN_DEST="$HOME/.local/bin"
SHARE_DEST="$HOME/.local/share/pacfz"

echo "Starting installation..."

# 1. Create the folders if they don't exist
mkdir -p "$BIN_DEST"
mkdir -p "$SHARE_DEST"

# 2. Copy binaries and ASK before overwriting (-i flag)
echo " Installing executables to $BIN_DEST..."
cp -i bin/pacfz bin/pacq "$BIN_DEST/"

# Ensure the binaries have execution permissions
chmod +x "$BIN_DEST/pacfz" "$BIN_DEST/pacq"

# 3. Copy Python support files and ASK before overwriting (-i flag)
echo " Installing support files to $SHARE_DEST..."
cp -i share/pacfz/* "$SHARE_DEST/"

echo "✔ Installation finished successfully!"
