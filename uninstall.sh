#!/usr/bin/env bash

# 1. Ask if the user wants to uninstall (y/N)
read -p "  Are you sure you want to uninstall pacfz? (y/N): " response

# Convert response to lowercase and check it
case "$response" in
    [yY][eE][sS]|[yY])
        echo "Stopping and removing files..."

        # 2. Remove the files that were copied into bin
        rm -f "$HOME/.local/bin/pacfz"
        rm -f "$HOME/.local/bin/pacq"
        echo "• Removed binaries from .local/bin"

        # 3. Remove the whole folder pacfz in share
        if [ -d "$HOME/.local/share/pacfz" ]; then
            rm -rf "$HOME/.local/share/pacfz"
            echo "• Removed shared folder .local/share/pacfz"
        fi

        # 4. Remove .cache/pacman_packages.db
        if [ -f "$HOME/.cache/pacman_packages.db" ]; then
            rm -f "$HOME/.cache/pacman_packages.db"
            echo "• Removed cache database"
        fi

        echo "✔ Uninstallation complete!"
        ;;
    *)
        echo "✘ Uninstallation canceled."
        exit 0
        ;;
esac
