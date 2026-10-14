"""Génère icon.ico (flèche d'envoi sur fond bleu arrondi)."""
from PIL import Image, ImageDraw

S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
grad = Image.new("RGBA", (S, S))
gd = ImageDraw.Draw(grad)
for y in range(S):
    t = y / S
    gd.line([(0, y), (S, y)], fill=(int(70 - 30 * t), int(140 - 60 * t), int(255 - 40 * t), 255))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([16, 16, S - 16, S - 16], radius=110, fill=255)
img.paste(grad, (0, 0), mask)

d = ImageDraw.Draw(img)
white = (255, 255, 255, 255)
# flèche vers le haut
d.polygon([(256, 96), (396, 250), (306, 250), (306, 340), (206, 340), (206, 250), (116, 250)], fill=white)
# plateau
d.rounded_rectangle([130, 376, 382, 416], radius=20, fill=white)

img.save("icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save("icon.png")
