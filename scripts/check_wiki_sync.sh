#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
wiki_dir="${HOMESRVCTL_WIKI_DIR:-$repo_root/../homesrvctl.wiki}"

cd "$repo_root"

if [[ ! -d "$wiki_dir/.git" ]]; then
  echo "wiki check skipped: sibling wiki checkout not found at $wiki_dir"
  echo "clone it with: git clone git@github.com:Broda/homesrvctl.wiki.git \"$wiki_dir\""
  exit 0
fi

mapfile -t changed_repo_files < <(
  {
    git diff --name-only
    git diff --cached --name-only
    git ls-files --others --exclude-standard
  } | sort -u
)

if [[ "${#changed_repo_files[@]}" -eq 0 ]]; then
  echo "wiki check ok: no local repo changes detected"
  exit 0
fi

needs_wiki_update=0
for path in "${changed_repo_files[@]}"; do
  case "$path" in
    README.md|CHANGELOG.md)
      needs_wiki_update=1
      ;;
    homesrvctl/template_catalog.py|homesrvctl/templates/*|homesrvctl/templates/*/*|homesrvctl/templates/*/*/*|homesrvctl/templates/*/*/*/*)
      needs_wiki_update=1
      ;;
    homesrvctl/commands/*.py|homesrvctl/tui/*.py)
      needs_wiki_update=1
      ;;
  esac
done

if [[ "$needs_wiki_update" -eq 0 ]]; then
  echo "wiki check ok: no user-facing repo surfaces changed"
  exit 0
fi

wiki_status="$(git -C "$wiki_dir" status --porcelain)"
if [[ -n "$wiki_status" ]]; then
  echo "wiki check ok: repo changes that may affect user-facing guidance are paired with wiki changes"
  echo "$wiki_status"
  exit 0
fi

echo "wiki check failed: user-facing repo changes detected, but the sibling wiki checkout is still clean"
echo
echo "repo changes:"
printf '  %s\n' "${changed_repo_files[@]}"
echo
echo "wiki checkout: $wiki_dir"
echo "update the relevant wiki pages in the same slice, or set HOMESRVCTL_WIKI_DIR if your wiki checkout lives elsewhere"
exit 1
