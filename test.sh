#!/usr/bin/env bash
# Run the doormat test suite.
#
# There is nothing to build and nothing to install. The package is ctypes
# against libraries the operating system already has, so the suites run
# against the checkout with whatever python3 is on the PATH.
#
# All three window suites run everywhere. Each opens real windows where its
# platform provides them and skips cleanly where it does not, which is the
# point of running all three on every machine: the two that cannot do
# anything here still have to import, and say why.
#
# On Windows, run `bash test.sh` -- Git for Windows ships one, and there is
# nothing in here that needs anything else.
set -euo pipefail
cd "$(dirname "$0")"

# Those suites open dozens of real windows in a few seconds, and a window's
# default manners -- centre itself, raise above everything, take the keyboard
# -- make the machine unusable for as long as the run lasts. QUIET drops
# exactly those three things: the windows are still created, mapped, drawn
# into and sent real events, so every assertion proves what it proved before.
# Honour an existing value, so `DOORMAT_QUIET=0 ./test.sh` still gets you the
# windows when you want to watch them.
export DOORMAT_QUIET="${DOORMAT_QUIET:-1}"

PY="${PYTHON:-python3}"

# The suites import `doormat` and `tests.support` by name, so the checkout
# has to be importable. Prepending rather than appending, so a doormat that
# happens to be pip-installed on this machine cannot be the one under test.
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"

if ! $PY -c "import pyflakes" 2>/dev/null; then
  echo "note: pyflakes is not installed, skipping the lint" >&2
else
  $PY -m pyflakes doormat tests
fi

$PY tests/test_x11.py     # opens real windows under X11, skips elsewhere
$PY tests/test_cocoa.py   # opens real windows on macOS, skips elsewhere
$PY tests/test_win32.py   # opens real windows on Windows, skips elsewhere
$PY tests/test_asmx11.py  # raw assembly on Linux/x86-64, Python elsewhere

echo
echo "all suites passed"
