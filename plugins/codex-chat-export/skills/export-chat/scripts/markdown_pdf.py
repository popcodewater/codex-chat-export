"""Render parsed GFM blocks to local paginated PDF without a browser or server."""
from pathlib import Path
import html
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Preformatted, Table, TableStyle,
    ListFlowable, ListItem, HRFlowable,
)

PX = .75


class CodeBlock(Preformatted):
    def draw(self):
        self.canv.saveState()
        self.canv.setFillColor(colors.HexColor('#edf0f3'))
        self.canv.rect(0, -6, self.width, self.height+12, fill=1, stroke=0)
        self.canv.restoreState()
        super().draw()

    def split(self, width, height):
        return [CodeBlock('\n'.join(part.lines), part.style) for part in super().split(width, height)]


def register_fonts():
    directory = Path('/System/Library/Fonts')
    main = directory / 'Supplemental/Arial Unicode.ttf'
    bold = directory / 'STHeiti Medium.ttc'
    mono = directory / 'Menlo.ttc'
    italic = directory / 'Supplemental/Arial Italic.ttf'
    for name, path in [('ChatText', main), ('ChatBold', bold), ('ChatCode', mono), ('ChatItalic', italic)]:
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily('ChatText', normal='ChatText', bold='ChatBold', italic='ChatItalic', boldItalic='ChatBold')


def escaped(text):
    return escape(html.unescape(str(text)))


def inline(tokens):
    result = []
    for token in tokens or []:
        kind, text = token.get('type'), token.get('text', '')
        children = inline(token['tokens']) if token.get('tokens') else escaped(text)
        if kind == 'strong':
            value = f'<b>{children}</b>'
        elif kind == 'em':
            # Preserve nested inline styles; the CJK fallback has no italic face.
            value = children if re.search(r'[^\x00-\x7f]', text) else f'<i>{children}</i>'
        elif kind == 'del':
            value = f'<strike>{children}</strike>'
        elif kind == 'codespan':
            face = 'ChatText' if re.search(r'[^\x00-\x7f]', text) else 'ChatCode'
            value = f'<font name="{face}" size="16.5" color="#315447" backColor="#edf1ef">{escaped(text)}</font>'
        elif kind == 'link':
            href = token.get('href', '')
            value = f'<u><font color="#24795d">{children}</font></u>'
            if re.match(r'^https?://', href):
                value = f'<link href={html.escape(href, quote=True)!r}>{value}</link>'
        elif kind == 'image':
            value = f'<font color="#7a838b">[图片：{escaped(text or "附件")}]</font>'
        elif kind == 'br':
            value = '<br/>'
        elif kind == 'html':
            value = escaped(text)
        else:
            value = children
        result.append(value)
    return ''.join(result)


def style(name='body', quote=0, **changes):
    options = dict(fontName='ChatText', fontSize=20.25, leading=32.25, textColor=colors.HexColor('#233039'),
                   spaceAfter=13.5, wordWrap='CJK', leftIndent=quote * 16.5, allowWidows=0, allowOrphans=0)
    if quote:
        options.update(backColor=colors.HexColor('#eef5f0'), textColor=colors.HexColor('#53675c'), borderPadding=7.5)
    options.update(changes)
    return ParagraphStyle(name, **options)


def wrapped_code(text, face, size, width):
    lines = []
    for line in text.expandtabs(4).split('\n'):
        current = ''
        for char in line:
            if current and pdfmetrics.stringWidth(current + char, face, size) > width:
                lines.append(current)
                current = char
            else:
                current += char
        lines.append(current)
    return '\n'.join(lines)


def blocks(tokens, width, quote=0):
    output = []
    for token in tokens:
        kind, text = token.get('type'), token.get('text', '')
        if kind == 'space':
            continue
        if kind == 'heading':
            size = {1:30, 2:25.5, 3:23, 4:21}.get(token['depth'], 20.25)
            output.append(Paragraph(inline(token.get('tokens')), style('heading', quote, fontName='ChatBold', fontSize=size,
                leading=size*1.4, spaceBefore=14, spaceAfter=11, keepWithNext=True)))
        elif kind in ('paragraph', 'text'):
            output.append(Paragraph(inline(token.get('tokens')) if token.get('tokens') else escaped(text), style(quote=quote)))
        elif kind == 'code':
            face = 'ChatText' if re.search(r'[^\x00-\x7f]', text) else 'ChatCode'
            code_style = style('code', quote, fontName=face, fontSize=17.25, leading=25.5,
                               backColor=colors.HexColor('#edf0f3'), borderPadding=10,
                               leftIndent=10+quote*16.5, rightIndent=10, spaceBefore=7, spaceAfter=18)
            output.append(CodeBlock(wrapped_code(text, face, 17.25, width-30-quote*16.5), code_style))
        elif kind == 'list':
            items = []
            for item in token.get('items', []):
                contents = blocks(item.get('tokens', []), width-30, quote)
                if item.get('task'):
                    marker = '☑' if item.get('checked') else '☐'
                    contents.insert(0, Paragraph(marker, style(fontSize=18, spaceAfter=0)))
                items.append(ListItem(contents or [Paragraph(' ', style())]))
            output.append(ListFlowable(items, bulletType='1' if token.get('ordered') else 'bullet',
                start=token.get('start', 1) if token.get('ordered') else 'bulletchar',
                leftIndent=30+quote*16.5, bulletFontName='ChatText', bulletFontSize=18,
                bulletFormat='%s.' if token.get('ordered') else None,
                spaceAfter=10))
        elif kind == 'blockquote':
            output.extend(blocks(token.get('tokens', []), width-20, quote+1))
        elif kind == 'hr':
            output.extend([Spacer(1, 8), HRFlowable(width='100%', thickness=1.2, color=colors.HexColor('#cedbd3')), Spacer(1, 15)])
        elif kind == 'table':
            header = token.get('header', [])
            if not header:
                continue
            count = len(header)
            rows = [header] + token.get('rows', [])
            data = []
            for index, row in enumerate(rows):
                cells = []
                for n in range(count):
                    cell = row[n] if n < len(row) else {}
                    align = {'left':0, 'center':1, 'right':2}.get(cell.get('align'), 0)
                    cells.append(Paragraph(inline(cell.get('tokens')) or escaped(cell.get('text', '')),
                        style('cell', fontName='ChatBold' if index==0 else 'ChatText', fontSize=18, leading=26, spaceAfter=0, alignment=align)))
                data.append(cells)
            table = Table(data, colWidths=[width/count]*count, repeatRows=1, splitByRow=1, splitInRow=1)
            table.setStyle(TableStyle([
                ('GRID',(0,0),(-1,-1),.8,colors.HexColor('#cad8ce')),
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5eee9')),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f8f7')]),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),10),
                ('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9),
            ]))
            output.extend([table, Spacer(1, 16)])
        elif kind == 'html':
            output.append(Paragraph(escaped(text).replace('\n', '<br/>'), style(quote=quote)))
        else:
            if text:
                output.append(Paragraph(escaped(text), style(quote=quote)))
    return output


def render_pdf(data, destination, page_height):
    register_fonts()
    page_width = 1200*PX
    height = page_height*PX
    doc = SimpleDocTemplate(str(destination), pagesize=(page_width,height),
        leftMargin=64*PX,rightMargin=64*PX,topMargin=110*PX,bottomMargin=44*PX)
    story = []
    for message in data['messages']:
        user = message['role']=='user'
        label = f'{"你" if user else "Codex"} · #{message["number"]}'
        story.append(Paragraph(label, style('role', fontName='ChatBold', fontSize=18, leading=28, keepWithNext=True,
            backColor=colors.HexColor('#e5f1ec' if user else '#f2f4f6'), borderPadding=8,
            spaceBefore=8,spaceAfter=14,textColor=colors.HexColor('#28725c' if user else '#536779'))))
        story.extend(blocks(message['tokens'], doc.width-12))
        story.append(Spacer(1, 16))

    def header(canvas, document):
        canvas.saveState()
        canvas.setFont('ChatText',16)
        canvas.setFillColor(colors.HexColor('#63716a'))
        canvas.drawString(64*PX,height-50*PX,f'Codex 聊天记录 · {data["short_id"]} · 消息 {data["start"]}–{data["end"]}')
        canvas.drawRightString(page_width-64*PX,height-50*PX,f'第 {document.page} 页')
        canvas.restoreState()
    doc.build(story,onFirstPage=header,onLaterPages=header)
