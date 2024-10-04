#!/usr/bin/env python3
# domain-sort.py
# Thanks to Server Fault user @aculich https://serverfault.com/a/364372
from fileinput import input

for y in sorted([x.strip().split(".")[::-1] for x in input()]):
    print(".".join(y[::-1]))  # noqa T201
