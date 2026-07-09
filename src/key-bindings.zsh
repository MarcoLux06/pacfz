# pacfz key bindings for zsh.
#
# Source this from your .zshrc:
#
#   source /usr/share/pacfz/key-bindings.zsh
#
# Binds ctrl+p to launch the exact same interactive session pacfz itself
# gives you (fuzzy search, live colorized preview pane, ctrl-r to rebuild
# the cache) - the only difference is what happens when you actually pick
# a package: instead of printing a final rendered preview and exiting,
# the selected package's name is inserted at your cursor, so you can
# follow it with e.g. "pacman -R " + the name it just inserted.
#
# Modeled on fzf's own key-bindings.zsh (CTRL-T / CTRL-R), which registers
# a ZLE (Zsh Line Editor) widget and binds a key sequence to it - zsh's
# equivalent of bash's `bind -x`.

__pacfz_select_package() {
  local selected
  selected="$(pacfz --print-selection </dev/tty)"
  if [[ -n "$selected" ]]; then
    LBUFFER="${LBUFFER}${selected}"
  fi
  zle reset-prompt
}

zle -N __pacfz_select_package
bindkey '^P' __pacfz_select_package
