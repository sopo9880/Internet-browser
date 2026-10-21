"""Generate native Windows product artwork from the existing parcel logo."""
from __future__ import annotations

import io
from pathlib import Path

THEME = 'chrome/app/theme/'
PNG_PATHS = tuple(
    [THEME + f'chromium/product_logo_{size}.png' for size in (16, 24, 48, 64, 128, 256)] +
    [THEME + 'chromium/product_logo_22_mono.png'] +
    [THEME + f'default_{scale}_percent/chromium/{name}.png'
     for scale in (100, 200)
     for name in ('product_logo_16', 'product_logo_32', 'product_logo_name_22',
                  'product_logo_name_22_white')] +
    [f'components/resources/default_{scale}_percent/chromium/{name}.png'
     for scale in (100, 200) for name in ('product_logo', 'product_logo_white')] +
    [THEME + f'chromium/win/tiles/{name}.png' for name in ('Logo', 'SmallLogo')])
SVG_PATHS = tuple(THEME + f'chromium/{name}.svg'
                  for name in ('product_logo', 'product_logo_animation'))
ICO_PATHS = tuple(THEME + f'chromium/win/{name}.ico'
                  for name in ('chromium', 'app_list'))
ARTWORK_PATHS = frozenset(PNG_PATHS + SVG_PATHS + ICO_PATHS)


def artwork(checkout: Path, root: Path) -> dict[str, bytes]:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    logo = Image.open(root / 'assets/icon/parcel.png').convert('RGBA')
    result = {}
    # Do not silently skip an upstream rename: all expected resources must exist.
    for relative in sorted(ARTWORK_PATHS):
        if not (checkout / relative).is_file():
            raise ValueError('Pinned Windows artwork path changed: ' + relative)
    for relative in PNG_PATHS:
        with Image.open(checkout / relative) as upstream:
            size = upstream.size
        canvas = Image.new('RGBA', size, (0, 0, 0, 0))
        if 'product_logo_name_' in relative:
            # Keep the resource's layout size, with no dependency on host fonts.
            large = Image.new('RGBA', (size[0] * 4, size[1] * 4), (0, 0, 0, 0))
            draw = ImageDraw.Draw(large)
            text = 'Internet Browser'
            font_size = large.height
            while font_size > 1:
                font = ImageFont.load_default(size=font_size)
                box = draw.textbbox((0, 0), text, font=font)
                if box[2] - box[0] <= large.width and box[3] - box[1] <= large.height:
                    break
                font_size -= 1
            x = (large.width - (box[2] - box[0])) // 2 - box[0]
            y = (large.height - (box[3] - box[1])) // 2 - box[1]
            draw.text((x, y), text, font=font,
                      fill='white' if '_white.' in relative else '#202124')
            canvas = large.resize(size, Image.Resampling.LANCZOS)
        else:
            image = logo.copy()
            if '_mono.' in relative or '_white.' in relative:
                alpha = ImageOps.grayscale(image)
                image = Image.new('RGBA', image.size, 'white')
                image.putalpha(alpha)
            image = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
            canvas.alpha_composite(image, ((size[0] - image.width) // 2,
                                           (size[1] - image.height) // 2))
        output = io.BytesIO()
        canvas.save(output, format='PNG')
        result[relative] = output.getvalue()
    for relative in SVG_PATHS:
        result[relative] = (root / 'assets/icon/parcel.svg').read_bytes()
    output = io.BytesIO()
    logo.save(output, format='ICO', sizes=[(16, 16), (24, 24), (32, 32),
                                         (48, 48), (64, 64), (128, 128), (256, 256)])
    for relative in ICO_PATHS:
        result[relative] = output.getvalue()
    return result
