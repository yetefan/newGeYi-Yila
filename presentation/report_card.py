# -*- encoding: utf-8 -*-
"""把「状态 / 记忆 / 用量」这类多行回复画成一张卡片。

和菜单图分开：菜单是固定版式，这里是把已经拼好的文字原样排进卡片。
内容一个字不改，只换样子。画不出来、或者内容长到放不下时返回空串，
调用方改发原来的文字，所以不会出现「看图少了一半」。

适合看一眼的报告，不适合要复制的内容（面板地址、文件路径仍走文字）。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from . import theme

logger = logging.getLogger('newGeYi.report_card')

W = 1080
# 超过这么多行就放弃画图：再高的图在手机上要滑很久，不如直接看文字
MAX_LINES = 48
MARGIN = 64


def render_report(text: str, dest: Path, notes: dict | None = None) -> str:
    """把一段多行文字画成卡片，成功返回保存路径，失败返回空串。

    notes 只画在图上、不进文字：键是正文里某一行的完整内容，值是画在
    它下面的一行小字。用来标记忆的记录时间，所以不会写进对话记录。
    """
    try:
        from PIL import Image  # noqa: F401
    except Exception:  # noqa: BLE001
        logger.warning('画报告失败：Pillow 不可用')
        return ''
    try:
        return _render(str(text or ''), dest, notes or {})
    except Exception:  # noqa: BLE001
        logger.exception('画报告失败')
        return ''


def _title_of(lines: list) -> tuple:
    """第一行如果是标题（--- 标题 --- 或 【标题】），就拆出来当卡片标题。"""
    if not lines:
        return '伊菈', []
    head = lines[0].strip()
    boxed = re.fullmatch(r'-{2,}\s*(.+?)\s*-{2,}', head)
    if boxed:
        return boxed.group(1).strip() or '伊菈', lines[1:]
    if head.startswith('【') and head.endswith('】') and 1 < len(head) <= 24:
        return head.strip('【】').strip() or '伊菈', lines[1:]
    return '伊菈', lines


def _wrap(draw, value: str, font, width: int) -> list:
    if not value:
        return ['']
    rows, cur = [], ''
    for ch in value:
        trial = cur + ch
        box = draw.textbbox((0, 0), trial, font=font)
        if cur and box[2] - box[0] > width:
            rows.append(cur)
            cur = ch
        else:
            cur = trial
    if cur:
        rows.append(cur)
    return rows or ['']



def _render(text: str, dest: Path, notes: dict) -> str:
    from PIL import Image, ImageDraw

    raw = [line.rstrip() for line in text.replace('\r\n', '\n').split('\n')]
    title, body = _title_of(raw)
    while body and not body[0].strip():
        body = body[1:]
    while body and not body[-1].strip():
        body = body[:-1]
    if not body:
        return ''

    title_font = theme.title_font(42)
    body_font = theme.font(24, bold=True)
    note_font = theme.font(16)
    inner = W - MARGIN * 2 - 56
    probe = ImageDraw.Draw(Image.new('RGB', (8, 8)))
    wrapped = []
    noted = {}
    for line in body:
        rows = _wrap(probe, line, body_font, inner)
        note = str(notes.get(line) or '').strip()
        if note:
            # 记在这一条最后一行上。小字贴在它正下方，不另起一整行。
            noted[len(wrapped) + len(rows) - 1] = note
        wrapped.extend(rows)
        if len(wrapped) > MAX_LINES:
            return ''

    row_h = 40
    note_h = 22
    head_h = 190
    foot_h = 230
    # 记录时间是贴在事实下面的小字，不占一整行，所以不计入上面的行数上限
    height = head_h + len(wrapped) * row_h + len(noted) * note_h + foot_h

    img = theme.background(W, height)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((28, 28, W - 28, height - 28), radius=14,
                        outline=theme.SILVER_DIM + (200,), width=1)
    theme.notched_frame(img, 46, 46, W - 46, height - 46)

    theme.crest(img, MARGIN + 40, 104, 34)
    theme.gradient_text(img, title, title_font, MARGIN + 92, 72,
                        (236, 240, 246), (150, 156, 168))
    theme.moon(img, W - 130, 104, 28)

    card = Image.new('RGBA', img.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle((MARGIN, head_h - 20, W - MARGIN, height - foot_h + 12),
                         radius=12, fill=theme.CARD, outline=theme.LINE + (255,), width=1)
    img.alpha_composite(card)
    d = ImageDraw.Draw(img)

    y = head_h
    for index, line in enumerate(wrapped):
        d.text((MARGIN + 36, y), line, font=body_font, fill=theme.CREAM + (255,))
        note = noted.get(index)
        if note:
            y += row_h - 8
            d.text((MARGIN + 36 + 38, y), note, font=note_font, fill=theme.MUTED + (255,))
            y += note_h + 8
        else:
            y += row_h

    theme.divider(img, height - 112, W // 2)
    theme.paper_plane(img, 200, height - 108)
    theme.tarot_fan(img, W - 175, height - 90)

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.convert('RGB').save(dest, 'PNG', optimize=True)
    return str(dest.resolve())
