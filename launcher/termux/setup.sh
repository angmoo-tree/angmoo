#!/bin/sh
set -eu
# Run from the reviewed release's extracted launcher/termux directory.
# No pipe-to-shell download and no system-wide upgrade on application start.
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! command -v python >/dev/null || ! command -v proot >/dev/null; then
  if command -v pkg >/dev/null; then
    pkg install python proot
  else
    echo 'Install Python 3 and proot first. / 먼저 Python 3과 proot을 설치하세요.' >&2
    exit 1
  fi
fi
tools="$HOME/.local/share/angmoo-tools"
mkdir -p "$HOME/.local/bin" "$tools"
if [ ! -x "$tools/venv/bin/python" ]; then
  python -m venv "$tools/venv"
fi
"$tools/venv/bin/python" -m pip install --require-hashes --only-binary=:all: --no-deps -r "$here/requirements.txt"
for file in angmoo.py payload.py processes.py service_logs.py requirements.txt; do
  cp "$here/$file" "$tools/$file"
done
if [ -f "$here/LICENSE" ]; then
  cp "$here/LICENSE" "$tools/LICENSE"
fi
cat > "$HOME/.local/bin/angmoo" <<'SH'
#!/bin/sh
PATH="$HOME/.local/share/angmoo-tools/venv/bin:$PATH"
export PATH
exec "$HOME/.local/share/angmoo-tools/venv/bin/python" "$HOME/.local/share/angmoo-tools/angmoo.py" "$@"
SH
chmod 0755 "$HOME/.local/bin/angmoo"
printf '%s\n' 'Setup complete. / 최초 준비 완료.' \
  '~/.local/bin/angmoo install --release 0.1.0' '~/.local/bin/angmoo start'
