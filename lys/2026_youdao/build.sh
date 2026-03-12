#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)

find_xelatex() {
  if command -v xelatex >/dev/null 2>&1; then
    printf '%s\n' "xelatex"
    return 0
  fi

  MIKTEX="/c/Users/LYS/AppData/Local/Programs/MiKTeX/miktex/bin/x64/xelatex.exe"
  if [ -f "$MIKTEX" ]; then
    printf '%s\n' "$MIKTEX"
    return 0
  fi

  echo "xelatex not found."
  exit 1
}

XELATEX=$(find_xelatex)

if [ "$#" -gt 1 ]; then
  echo "Usage: sh build.sh [tex-file]"
  exit 1
fi

if [ "$#" -eq 1 ]; then
  INPUT_ARG=$1
else
  INPUT_ARG="$SCRIPT_DIR/resume.tex"
fi

if command -v cygpath >/dev/null 2>&1; then
  INPUT_PATH=$(cygpath -u "$INPUT_ARG")
else
  INPUT_PATH=$INPUT_ARG
fi

case "$INPUT_PATH" in
  /*) ;;
  *) INPUT_PATH="$SCRIPT_DIR/$INPUT_PATH" ;;
esac

if [ ! -f "$INPUT_PATH" ]; then
  echo "File not found: $INPUT_PATH"
  exit 1
fi

INPUT_ABS=$(CDPATH= cd -- "$(dirname -- "$INPUT_PATH")" && pwd)/$(basename -- "$INPUT_PATH")

case "$INPUT_ABS" in
  "$REPO_ROOT"/*) INPUT_REL=${INPUT_ABS#"$REPO_ROOT"/} ;;
  *)
    echo "Input must be inside repository: $INPUT_ABS"
    exit 1
    ;;
esac

OUTPUT_DIR=$(dirname "$INPUT_REL")

echo "Compiling $INPUT_REL"
echo "Output directory: $OUTPUT_DIR"

oldpwd=$(pwd)
cd "$REPO_ROOT"
"$XELATEX" -interaction=nonstopmode -output-directory="$OUTPUT_DIR" "$INPUT_REL"
"$XELATEX" -interaction=nonstopmode -output-directory="$OUTPUT_DIR" "$INPUT_REL"
cd "$oldpwd"

echo "PDF generated:"
echo "$REPO_ROOT/$OUTPUT_DIR/$(basename "$INPUT_REL" .tex).pdf"
