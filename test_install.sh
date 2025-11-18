#!/bin/bash
# Test script to validate install.sh without making system changes

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SCRIPT="$SCRIPT_DIR/install.sh"

echo "Testing installation script..."
echo "=============================="
echo ""

# Test 1: Check if script exists and is executable
echo "Test 1: Checking script exists and is executable..."
if [ ! -f "$INSTALL_SCRIPT" ]; then
    echo "❌ FAIL: install.sh not found"
    exit 1
fi

if [ ! -x "$INSTALL_SCRIPT" ]; then
    echo "❌ FAIL: install.sh is not executable"
    exit 1
fi
echo "✅ PASS: Script exists and is executable"
echo ""

# Test 2: Check syntax
echo "Test 2: Checking bash syntax..."
if bash -n "$INSTALL_SCRIPT" 2>&1; then
    echo "✅ PASS: Syntax is valid"
else
    echo "❌ FAIL: Syntax errors found"
    exit 1
fi
echo ""

# Test 3: Check required files exist
echo "Test 3: Checking required files exist..."
REQUIRED_FILES=(
    "player.py"
    "cli.py"
    "music-player.service"
    "sources.json.example"
    "spotifyd.conf.example"
)

MISSING_FILES=()
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$SCRIPT_DIR/$file" ]; then
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -eq 0 ]; then
    echo "✅ PASS: All required files present"
else
    echo "❌ FAIL: Missing files: ${MISSING_FILES[*]}"
    exit 1
fi
echo ""

# Test 4: Check script structure (basic validation)
echo "Test 4: Validating script structure..."
if grep -q "set -euo pipefail" "$INSTALL_SCRIPT"; then
    echo "✅ PASS: Script uses strict error handling"
else
    echo "⚠️  WARN: Script doesn't use 'set -euo pipefail'"
fi

if grep -q "main()" "$INSTALL_SCRIPT"; then
    echo "✅ PASS: Script has main function"
else
    echo "⚠️  WARN: Script doesn't have main function"
fi

if grep -q "systemctl" "$INSTALL_SCRIPT"; then
    echo "✅ PASS: Script includes systemd service installation"
else
    echo "⚠️  WARN: Script doesn't include systemd service installation"
fi
echo ""

# Test 5: Check for common bash pitfalls
echo "Test 5: Checking for common issues..."
ISSUES=0

# Check for unquoted variables (basic check)
if grep -E '\$[A-Z_]+[^"]' "$INSTALL_SCRIPT" | grep -vE '(echo|print_|RED|GREEN|YELLOW|NC)' | head -1; then
    echo "⚠️  WARN: Potential unquoted variables found"
    ISSUES=$((ISSUES + 1))
fi

# Check for proper error handling
if ! grep -q "set -e" "$INSTALL_SCRIPT"; then
    echo "⚠️  WARN: Script may not exit on errors"
    ISSUES=$((ISSUES + 1))
fi

if [ $ISSUES -eq 0 ]; then
    echo "✅ PASS: No obvious issues found"
fi
echo ""

# Test 6: Validate service file exists and is readable
echo "Test 6: Validating service file..."
if [ -f "$SCRIPT_DIR/music-player.service" ]; then
    if grep -q "\[Unit\]" "$SCRIPT_DIR/music-player.service" && \
       grep -q "\[Service\]" "$SCRIPT_DIR/music-player.service" && \
       grep -q "\[Install\]" "$SCRIPT_DIR/music-player.service"; then
        echo "✅ PASS: Service file has valid structure"
    else
        echo "⚠️  WARN: Service file may be malformed"
    fi
else
    echo "❌ FAIL: Service file not found"
    exit 1
fi
echo ""

echo "=============================="
echo "✅ All tests passed!"
echo ""
echo "The installation script appears to be valid."
echo "You can now run: ./install.sh"
echo ""

