#!/usr/bin/env python3
"""List theme background image files as JSON for the command_line sensor."""

import json
import os
from pathlib import Path

SOURCE_DIR = Path('/config/www/themes/backgrounds')
IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp'}


def main() -> None:
    files = sorted(
        f.name
        for f in SOURCE_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES
    )
    print(json.dumps({'count': len(files), 'file_list': files}))


if __name__ == '__main__':
    main()
