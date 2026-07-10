#!/bin/zsh
set -e
cd "$(dirname "$0")"
mkdir -p build docx
for md in [0-9][0-9]-*.md; do
  base="${md%.md}"
  echo "  building $base ..."
  mmdc -i "$md" -o "build/$base.md" -e png -c mermaid-config.json -p puppeteer.json >/dev/null 2>&1 || cp "$md" "build/$base.md"
  ( cd build && pandoc "$base.md" -o "../docx/$base.docx" \
      --reference-doc=../reference.docx --toc --toc-depth=2 \
      --resource-path=. --metadata title="Lucidate / Horizon Assessment" 2>/dev/null )
done
echo "built $(ls docx/*.docx 2>/dev/null | wc -l | tr -d ' ') docx files"
