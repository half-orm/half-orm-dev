#!/bin/bash
cd hop_release_ordering

echo "=== TOML files in .hop/releases ==="
ls -la .hop/releases/*.toml 2>/dev/null || echo "No TOML files found"

echo ""
echo "=== Content of TOML files ==="
for f in .hop/releases/*.toml; do
    if [ -f "$f" ]; then
        echo "--- $f ---"
        cat "$f"
    fi
done

echo ""
echo "=== Checking if propagation message appeared ==="
echo "Look for messages like '• Propagating to ho-release/0.1.0...' in the merge output above"
