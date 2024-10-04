#!/usr/bin/env python3
import sys

from bootstrap import in_virtualenv

if in_virtualenv():
    sys.exit(0)
else:
    sys.exit(1)
