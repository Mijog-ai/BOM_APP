import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm

# ----------------------------
# 1) Recreate data as DataFrame
# ----------------------------
data = [
    [1,  "Zsb. Regelkopf",    1],
    [2,  "Zsb. Mitnehmer",    1],
    [3,  "Welle",             1],
    [4,  "Mitnehmer",         1],
    [6,  "Zsb. Wiegenlager",  1],
    [7,  "Wiegenlager",       1],
    [8,  "Lagerschale",       2],
    [9,  "Senkschraube",      2],
    [12, "Regelkopf",         1],
    [13, "Sicherungsring",    1],
]

df = pd.DataFrame(data, columns=["Lfd.Nr.", "Benennung", "St."])

# ----------------------------
# 2) PDF layout settings
# ----------------------------
pdf_path = "table_with_arrows.pdf"
page_width, page_height = A4
c = canvas.Canvas(pdf_path, pagesize=A4)

left_margin = 25 * mm
top_margin = page_height - 25 * mm

row_h = 12 * mm
header_h = 12 * mm

# Column x positions
x_nr = left_margin
x_name = x_nr + 30 * mm
x_graph = x_name + 95 * mm   # area for arrows / vertical line
x_qty = x_graph + 25 * mm

# right border
table_right = x_qty + 18 * mm

# ----------------------------
# 3) Row placement with gaps
#    to mimic original grouping
# ----------------------------
y_positions = []
y = top_margin - header_h

for i, nr in enumerate(df["Lfd.Nr."].tolist()):
    y_positions.append(y)
    y -= row_h

    # add visual gaps after 4 and 9 like the image
    if nr == 4 or nr == 9:
        y -= 10 * mm

# ----------------------------
# 4) Draw header
# ----------------------------
c.setFont("Helvetica-Bold", 10)
c.setFillColor(colors.black)
c.drawString(x_nr, top_margin, "Lfd.Nr.")
c.drawString(x_name, top_margin, "Benennung")
c.drawString(x_qty, top_margin, "St.")

# underline header
c.setStrokeColor(colors.HexColor("#cfcfcf"))
c.setLineWidth(0.8)
c.line(left_margin - 2 * mm, top_margin - 3 * mm, table_right, top_margin - 3 * mm)

# ----------------------------
# 5) Draw table rows
# ----------------------------
c.setFont("Helvetica", 10)
light_grid = colors.HexColor("#e6e6e6")

for i, row in df.iterrows():
    y = y_positions[i]

    # row line
    c.setStrokeColor(light_grid)
    c.setLineWidth(0.6)
    c.line(left_margin - 2 * mm, y - 3 * mm, table_right, y - 3 * mm)

    # text
    c.setFillColor(colors.black)
    c.drawString(x_nr + 6, y, str(row["Lfd.Nr."]))
    c.drawString(x_name, y, str(row["Benennung"]))
    c.drawString(x_qty + 5, y, str(row["St."]))

# bottom border
c.setStrokeColor(colors.HexColor("#cfcfcf"))
c.setLineWidth(0.8)
c.line(left_margin - 2 * mm, y_positions[-1] - 8 * mm, table_right, y_positions[-1] - 8 * mm)

# ----------------------------
# 6) Helper functions
# ----------------------------
def row_center(row_number):
    """
    Return y center for a given Lfd.Nr.
    """
    idx = df.index[df["Lfd.Nr."] == row_number][0]
    return y_positions[idx] + 1.5 * mm

def draw_dot(x, y, r=1.4 * mm, color=colors.HexColor("#8f8f8f")):
    c.setFillColor(color)
    c.setStrokeColor(color)
    c.circle(x, y, r, fill=1, stroke=0)

def draw_vertical_connector(x, y_top, y_bottom, color=colors.HexColor("#9a9a9a")):
    c.setStrokeColor(color)
    c.setLineWidth(0.7)
    c.line(x, y_top, x, y_bottom)

def draw_left_arrow(x_right, y, length=12 * mm, color=colors.HexColor("#2d74da")):
    """
    Draw a left-facing arrow whose tip is on the left.
    x_right = right end of horizontal shaft
    """
    x_left = x_right - length
    c.setStrokeColor(color)
    c.setLineWidth(1.1)
    c.line(x_left, y, x_right, y)

    # arrow head at left
    ah = 2 * mm
    c.line(x_left, y, x_left + ah, y + ah * 0.8)
    c.line(x_left, y, x_left + ah, y - ah * 0.8)

def draw_blue_node(x, y):
    draw_dot(x, y, r=1.5 * mm, color=colors.HexColor("#2d74da"))

# ----------------------------
# 7) Draw arrows and vertical lines
#    based on the visible structure
# ----------------------------

# Common x positions for graphics
x_v1 = x_graph + 7 * mm   # first vertical line
x_v2 = x_graph + 13 * mm  # second vertical line

# Group 1: rows 1-4
y1 = row_center(1)
y2 = row_center(2)
y3 = row_center(3)
y4 = row_center(4)

# Blue arrow from row 1 into first connector
draw_left_arrow(x_v2, y1, length=14 * mm)
draw_blue_node(x_v2, y2)

# Blue arrow from row 2 into first connector
draw_left_arrow(x_v1 - 1 * mm, y2, length=10 * mm)

# vertical connectors
draw_vertical_connector(x_v2, y1, y4)
draw_vertical_connector(x_v1, y2, y4)

# dots on verticals
for yy in [y2, y3, y4]:
    draw_dot(x_v2, yy)
for yy in [y3, y4]:
    draw_dot(x_v1, yy)

# Group 2: rows 6-9
y6 = row_center(6)
y7 = row_center(7)
y8 = row_center(8)
y9 = row_center(9)

draw_left_arrow(x_v2, y6, length=11 * mm)
draw_blue_node(x_v2, y6)

draw_vertical_connector(x_v2, y6, y12 := row_center(12))
draw_vertical_connector(x_v1, y7, y8)

for yy in [y7, y8]:
    draw_dot(x_v1, yy)

for yy in [y8, y9, y12]:
    draw_dot(x_v2, yy)

# Group 3: rows 12-13 on same long vertical
y12 = row_center(12)
y13 = row_center(13)
draw_vertical_connector(x_v2, y12, y13)
draw_dot(x_v2, y12)
draw_dot(x_v2, y13)

# ----------------------------
# 8) Save PDF
# ----------------------------
c.save()

print("PDF created:", pdf_path)
print()
print("DataFrame:")
print(df)