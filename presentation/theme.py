# -*- encoding: utf-8 -*-
"""菜单图和报告卡片共用的画法。

配色只取伊菈身上有的东西：银（发丝、发冠、纹章藤蔓）、红宝石（眼眸、吊坠）、
近黑的底。金色和绿色都不在这里。装饰是家纹、弯月、纸飞机和魔术师牌，
两边用同一套，所以所有发出去的图看起来是一家人。
"""

from __future__ import annotations

import math
from pathlib import Path

INK = (10, 8, 14)
SILVER = (198, 204, 214)
SILVER_DIM = (122, 128, 140)
RUBY = (168, 32, 54)
RUBY_DEEP = (92, 14, 28)
CREAM = (232, 226, 222)
MUTED = (150, 142, 146)
LINE = (70, 60, 66)
CARD = (18, 14, 20, 255)

FONT_TITLE = r'C:\Windows\Fonts\STZHONGS.TTF'
FONT_EN = r'C:\Windows\Fonts\georgia.ttf'
FONT_SANS = r'C:\Windows\Fonts\NotoSansSC-VF.ttf'


def font(size: int, bold: bool = False):
    """正文用思源黑体的粗体。

    这个可变字体默认落在最细的一档，发到群里会发糊，所以显式选字重：
    正文 Bold，小字备注 Medium。没有思源黑体时退回微软雅黑粗体。
    """
    from PIL import ImageFont

    if Path(FONT_SANS).exists():
        face = ImageFont.truetype(FONT_SANS, size)
        face.set_variation_by_name('Bold' if bold else 'Medium')
        return face
    fallback = Path(r'C:\Windows\Fonts') / 'msyhbd.ttc'
    if fallback.exists():
        return ImageFont.truetype(str(fallback), size)
    return ImageFont.load_default()


def title_font(size: int):
    from PIL import ImageFont

    if Path(FONT_TITLE).exists():
        return ImageFont.truetype(FONT_TITLE, size)
    return font(size, bold=True)


def english_font(size: int):
    from PIL import ImageFont

    if Path(FONT_EN).exists():
        return ImageFont.truetype(FONT_EN, size)
    return font(size)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def gradient_text(img, text, fnt, x, y, top, bottom):
    """竖向渐变的文字：顶部亮银，底部暗银。"""
    from PIL import Image, ImageDraw

    mask = Image.new('L', img.size, 0)
    ImageDraw.Draw(mask).text((x, y), text, font=fnt, fill=255)
    box = mask.getbbox()
    if not box:
        return
    grad = Image.new('RGBA', img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for yy in range(box[1], box[3]):
        t = (yy - box[1]) / max(1, box[3] - box[1])
        gd.line((box[0], yy, box[2], yy), fill=lerp(top, bottom, t) + (255,))
    grad.putalpha(mask)
    img.alpha_composite(grad)


def background(width, height):
    """近黑的竖向渐变，左下一点暗红，右上一点冷银。"""
    from PIL import Image, ImageDraw, ImageFilter

    img = Image.new('RGB', (width, height))
    d = ImageDraw.Draw(img)
    for y in range(height):
        d.line((0, y, width, y), fill=lerp(INK, (20, 10, 16), y / max(1, height)))
    glow = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse((width - 520, -320, width + 200, 400), fill=(200, 210, 230, 30))
    g.ellipse((-300, height - 470, 380, height + 210), fill=(120, 16, 36, 34))
    return Image.alpha_composite(img.convert('RGBA'), glow.filter(ImageFilter.GaussianBlur(70)))


def notched_frame(img, x0, y0, x1, y1, r=24):
    """内框：四角向内凹成四分之一圆弧，凹口里嵌一颗小红宝石。"""
    from PIL import ImageDraw

    d = ImageDraw.Draw(img)
    c = SILVER + (210,)
    d.line((x0 + r, y0, x1 - r, y0), fill=c, width=1)
    d.line((x0 + r, y1, x1 - r, y1), fill=c, width=1)
    d.line((x0, y0 + r, x0, y1 - r), fill=c, width=1)
    d.line((x1, y0 + r, x1, y1 - r), fill=c, width=1)
    d.arc((x0 - r, y0 - r, x0 + r, y0 + r), 0, 90, fill=c, width=1)
    d.arc((x1 - r, y0 - r, x1 + r, y0 + r), 90, 180, fill=c, width=1)
    d.arc((x0 - r, y1 - r, x0 + r, y1 + r), 270, 360, fill=c, width=1)
    d.arc((x1 - r, y1 - r, x1 + r, y1 + r), 180, 270, fill=c, width=1)
    for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        ruby_diamond(d, cx, cy, 6)


def ruby_diamond(draw, cx, cy, size):
    draw.polygon([(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)],
                 fill=RUBY + (255,), outline=SILVER + (230,))


def crest(img, cx, cy, r=34):
    """雷恩家纹章：银色圆框，里面一颗红宝石。"""
    from PIL import Image, ImageDraw

    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=SILVER + (255,), width=2)
    d.ellipse((cx - r + 5, cy - r + 5, cx + r - 5, cy + r - 5), outline=SILVER_DIM + (180,), width=1)
    for i in range(8):
        a = i * math.pi / 4 + 0.2
        x1 = cx + math.cos(a) * (r - 8)
        y1 = cy + math.sin(a) * (r - 8)
        x2 = cx + math.cos(a + 0.5) * (r * 0.45)
        y2 = cy + math.sin(a + 0.5) * (r * 0.45)
        d.arc((min(x1, x2) - 6, min(y1, y2) - 6, max(x1, x2) + 6, max(y1, y2) + 6),
              0, 200, fill=SILVER_DIM + (160,))
    rr = r * 0.32
    d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=RUBY_DEEP + (255,))
    rr2 = rr * 0.7
    d.ellipse((cx - rr2, cy - rr2, cx + rr2, cy + rr2), fill=RUBY + (255,))
    d.ellipse((cx - 3, cy - rr2 * 0.6 - 3, cx + 3, cy - rr2 * 0.6 + 3), fill=(255, 230, 234, 200))
    img.alpha_composite(layer)


def moon(img, cx, cy, r=38):
    """银色渐变弯月，外面一圈细光环和几颗星芒。"""
    from PIL import Image, ImageDraw, ImageFilter

    glow = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((cx - r * 2.2, cy - r * 2.2, cx + r * 2.2, cy + r * 2.2),
                                 fill=(200, 210, 230, 40))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(30)))

    mask = Image.new('L', img.size, 0)
    md = ImageDraw.Draw(mask)
    md.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    off = r * 0.42
    md.ellipse((cx - r + off, cy - r - off * 0.35, cx + r + off, cy + r - off * 0.35), fill=0)
    grad = Image.new('RGBA', img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for yy in range(int(cy - r), int(cy + r) + 1):
        t = (yy - (cy - r)) / (2 * r)
        gd.line((cx - r, yy, cx + r, yy), fill=lerp((244, 246, 250), (150, 156, 170), t) + (255,))
    grad.putalpha(mask)
    img.alpha_composite(grad)

    d = ImageDraw.Draw(img)
    d.ellipse((cx - r - 16, cy - r - 16, cx + r + 16, cy + r + 16), outline=SILVER_DIM + (150,), width=1)
    for k in range(48):
        if k % 4 == 0:
            continue
        a = 2 * math.pi * k / 48
        x, y = cx + (r + 24) * math.cos(a), cy + (r + 24) * math.sin(a)
        d.ellipse((x - 1, y - 1, x + 1, y + 1), fill=SILVER_DIM + (160,))

    def sparkle(x, y, s, color):
        d.polygon([(x, y - s), (x + s * 0.22, y - s * 0.22), (x + s, y), (x + s * 0.22, y + s * 0.22),
                    (x, y + s), (x - s * 0.22, y + s * 0.22), (x - s, y), (x - s * 0.22, y - s * 0.22)],
                   fill=color)

    sparkle(cx + r * 0.55, cy + r * 0.05, 7, SILVER + (240,))
    sparkle(cx - r - 40, cy - r * 0.6, 6, SILVER + (210,))
    sparkle(cx - r - 22, cy + r * 0.9, 4, RUBY + (255,))
    sparkle(cx + r + 34, cy + r * 0.7, 4, SILVER_DIM + (220,))


def divider(img, y, cx):
    """两侧渐隐的细银线，中间是家纹红宝石吊坠。"""
    from PIL import Image, ImageDraw

    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    span = 520
    for side in (-1, 1):
        for k in range(span):
            a = int(200 * (1 - k / span))
            d.point((cx + side * (40 + k), y), fill=SILVER + (a,))
        for k in (60, 76):
            x = cx + side * k
            ruby_diamond(d, x, y, 4)
    img.alpha_composite(layer)
    crest(img, cx, y, 24)


def paper_plane(img, cx, cy):
    """朝右上飞的纸飞机，机尾两个后角各一颗红宝石。"""
    from PIL import ImageDraw

    d = ImageDraw.Draw(img)
    c = SILVER + (235,)
    s = 1.5

    def p(x, y):
        return (cx + x * s, cy + y * s)

    nose = p(52, -50)
    wing = p(-50, -4)
    tail = p(-22, 36)
    fold = p(-6, 6)
    keel = p(-14, 22)
    d.polygon([nose, wing, fold], fill=(26, 22, 30, 255), outline=c)
    d.polygon([nose, fold, keel], fill=(16, 13, 20, 255), outline=c)
    d.polygon([nose, keel, tail], fill=(22, 18, 26, 255), outline=c)
    for px, py in (wing, tail):
        d.ellipse((px - 4, py - 4, px + 4, py + 4), fill=RUBY + (255,))
    for k in range(7):
        x0, y0 = p(-30 - k * 12, 44 + k * 7)
        d.line((x0, y0, x0 - 6, y0 + 3), fill=SILVER_DIM + (150 - k * 15,), width=1)


def tarot_fan(img, cx, cy):
    """一叠大阿尔卡纳牌背，抽出的一张是魔术师。

    牌面只画四要素：权杖头、宝剑、圣杯、星币，不照抄任何现成牌组的插画。
    宝剑没有剑柄，冠环下面隔开一小段直接接剑刃。
    """
    from PIL import Image, ImageDraw

    card_w, card_h = 96, 150

    def one_card(face):
        card = Image.new('RGBA', (card_w, card_h), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        face_fill = (32, 26, 34, 255) if face else (14, 11, 16, 255)
        cd.rounded_rectangle((1, 1, card_w - 2, card_h - 2), radius=7,
                             fill=face_fill, outline=SILVER + (235,), width=2)
        cd.rounded_rectangle((7, 7, card_w - 8, card_h - 8), radius=4,
                             outline=SILVER_DIM + (170,))
        mx, my = card_w / 2, card_h / 2 + (6 if face else 0)
        if face:
            f = english_font(18)
            box = cd.textbbox((0, 0), 'I', font=f)
            cd.text((mx - (box[2] - box[0]) / 2 - box[0], 12), 'I', font=f, fill=RUBY + (255,))
            ly, lr = 44, 9
            pts = [(mx + lr * 1.7 * math.sin(t) / (1 + math.cos(t) ** 2),
                    ly + lr * math.sin(t) * math.cos(t) / (1 + math.cos(t) ** 2) * 1.6)
                   for t in (k * math.pi / 40 for k in range(81))]
            cd.line(pts, fill=SILVER + (240,), width=2)
            cd.ellipse((mx - 5, 56, mx + 5, 66), fill=RUBY + (255,), outline=SILVER + (240,))
            cd.arc((mx - 8, 62, mx + 8, 72), 200, 340, fill=SILVER + (240,), width=2)
            cd.line((mx - 8, 67, mx + 8, 67), fill=SILVER + (240,), width=2)
            cd.polygon([(mx, 114), (mx - 5, 78), (mx + 5, 78)], outline=SILVER + (240,))
            cd.line((mx, 79, mx, 112), fill=SILVER_DIM + (200,))
            cup_x = mx - 26
            cd.arc((cup_x - 8, 78, cup_x + 8, 96), 0, 180, fill=SILVER + (240,), width=2)
            cd.line((cup_x - 8, 87, cup_x + 8, 87), fill=SILVER + (240,), width=2)
            cd.line((cup_x, 96, cup_x, 104), fill=SILVER + (240,), width=2)
            cd.line((cup_x - 6, 104, cup_x + 6, 104), fill=SILVER + (240,), width=2)
            coin_x, coin_y, coin_r = mx + 26, 92, 9
            cd.ellipse((coin_x - coin_r, coin_y - coin_r, coin_x + coin_r, coin_y + coin_r),
                       outline=SILVER + (240,), width=2)
            star = [(coin_x + (coin_r - 3) * math.cos(math.radians(-90 + 72 * k)),
                     coin_y + (coin_r - 3) * math.sin(math.radians(-90 + 72 * k)))
                    for k in (0, 2, 4, 1, 3)]
            cd.line(star + [star[0]], fill=RUBY + (255,), width=1)
        else:
            ruby_diamond(cd, mx, my, 7)
        return card

    for angle in (-34, -20, -8, 6, 20):
        card = one_card(False).rotate(angle, expand=True, resample=Image.BICUBIC)
        img.alpha_composite(card, (int(cx - card.width / 2 + angle * 0.6),
                                   int(cy - card.height / 2 + abs(angle) * 0.15)))
    face = one_card(True).rotate(-12, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(face, (int(cx - face.width / 2 - 40), int(cy - face.height / 2 - 22)))
