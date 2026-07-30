"""Generate the Warhammer-flavored skeeball textures (procedural, no source
art). Outputs to skeeball-frontend/public/tex/ — rebuild the frontend after
running so vite copies them into static/game/tex/.

Run: venv/bin/python scripts/gen_wh_textures.py
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(__file__), "..", "skeeball-frontend",
                   "public", "tex")

rng = np.random.default_rng(40_000)  # in the grim darkness of the far future


def _noise(w, h, scale, lo, hi):
    """Blurred uniform noise upsampled to (w, h), mapped to [lo, hi]."""
    small = rng.random((max(2, h // scale), max(2, w // scale)))
    img = Image.fromarray((small * 255).astype("uint8"), "L").resize(
        (w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(2))
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return lo + arr * (hi - lo)


def _colorize(base_rgb, lum):
    """Stack a luminance map onto an RGB base color."""
    r, g, b = base_rgb
    return np.dstack([
        np.clip(r * lum, 0, 255),
        np.clip(g * lum, 0, 255),
        np.clip(b * lum, 0, 255),
    ]).astype("uint8")


def ball(path, size=1024):
    """Crimson ceremonial orb: mottled deep red, brass latitude bands.
    Horizontal bands read beautifully on a spinning UV sphere."""
    lum = _noise(size, size, 8, 0.72, 1.05)
    img = Image.fromarray(_colorize((150, 26, 30), lum))
    draw = ImageDraw.Draw(img)

    def band(cy, half, color, edge=3):
        draw.rectangle([0, cy - half, size, cy + half], fill=color)
        draw.rectangle([0, cy - half, size, cy - half + edge], fill=(90, 62, 18))
        draw.rectangle([0, cy + half - edge, size, cy + half], fill=(90, 62, 18))

    band(size // 2, 46, (196, 156, 60))          # brass equator
    band(int(size * 0.22), 14, (196, 156, 60))   # thin upper band
    band(int(size * 0.78), 14, (196, 156, 60))   # thin lower band
    # Darkened poles (top/bottom of the UV map) ground the sphere shading.
    arr = np.asarray(img).astype(np.float32)
    ys = np.arange(size)
    pole = np.minimum(ys, size - 1 - ys) / (size * 0.18)
    k = np.where(pole < 1, 0.55 + 0.45 * pole, 1.0)
    arr *= k[:, None, None]
    # Brass studs along the equator band.
    img = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))
    draw = ImageDraw.Draw(img)
    for i in range(16):
        x = int((i + 0.5) * size / 16)
        draw.ellipse([x - 10, size // 2 - 10, x + 10, size // 2 + 10],
                     fill=(228, 196, 104), outline=(90, 62, 18), width=3)
    img.save(path, quality=88)


def lane(path, size=1024, plates=4):
    """Gunmetal deck plating: plate grid + rivets + grime. Tileable — the
    seams sit exactly on the texture edges."""
    lum = _noise(size, size, 6, 0.82, 1.02)
    grime = _noise(size, size, 64, 0.85, 1.0)
    img = Image.fromarray(_colorize((64, 68, 76), lum * grime))
    draw = ImageDraw.Draw(img)
    step = size // plates
    for i in range(plates + 1):
        p = min(i * step, size - 1)
        draw.line([(0, p), (size, p)], fill=(28, 30, 34), width=7)
        draw.line([(p, 0), (p, size)], fill=(28, 30, 34), width=7)
        draw.line([(0, p + 4), (size, p + 4)], fill=(96, 100, 110), width=2)
        draw.line([(p + 4, 0), (p + 4, size)], fill=(96, 100, 110), width=2)
    for gy in range(plates):
        for gx in range(plates):
            for ox, oy in ((28, 28), (step - 28, 28), (28, step - 28),
                           (step - 28, step - 28)):
                x, y = gx * step + ox, gy * step + oy
                draw.ellipse([x - 9, y - 9, x + 9, y + 9],
                             fill=(30, 32, 36), outline=(110, 114, 124), width=2)
                draw.ellipse([x - 5, y - 5, x + 2, y + 2], fill=(140, 144, 154))
    # Scratches
    for _ in range(60):
        x, y = rng.integers(0, size, 2)
        dx, dy = rng.integers(-90, 90, 2)
        draw.line([(x, y), (x + dx, y + dy)], fill=(100, 104, 112), width=1)
    img.save(path, quality=88)


def space(path, w=2048, h=1024):
    """Equirectangular nebula sky, warm ember tones. Generated on a half
    canvas and mirrored so the left/right edges meet seamlessly."""
    half = w // 2
    base = np.zeros((h, half, 3), dtype=np.float32)
    base[..., 0] = 10
    base[..., 1] = 8
    base[..., 2] = 18

    nebula = Image.new("RGB", (half, h), (0, 0, 0))
    nd = ImageDraw.Draw(nebula)
    palette = [(120, 30, 24), (150, 70, 20), (60, 24, 70), (24, 40, 80)]
    for _ in range(90):
        x = int(rng.integers(0, half))
        y = int(rng.integers(int(h * 0.15), int(h * 0.85)))
        r = int(rng.integers(40, 190))
        color = palette[int(rng.integers(len(palette)))]
        nd.ellipse([x - r, y - r, x + r, y + r], fill=color)
    nebula = nebula.filter(ImageFilter.GaussianBlur(60))
    arr = base + np.asarray(nebula, dtype=np.float32) * 0.55

    img = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))
    draw = ImageDraw.Draw(img)
    for _ in range(700):  # stars, brighter toward the galactic band
        x = int(rng.integers(0, half))
        y = int(rng.integers(0, h))
        b = int(rng.integers(90, 255))
        warm = rng.random() < 0.25
        c = (b, int(b * 0.82), int(b * 0.5)) if warm else (b, b, min(255, b + 20))
        r = 2 if rng.random() < 0.06 else 1
        draw.ellipse([x - r, y - r, x + r, y + r], fill=c)

    full = Image.new("RGB", (w, h))
    full.paste(img, (0, 0))
    full.paste(img.transpose(Image.FLIP_LEFT_RIGHT), (half, 0))
    full.save(path, quality=85)


def _face_base(size=1024):
    """Shared HORUS head: big bald bronze dome on transparency."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = size // 2
    # head + jaw
    d.ellipse([cx - 400, 60, cx + 400, 900], fill=(196, 152, 92, 255),
              outline=(94, 66, 30, 255), width=10)
    # dome shading + bald shine
    d.ellipse([cx - 320, 90, cx + 340, 420], fill=(214, 172, 112, 255))
    d.ellipse([cx + 90, 120, cx + 260, 230], fill=(240, 214, 168, 255))
    # ears
    for side in (-1, 1):
        d.ellipse([cx + side * 400 - 48, 420, cx + side * 400 + 48, 560],
                  fill=(186, 140, 82, 255), outline=(94, 66, 30, 255), width=8)
    # eye of horus mark (teal, under left eye)
    d.arc([cx - 300, 560, cx - 120, 660], 20, 160, fill=(20, 160, 170, 255), width=10)
    d.line([cx - 210, 645, cx - 240, 720], fill=(20, 160, 170, 255), width=10)
    return img, d, cx


def _face_angry_eyes(d, cx, black_eye=None):
    """Glaring eyes + heavy inward-slanted brows. black_eye: None|'r'|'both'."""
    for side in (-1, 1):
        ex = cx + side * 190
        bruised = black_eye == "both" or (black_eye == "r" and side == 1)
        if bruised:
            d.ellipse([ex - 120, 380, ex + 120, 560], fill=(96, 62, 120, 255))
        d.ellipse([ex - 95, 415, ex + 95, 535], fill=(245, 240, 228, 255),
                  outline=(70, 50, 30, 255), width=6)
        d.ellipse([ex - 34, 445 if not bruised else 470, ex + 34,
                   515 if not bruised else 540], fill=(120, 30, 20, 255))
        d.ellipse([ex - 12, 460 if not bruised else 485, ex + 12,
                   490 if not bruised else 515], fill=(20, 10, 8, 255))
        # brow: thick wedge slanting toward the nose
        brow = ([ (ex - 130, 330), (ex + 120, 400), (ex + 120, 452), (ex - 130, 392) ]
                if side == 1 else
                [ (ex + 130, 330), (ex - 120, 400), (ex - 120, 452), (ex + 130, 392) ])
        d.polygon(brow, fill=(60, 40, 22, 255))


def _face_frown(d, cx, cracked=False):
    """Gritted-teeth grimace."""
    d.rounded_rectangle([cx - 190, 700, cx + 190, 800], 40,
                        fill=(70, 30, 24, 255), outline=(70, 50, 30, 255), width=8)
    for i in range(5):
        x0 = cx - 170 + i * 68
        missing = cracked and i == 2
        if not missing:
            d.rounded_rectangle([x0, 712, x0 + 60, 788], 12, fill=(235, 228, 210, 255))
    # downturned mouth corners
    d.arc([cx - 260, 640, cx - 120, 760], 300, 40, fill=(70, 50, 30, 255), width=12)
    d.arc([cx + 120, 640, cx + 260, 760], 140, 240, fill=(70, 50, 30, 255), width=12)


def _bandaid(d, x, y, angle_deg=30):
    """Crossed band-aid strips."""
    import math
    for a in (angle_deg, angle_deg + 90):
        rad = math.radians(a)
        dx, dy = math.cos(rad) * 80, math.sin(rad) * 80
        px, py = math.cos(rad + 1.5708) * 18, math.sin(rad + 1.5708) * 18
        d.polygon([(x - dx - px, y - dy - py), (x + dx - px, y + dy - py),
                   (x + dx + px, y + dy + py), (x - dx + px, y - dy + py)],
                  fill=(226, 200, 160, 255), outline=(150, 120, 80, 255))


def horus_faces(out_dir, size=1024):
    """HORUS boss faces: fresh / bruised / battered / laughing. RGBA PNGs so
    the in-game plane keeps the head silhouette."""
    # stage 0 — furious and pristine
    img, d, cx = _face_base(size)
    _face_angry_eyes(d, cx)
    _face_frown(d, cx)
    img.save(os.path.join(out_dir, "horus_face_0.png"))

    # stage 1 — black eye, cheek bruise, forehead band-aid
    img, d, cx = _face_base(size)
    d.ellipse([cx - 330, 600, cx - 150, 730], fill=(110, 70, 140, 160))
    _face_angry_eyes(d, cx, black_eye="r")
    _face_frown(d, cx)
    _bandaid(d, cx - 120, 200)
    img.save(os.path.join(out_dir, "horus_face_1.png"))

    # stage 2 — both eyes, green+purple bruises, missing tooth, swollen jaw
    img, d, cx = _face_base(size)
    d.ellipse([cx - 350, 580, cx - 140, 740], fill=(110, 70, 140, 170))
    d.ellipse([cx + 140, 610, cx + 350, 760], fill=(90, 130, 70, 160))
    d.ellipse([cx - 90, 130, cx + 120, 260], fill=(120, 80, 150, 140))
    _face_angry_eyes(d, cx, black_eye="both")
    _face_frown(d, cx, cracked=True)
    _bandaid(d, cx - 130, 195)
    _bandaid(d, cx + 240, 330, angle_deg=70)
    img.save(os.path.join(out_dir, "horus_face_2.png"))

    # laugh — closed happy eyes, huge open mouth: the mockery face
    img, d, cx = _face_base(size)
    for side in (-1, 1):
        ex = cx + side * 190
        d.arc([ex - 95, 430, ex + 95, 560], 200, 340, fill=(60, 40, 22, 255), width=18)
        d.arc([ex - 130, 330, ex + 130, 430], 220, 320, fill=(60, 40, 22, 255), width=14)
    d.ellipse([cx - 210, 620, cx + 210, 850], fill=(70, 30, 24, 255),
              outline=(70, 50, 30, 255), width=8)
    d.rounded_rectangle([cx - 170, 630, cx + 170, 690], 16, fill=(235, 228, 210, 255))
    d.ellipse([cx - 90, 760, cx + 90, 850], fill=(180, 80, 80, 255))  # tongue
    img.save(os.path.join(out_dir, "horus_laugh.png"))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    ball(os.path.join(OUT, "wh_ball.jpg"))
    lane(os.path.join(OUT, "wh_lane.jpg"))
    space(os.path.join(OUT, "wh_space.jpg"))
    horus_faces(OUT)
    for f in sorted(os.listdir(OUT)):
        print(f, os.path.getsize(os.path.join(OUT, f)) // 1024, "KB")
