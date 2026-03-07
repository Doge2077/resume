#!/usr/bin/env bash
set -e

if [ $# -lt 1 ]; then
echo "Usage:"
echo "  sh build.sh <tex-file>"
exit 1
fi

INPUT="$1"

# Convert Windows path -> POSIX path if needed

if command -v cygpath >/dev/null 2>&1; then
INPUT=$(cygpath -u "$INPUT")
fi

if [ ! -f "$INPUT" ]; then
echo "File not found: $INPUT"
exit 1
fi

DIR=$(dirname "$INPUT")
BASE=$(basename "$INPUT" .tex)

# locate xelatex

if command -v xelatex >/dev/null 2>&1; then
XELATEX="xelatex"
else
MIKTEX="/c/Users/LYS/AppData/Local/Programs/MiKTeX/miktex/bin/x64/xelatex.exe"
if [ -f "$MIKTEX" ]; then
XELATEX="$MIKTEX"
else
echo "xelatex not found."
exit 1
fi
fi

echo "Compiling $INPUT"
echo "Output directory: $DIR"

"$XELATEX" -interaction=nonstopmode -output-directory="$DIR" "$INPUT"
"$XELATEX" -interaction=nonstopmode -output-directory="$DIR" "$INPUT"

echo "PDF generated:"
echo "$DIR/$BASE.pdf"
