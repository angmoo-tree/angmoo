#!/bin/sh
set -eu
# Run from the reviewed release's extracted launcher/termux directory.
# No pipe-to-shell download and no system-wide upgrade on application start.
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "$#:$*" in
  0:) mode=setup ;;
  1:--register-command-only) mode=register-only ;;
  *) echo 'Usage: sh setup.sh [--register-command-only]' >&2; exit 2 ;;
esac
if ! command -v python >/dev/null; then
  if [ "$mode" = setup ] && command -v pkg >/dev/null; then
    pkg install python
  else
    echo 'Install Python 3 first; no command was registered.' >&2
    exit 1
  fi
fi
exec python "$here/command_registration.py" "$mode"
