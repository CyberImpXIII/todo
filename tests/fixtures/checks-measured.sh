#!/bin/sh
# A checks CLI that answers `practices --rows --json` with the measured run's output
# (rows carrying cells, a ratchet): tests/test_practices.py shows the brief refuses
# it rather than read measured cells as the rows view (PLAN-O27 step 4, td-97).
printf '{"rows": [{"id": "x-y", "part": "B", "status": "live", "held": {"kind": "prose", "text": "t"}, "applies": "all", "cells": {}}], "ratchet": {}, "measured": true}\n'
