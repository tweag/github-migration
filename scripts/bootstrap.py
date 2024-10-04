#!/usr/bin/env python3
# bootstrap.py
#
# Functions used to bootstrap scripts
# Do not use any dependencies from pip here.
import sys


# Thanks https://stackoverflow.com/a/1883251 for the hint on reliably
# determining whether you are in a virtualenv
def get_base_prefix_compat():
    """Get base/real prefix, or sys.prefix if there is none."""
    return (
        getattr(sys, "base_prefix", None)
        or getattr(sys, "real_prefix", None)
        or sys.prefix
    )


def in_virtualenv():
    return sys.prefix != get_base_prefix_compat()
