"""Vorschaubilder der 4 vorinstallierten Adapter-Hintergründe aus app-source erzeugen."""
import sys
from pathlib import Path
from PIL import Image

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
dst.mkdir(parents=True, exist_ok=True)
for i in (1, 2, 3, 4):
    img = Image.open(src / f"{i}.png").convert("RGB")
    img.thumbnail((288, 162), Image.LANCZOS)   # doppelte Größe; die GUI halbiert bei bis zu 175 % Skalierung
    img.save(dst / f"{i}.png", optimize=True)
