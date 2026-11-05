"""Regenerate assets/app.ico used by the Windows executable."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets"


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = max(1, size // 16)
    radius = max(4, size // 5)
    bg = (15, 107, 92, 255)
    x0, y0, x1, y1 = margin, margin, size - margin - 1, size - margin - 1
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=bg)

    card_m = size * 0.22
    draw.rounded_rectangle(
        [card_m, size * 0.18, size - card_m, size * 0.72],
        radius=max(2, size // 14),
        fill=(255, 253, 248, 255),
    )
    draw.rounded_rectangle(
        [size * 0.28, size * 0.78, size * 0.72, size * 0.88],
        radius=max(2, size // 20),
        fill=(216, 240, 234, 255),
    )

    try:
        font = ImageFont.truetype("segoeui.ttf", max(10, size // 3))
    except OSError:
        try:
            font = ImageFont.truetype("arial.ttf", max(10, size // 3))
        except OSError:
            font = ImageFont.load_default()

    text = "$"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    _ = th
    tx = (size - tw) / 2 - bbox[0]
    ty = size * 0.30 - bbox[1]
    draw.text((tx, ty), text, fill=(15, 107, 92, 255), font=font)
    return img


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [make_icon(size) for size in sizes]
    ico_path = OUT_DIR / "app.ico"
    images[-1].save(ico_path, format="ICO", sizes=[(size, size) for size in sizes])
    make_icon(256).save(OUT_DIR / "app.png", format="PNG")
    print(f"Wrote {ico_path}")


if __name__ == "__main__":
    main()
