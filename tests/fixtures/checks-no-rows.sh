#!/bin/sh
# A checks CLI whose `practices --json` parses and holds no row. The real tool
# refuses an empty registry (exit 2), so tests/test_practices.py reaches the
# brief's own empty-rows guard only through this: none read is UNCHECKED, never
# "no prose row applies".
cat >/dev/null
printf '{"rows": []}\n'
