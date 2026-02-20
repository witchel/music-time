#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["requests"]
# ///
"""Allow running as: uv run python -m gdtimings"""
from gdtimings.cli import main

main()
