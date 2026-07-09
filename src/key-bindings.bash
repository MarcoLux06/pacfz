# pacfz key bindings for bash.
#
# Source this from your .bashrc:
#
#   source /usr/share/pacfz/key-bindings.bash
#
# Binds ctrl+p to launch the exact same interactive session pacfz itself
# gives you (fuzzy search, live colorized preview pane, ctrl-r to rebuild
# the cache) - the only difference is what happens when you actually pick
# a package: instead of printing a final rendered preview and exiting,
# the selected package's name is inserted at your cursor, so you can
# follow it with e.g. "pacman -R " + the name it just inserted.
#
# Modeled on fzf's own key-bindings.bash (CTRL-T / CTRL-R), which uses the
# same "run a command, capture its stdout, splice it into READLINE_LINE"
# pattern via `bind -x`.

__pacfz_select_package__() {
  local selected
  selected="$(pacfz --print-selection </dev/tty)"
  if [[ -n "$selected" ]]; then
    READLINE_LINE="${READLINE_LINE:0:$READLINE_POINT}${selected}${READLINE_LINE:$READLINE_POINT}"
    READLINE_POINT=$((READLINE_POINT + ${#selected}))
  fi
}

# bind -x runs the given command with READLINE_LINE/READLINE_POINT
# available for it to read and modify; readline splices the updated line
# back in once the command returns. </dev/tty above is needed because
# bind -x's command normally has its stdin/stdout wired to the pipeline
# bind -x itself is invoked from, not your actual terminal - fzf needs a
# real terminal to draw its interface on.
bind -x '"\C-p": __pacfz_select_package__'
