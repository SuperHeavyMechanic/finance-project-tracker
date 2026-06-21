from PIL import Image, ImageDraw

SIZE = 1024
BG = "#23211C"       # --header-bg
BAR_DARK = "#0A6450"  # --accent-strong
BAR_MID = "#0E7A5F"   # --accent
BAR_LIGHT = "#57C29C"  # --accent-on-dark

img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Squircle-ish rounded square background (macOS-style corner ratio)
corner_radius = int(SIZE * 0.176)
draw.rounded_rectangle([(0, 0), (SIZE, SIZE)], radius=corner_radius, fill=BG)

# Three descending bars, rounded tops only (expenses trending down)
bar_width = 130
gap = 55
heights = [480, 370, 260]
colors = [BAR_LIGHT, BAR_MID, BAR_DARK]
total_width = bar_width * 3 + gap * 2
start_x = (SIZE - total_width) // 2
bottom_y = 760
bar_radius = 28

for i, (h, color) in enumerate(zip(heights, colors)):
    x0 = start_x + i * (bar_width + gap)
    x1 = x0 + bar_width
    y0 = bottom_y - h
    y1 = bottom_y
    # rounded top corners, square bottom corners
    draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=bar_radius, fill=color)
    draw.rectangle([(x0, y0 + bar_radius), (x1, y1)], fill=color)

img.save("/Users/shansebastian/Claude Code Projects/01-Finance Project Tracker/branding/icon_1024.png")
print("done")
