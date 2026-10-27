"""Erzeugt wda.ico (eigenes Symbol: Bildschirm mit Funkwellen)."""
import sys
from PIL import Image, ImageDraw

S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((16, 16, S - 16, S - 16), radius=110, fill=(0, 95, 184, 255))
# Bildschirm
d.rounded_rectangle((96, 150, 416, 350), radius=22, outline="white", width=26)
d.rectangle((236, 350, 276, 392), fill="white")
d.rounded_rectangle((176, 386, 336, 412), radius=12, fill="white")
# Funkwellen
for i, r in enumerate((40, 80)):
    d.arc((256 - r, 96 - r, 256 + r, 96 + r), start=220, end=320, fill="white", width=18)
d.ellipse((244, 84, 268, 108), fill="white")
img.save(sys.argv[1], sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
