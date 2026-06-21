from PIL import Image

ROOT = "/Users/shansebastian/Claude Code Projects/01-Finance Project Tracker"
src = Image.open(f"{ROOT}/branding/icon_1024.png")

src.resize((16, 16), Image.LANCZOS).save(f"{ROOT}/static/favicon-16x16.png")
src.resize((32, 32), Image.LANCZOS).save(f"{ROOT}/static/favicon-32x32.png")
src.resize((180, 180), Image.LANCZOS).save(f"{ROOT}/static/apple-touch-icon.png")

icon_sizes = [(16, 16), (32, 32), (48, 48)]
src.save(
    f"{ROOT}/static/favicon.ico",
    sizes=icon_sizes,
)

print("done")
