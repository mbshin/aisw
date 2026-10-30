#!/usr/bin/env bash
# BROWSER for `claude auth login` (set by aisw login): open the sign-in page in a new, empty Chrome
# profile, so no existing Claude login (normal or Incognito windows) is reused for the wrong account.
url=$1
if [ -d "/Applications/Google Chrome.app" ]; then
  dir=$(mktemp -d "${TMPDIR:-/tmp}/aisw-login.XXXXXX")
  open -na "Google Chrome" --args --user-data-dir="$dir" --no-first-run --no-default-browser-check "$url"
else
  open "$url"
fi
