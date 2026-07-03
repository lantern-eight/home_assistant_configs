#!/usr/bin/env python3
"""Generate JPEG thumbnails for theme background images on Home Assistant."""

from __future__ import annotations

import sys
from pathlib import Path

SOURCE_DIR = Path('/config/www/themes/backgrounds')
THUMB_DIR = SOURCE_DIR / 'thumbs'
THUMB_WIDTH = 300
THUMB_QUALITY = 80
IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp'}


def _is_image(path: Path) -> bool:
  return path.suffix.lower() in IMAGE_SUFFIXES


def main() -> int:
  try:
    from PIL import Image
  except ImportError:
    print('Pillow is required: pip install Pillow', file=sys.stderr)
    return 1

  THUMB_DIR.mkdir(parents=True, exist_ok=True)

  sources = {
    p.name: p
    for p in SOURCE_DIR.iterdir()
    if p.is_file() and _is_image(p)
  }

  for name, source in sources.items():
    thumb_path = THUMB_DIR / f'{Path(name).stem}.jpg'
    if thumb_path.exists():
      continue
    with Image.open(source) as img:
      img = img.convert('RGB')
      w, h = img.size
      if w > THUMB_WIDTH:
        h = max(1, round(h * THUMB_WIDTH / w))
        img = img.resize((THUMB_WIDTH, h), Image.Resampling.LANCZOS)
      img.save(thumb_path, 'JPEG', quality=THUMB_QUALITY, optimize=True)
    print(f'created {thumb_path.name}')

  for thumb in THUMB_DIR.glob('*.jpg'):
    stem = thumb.stem
    if not any(Path(name).stem == stem for name in sources):
      thumb.unlink()
      print(f'removed orphan {thumb.name}')

  return 0


if __name__ == '__main__':
  raise SystemExit(main())
