# -*- encoding: utf-8 -*-
"""「伊菈菜单」的图片版。

为什么单独放这里：菜单的文字清单在 routing/commands.py，那是「有哪些指令」的唯一来源；
这里只负责把它画成一张图。画不出来（缺字体、缺画图库）时返回空串，
调用方退回原来的文字菜单，所以这张图是锦上添花，不是新的故障点。

版式是骰主看过样稿后定的：横版三列卡片、不要版本号，银与红宝石的装饰。
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import theme

logger = logging.getLogger('newGeYi.menu_card')

W = 1600
CARD_W_GAP = 28

# 报告卡片还在用这些名字，统一指向新配色，免得两张图各画各的。
GOLD = theme.SILVER
GOLD_DIM = theme.SILVER_DIM
CREAM = theme.CREAM
MUTED = theme.MUTED
LINE = theme.LINE
CARD = theme.CARD
PETAL = [theme.RUBY_DEEP, theme.RUBY]

# 分组和 commands.py 里的文字菜单一一对应。改指令时两边都要改，
# 测试会核对「赞助名单」还在、档位额度不出现。
GROUPS = [
    ('大家都能用', '忘记后面写编号，其余原样发',
     ['状态', '用量', '记忆', '忘记 编号', '忘了我', '关系', '世界书状态', '查看触发词']),
    ('群管理', '群管或主人；开和关是两条',
     ['被动开', '被动关', '主动开', '主动关', '设置群背景 文字', '群背景']),
    ('主人 · 运行', '「切换」后面要接渠道',
     ['渠道', '切换 名称', '切换 自动', '面板', '静默列表', '解除静默', '测试通知', '搭话观察']),
    ('主人 · 开关', '斜杠两边各发一条，不要打斜杠',
     ['全局被动开/关', '主动搭话开/关', '搭话影子开/关', '世界书开/关', '好感度开/关',
      '好感度影子开/关', '图片理解开/关', '休眠开/关', '私聊触发词开/关',
      '开启私聊', '关闭私聊', '开启表情包', '关闭表情包', '开启语音', '关闭语音']),
    ('主人 · 好感', '空格后面要换成真实内容',
     ['关系详情 QQ', '关系设置 QQ 0-5', '关系重置 QQ', '私聊用量', '赞助名单',
      '赞助加 QQ', '赞助删 QQ']),
    ('主人 · 维护', '空格后面要换成真实内容',
     ['记忆状态', '导出记忆', '重置上下文', '重载设定', '世界书重载', '添加触发词 词',
      '删除触发词 词', '设置key 密钥（私聊）', '休眠状态', '休眠时间 23:30-07:00', '休眠重置',
      '表情包状态', '表情包重载', '加载表情包 路径', '语音状态', '测试语音', '语音重载',
      '自动好友状态', '自动好友开/关', '自动好友检查']),
]


def _font(size: int, bold: bool = False):
    """报告卡片还在调用这个名字，实际走共用的字体选择。"""
    return theme.font(size, bold)


def _lerp(a, b, t):
    return theme.lerp(a, b, t)


def _chip_rows(draw, chips, font, inner_w):
    rows, row, used = [], [], 0
    for chip in chips:
        box = draw.textbbox((0, 0), chip, font=font)
        width = box[2] - box[0] + 32
        if row and used + width > inner_w:
            rows.append(row)
            row, used = [], 0
        row.append((chip, width))
        used += width + 10
    if row:
        rows.append(row)
    return rows


def render_menu_card(channel: str, states: dict, dest: Path) -> str:
    """画菜单并保存到 dest。成功返回路径，任何失败都返回空串（调用方改发文字）。

    states 的键：worldbook / memory / image / voice，值是已经算好的「开」「关」之类的短词。
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: F401
    except Exception:  # noqa: BLE001 - 没有画图库就退回文字，不影响菜单本身
        logger.warning('画菜单失败：Pillow 不可用')
        return ''
    try:
        return _render(channel, states, dest)
    except Exception:  # noqa: BLE001 - 画图出错不能让「伊菈菜单」没反应
        logger.exception('画菜单失败')
        return ''


def _render(channel: str, states: dict, dest: Path) -> str:
    from PIL import Image, ImageDraw

    probe = ImageDraw.Draw(Image.new('RGB', (8, 8)))
    left, top = 100, 320
    card_w = (W - left * 2 - CARD_W_GAP * 2) // 3
    inner_w = card_w - 56
    head = theme.title_font(26)
    chip_font = theme.font(20)
    note_font = theme.font(17)
    laid = []
    for title_text, note_text, chips in GROUPS:
        rows = _chip_rows(probe, chips, chip_font, inner_w)
        laid.append((title_text, note_text, rows,
                     50 + (30 if note_text else 0) + len(rows) * 42 + 52))
    row_heights = [max(c[3] for c in laid[0:3]), max(c[3] for c in laid[3:6])]
    bottom = top + sum(row_heights) + CARD_W_GAP
    height = bottom + 200

    img = theme.background(W, height)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((28, 28, W - 28, height - 28), radius=14,
                        outline=theme.SILVER_DIM + (200,), width=1)
    theme.notched_frame(img, 46, 46, W - 46, height - 46)

    # 左上：家纹在前，标题在后，像信笺抬头
    theme.crest(img, 160, 130, 50)
    tx = 240
    theme.gradient_text(img, '伊 菈', theme.title_font(84), tx, 68,
                        (236, 240, 246), (150, 156, 168))
    d = ImageDraw.Draw(img)
    d.text((tx + 8, 172), 'H O U S E   W R E N', font=theme.english_font(20),
           fill=theme.SILVER_DIM + (255,))
    d.line((tx + 8, 206, tx + 320, 206), fill=theme.SILVER_DIM + (160,), width=1)
    d.text((118, 248), '前面加「伊菈」。带空格的，空格后面也要换成真实内容',
           font=theme.font(22), fill=MUTED + (255,))

    theme.moon(img, 1420, 130, 38)

    pill_font = theme.font(18)
    pills = ['世界书  %s' % states.get('worldbook', '关'),
             '记忆  %s' % states.get('memory', '关'),
             '图片  %s' % states.get('image', '关'),
             '语音  %s' % states.get('voice', '关')]
    x = 1280
    d = ImageDraw.Draw(img)
    for pill in reversed(pills):
        box = d.textbbox((0, 0), pill, font=pill_font)
        w = box[2] - box[0] + 30
        x -= w
        d.rounded_rectangle((x, 222, x + w, 252), radius=15,
                            outline=theme.SILVER_DIM + (180,), width=1)
        d.text((x + 15, 227), pill, font=pill_font, fill=theme.SILVER + (255,))
        x -= 10

    cards = Image.new('RGBA', img.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(cards)
    rects = []
    for i, _card in enumerate(laid):
        col, row = i % 3, i // 3
        x0 = left + col * (card_w + CARD_W_GAP)
        y0 = top + sum(row_heights[:row]) + CARD_W_GAP * row
        rect = (x0, y0, x0 + card_w, y0 + row_heights[row])
        rects.append(rect)
        cd.rounded_rectangle(rect, radius=12, fill=CARD, outline=LINE + (255,), width=1)
    img.alpha_composite(cards)
    d = ImageDraw.Draw(img)

    for (title_text, note_text, rows, _), (x0, y0, _x1, _y1) in zip(laid, rects):
        d.polygon([(x0 + 30, y0 + 40), (x0 + 38, y0 + 32), (x0 + 46, y0 + 40), (x0 + 38, y0 + 48)],
                  fill=theme.RUBY + (255,))
        d.text((x0 + 58, y0 + 24), title_text, font=head, fill=theme.SILVER + (255,))
        cy = y0 + 70
        if note_text:
            d.text((x0 + 28, cy), note_text, font=note_font, fill=MUTED + (255,))
            cy += 30
        for row_i, row in enumerate(rows):
            cx = x0 + 28
            for chip, width in row:
                cy0 = cy + row_i * 42
                d.rounded_rectangle((cx, cy0, cx + width, cy0 + 32),
                                    radius=16, outline=LINE + (255,), width=1)
                d.text((cx + 16, cy0 + 4), chip, font=chip_font, fill=CREAM + (255,))
                cx += width + 10

    bottom = rects[-1][3]
    theme.divider(img, bottom + 52, W // 2)
    theme.paper_plane(img, 200, bottom + 58)
    theme.tarot_fan(img, W - 175, bottom + 78)
    footer_font = theme.font(18)
    footer = '当前渠道  ·  %s' % (channel or '未配置')
    d = ImageDraw.Draw(img)
    box = d.textbbox((0, 0), footer, font=footer_font)
    d.text(((W - (box[2] - box[0])) // 2, bottom + 100), footer, font=footer_font,
           fill=theme.SILVER_DIM + (255,))

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.convert('RGB').save(dest, 'PNG', optimize=True)
    return str(dest.resolve())
