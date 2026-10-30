#!/usr/bin/env bash
# BROWSER for sign-ins started by aisw: open the sign-in page in a new, empty Chrome profile in
# Incognito, so no existing login is reused for the wrong account (all Incognito windows of the normal
# profile share one session) and nothing is kept. aisw deletes the profile afterwards.
url=$1
if [ -d "/Applications/Google Chrome.app" ]; then
  dir=$(mktemp -d "${TMPDIR:-/tmp}/aisw-login.XXXXXX")
  open -na "Google Chrome" --args --user-data-dir="$dir" --incognito --no-first-run --no-default-browser-check "$url"
else
  open "$url"
fi
