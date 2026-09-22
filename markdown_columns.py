#!/usr/bin/env python3
"""Lay out long Markdown or plain-text articles as duplex-ready two-column PDFs."""

from __future__ import annotations

import argparse
import html
import io
import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit, urljoin
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parent / "vendor" / "pyphen"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

from pypdf import PdfReader
from reportlab.lib.colors import Color
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph as ReportLabParagraph,
    Image,
    KeepTogether,
    Spacer,
)


INK = Color(0.055, 0.055, 0.055)
MUTED = Color(0.48, 0.48, 0.48)
BASELINE = 11.5
FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
FONT_REGULAR_PATH = FONT_DIR / "ABCAreal-400.ttf"
FONT_BOLD_PATH = FONT_DIR / "ABCAreal-700.ttf"
FONT_ITALIC_PATH = FONT_DIR / "ABCAreal-400-Italic.ttf"
FONT_REGULAR = "ABCAreal-400"
FONT_BOLD = "ABCAreal-700"
FONT_ITALIC = "ABCAreal-400-Italic"


class Paragraph(ReportLabParagraph):
    """Keep ReportLab's first split fragment from reflowing into an extra line."""

    def wrap(self, avail_width, avail_height):
        split_lines = getattr(self, "blPara", None)
        if (
            getattr(self, "_splitpara", False)
            and split_lines is not None
            and all(hasattr(line, "ascent") and hasattr(line, "descent") for line in split_lines.lines)
        ):
            cached_width = getattr(split_lines, "aW", avail_width)
            if math.isclose(cached_width, avail_width, abs_tol=1e-7):
                self.width = avail_width
                self._wrapWidths = [avail_width, avail_width]
                auto_leading = getattr(self, "autoLeading", getattr(self.style, "autoLeading", ""))
                leading = self.style.leading
                if auto_leading == "max":
                    height = sum(max(line.ascent - line.descent, leading) for line in split_lines.lines)
                elif auto_leading == "min":
                    height = sum(line.ascent - line.descent for line in split_lines.lines)
                else:
                    height = len(split_lines.lines) * leading
                self.height = height
                return self.width, self.height
        return super().wrap(avail_width, avail_height)


@dataclass
class Article:
    title: str
    author: str
    date: str
    blocks: list[tuple[str, str]]
    source: str | None = None


def _inline(text: str) -> str:
    text = html.escape(text.strip(), quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(.+?)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r"<font name='Courier'>\1</font>", text)
    text = re.sub(r"\[([^]]+)]\([^)]+\)", r"<u>\1</u>", text)
    return text


def parse_article(raw: str) -> Article:
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = "\n".join(
        line for line in raw.splitlines()
        if "e-flux" not in line.lower() and not line.startswith("Obsidian Reader")
        and not re.fullmatch(
            r"(?:https?://)?(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/\S*)?",
            line.strip(),
        )
    ).strip()

    title = "Untitled"
    author = ""
    date = ""

    if raw.startswith("---\n"):
        _, frontmatter, raw = raw.split("---", 2)
        for line in frontmatter.splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip().lower() in {"title", "author", "date"}:
                locals_map = {"title": title, "author": author, "date": date}
                locals_map[key.strip().lower()] = value.strip().strip('"')
                title, author, date = locals_map["title"], locals_map["author"], locals_map["date"]
        raw = raw.strip()

    lines = raw.splitlines()
    if lines and lines[0].startswith("# "):
        title = lines.pop(0)[2:].strip()
    elif lines:
        match = re.match(r"(.+?)\s+by\s+(.+)$", lines[0].strip(), re.I)
        if match:
            title, author = match.group(1), match.group(2)
            lines.pop(0)
        else:
            match = re.match(r"(.+?)\s+[—–-]\s+(.+)$", lines[0].strip())
            if match:
                author, title = match.group(1), match.group(2)
                lines.pop(0)

    if lines and lines[0].strip():
        meta = [part.strip() for part in lines[0].split("·")]
        if len(meta) >= 2 and (not author or meta[0] == author):
            author = author or meta[0]
            date = meta[1]
            lines.pop(0)

    blocks: list[tuple[str, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            blocks.append(("body", " ".join(part.strip() for part in buffer)))
            buffer.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if stripped in {
            "Why Pace?", "Embedded Evaluators", "Pacing Within Democracies",
            "Global Pacing", "Bottom Line", "Footnotes",
        }:
            flush(); blocks.append(("section", stripped))
        elif stripped.startswith("## "):
            flush(); blocks.append(("section", stripped[3:]))
        elif stripped.startswith("### "):
            flush(); blocks.append(("subhead", stripped[4:]))
        elif re.fullmatch(r"\d+\.", stripped):
            flush(); blocks.append(("section", stripped))
        elif stripped.startswith("> "):
            flush(); blocks.append(("quote", stripped[2:]))
        elif re.match(r"^[-*] ", stripped):
            flush(); blocks.append(("bullet", stripped[2:]))
        elif re.fullmatch(r"!\[[^]]*]\([^)]+\)", stripped):
            flush(); blocks.append(("image", re.match(r"!\[[^]]*]\(([^)]+)\)", stripped).group(1)))
        elif re.match(r"^(Inka Essenhigh,|Moonlight,)", stripped):
            flush(); blocks.append(("caption", stripped))
        else:
            buffer.append(stripped)
    flush()
    return Article(title, author, date, blocks, "\n".join(lines))

# Rendering is shared by the CLI and the web endpoint. No browser layout occurs.
@dataclass(frozen=True)
class RenderOptions:
    page_size: str = 'letter'
    typeface: str = 'sans'
    start_on_right: bool = True
    duplex: bool = True
    grayscale: bool = True
    midpoint: float = 1.08
    allow_local_images: bool = True
    base_dir: Path = Path('.')


def register_fonts(typeface: str):
    from fontTools.ttLib import TTFont as FontToolsFont
    from fontTools.varLib.instancer import instantiateVariableFont
    names = ('JournalSerif', 'JournalSerifBold', 'JournalSerifItalic') if typeface == 'serif' else (FONT_REGULAR, FONT_BOLD, FONT_ITALIC)
    paths = (FONT_REGULAR_PATH, FONT_BOLD_PATH, FONT_ITALIC_PATH)
    for index, name in enumerate(names):
        if name in pdfmetrics.getRegisteredFontNames():
            continue
        if typeface == 'serif':
            source = Path(__file__).resolve().parent / 'public/fonts/Alegreya-VariableFont_wght.ttf'
            font = instantiateVariableFont(FontToolsFont(source), {'wght': 700 if index == 1 else 400}, inplace=True)
            if index == 2:
                # The bundled Alegreya has no italic face. Make an embedded
                # oblique instance so emphasis remains visible in every viewer.
                from fontTools.pens.recordingPen import DecomposingRecordingPen
                from fontTools.pens.transformPen import TransformPen
                from fontTools.pens.ttGlyphPen import TTGlyphPen
                glyphs = font.getGlyphSet()
                replacements = {}
                for glyph_name in font.getGlyphOrder():
                    recording = DecomposingRecordingPen(glyphs)
                    glyphs[glyph_name].draw(recording)
                    pen = TTGlyphPen(None)
                    recording.replay(TransformPen(pen, (1, 0, 0.2, 1, 0, 0)))
                    replacements[glyph_name] = pen.glyph()
                for glyph_name, glyph in replacements.items():
                    font['glyf'][glyph_name] = glyph
                font['post'].italicAngle = -11
        else:
            font = FontToolsFont(paths[index])
        # The static Areal instances share a PostScript name. ReportLab otherwise
        # deduplicates them and silently renders bold/italic as the regular face.
        for record in font['name'].names:
            if record.nameID == 6:
                record.string = name.encode(record.getEncoding())
        data = io.BytesIO()
        font.save(data)
        data.seek(0)
        pdfmetrics.registerFont(TTFont(name, data))
    pdfmetrics.registerFontFamily(names[0], normal=names[0], bold=names[1], italic=names[2], boldItalic=names[1])
    return names


def remote_image(url: str) -> bytes:
    """Fetch bounded public images, pinning the validated IP on every redirect."""
    for _ in range(5):
        parts = urlsplit(url)
        if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password:
            raise ValueError('Figures must use public HTTP or HTTPS URLs.')
        port = parts.port or (443 if parts.scheme == 'https' else 80)
        addresses = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('Private network image addresses are not allowed.')
        connection = http.client.HTTPConnection(parts.hostname, port, timeout=15)
        sock = socket.create_connection((addresses[0][4][0], port), timeout=15)
        try:
            if parts.scheme == 'https':
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parts.hostname)
            connection.sock = sock
            connection.request('GET', parts.path + ('?' + parts.query if parts.query else ''), headers={'Host': parts.netloc, 'User-Agent': 'JournalPrint/0.1', 'Accept': 'image/*'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location: raise ValueError('Image redirect has no destination.')
                url = urljoin(url, location); continue
            if response.status != 200: raise ValueError(f'Image server returned {response.status}.')
            data = response.read(12_000_001)
            if len(data) > 12_000_000: raise ValueError('Image exceeds the 12 MB limit.')
            return data
        finally:
            connection.close()
            sock.close()
    raise ValueError('Too many image redirects.')


def image_reader(source: str, options: RenderOptions):
    from PIL import Image as PILImage, ImageEnhance, ImageOps
    if source.startswith(('http://', 'https://')):
        data = io.BytesIO(remote_image(source))
    elif options.allow_local_images:
        data = options.base_dir / source
    else:
        raise ValueError('Use a public HTTP or HTTPS URL for each figure; local files cannot be read by the web renderer.')
    with PILImage.open(data) as original:
        if original.width * original.height > 25_000_000: raise ValueError('Image exceeds the 25 megapixel limit.')
        image = ImageOps.exif_transpose(original).convert('RGBA')
        background = PILImage.new('RGBA', image.size, 'white'); background.alpha_composite(image)
        image = background.convert('RGB')
        if options.grayscale:
            image = ImageEnhance.Brightness(ImageOps.grayscale(image)).enhance(options.midpoint)
        return ImageReader(image)


class GridFigure(Flowable):
    def __init__(self, reader, caption, style, max_height):
        super().__init__()
        self.reader = reader
        self.caption_style = style
        self.caption = caption if isinstance(caption, Paragraph) else Paragraph(caption, style) if caption else None
        self.max_height = max_height

    def wrap(self, avail_width, avail_height):
        self.caption_height = self.caption.wrap(avail_width, self.max_height)[1] if self.caption else 0
        # Reserve the start of a caption, not its entire length. Long captions
        # may continue in the next frame without shrinking the image.
        room = self.max_height - (4 * BASELINE if self.caption else 2 * BASELINE)
        width, height = self.reader.getSize()
        scale = min(avail_width / width, min(230, room) / height)
        self.image_width, self.image_height = width * scale, height * scale
        self.width = avail_width
        self.height = math.ceil((self.image_height + self.caption_height + 2 * BASELINE) / BASELINE) * BASELINE
        return self.width, self.height

    def split(self, avail_width, avail_height):
        if not self.caption:
            return []
        self.wrap(avail_width, avail_height)
        # Round the available height down so the first fragment still fits after
        # wrap() snaps the figure block up to the baseline grid.
        available = math.floor(avail_height / BASELINE) * BASELINE
        caption_room = available - self.image_height - 2 * BASELINE
        if caption_room < 2 * self.caption_style.leading:
            return []
        parts = self.caption.split(avail_width, caption_room)
        if len(parts) < 2:
            return []
        first = GridFigure(self.reader, parts[0], self.caption_style, self.max_height)
        return [first, *parts[1:]]

    def draw(self):
        y = self.height - self.image_height
        self.canv.drawImage(self.reader, (self.width - self.image_width) / 2, y, self.image_width, self.image_height, mask='auto')
        if self.caption: self.caption.drawOn(self.canv, 0, y - BASELINE - self.caption_height)


def inline(nodes):
    result = []
    for node in nodes:
        kind = node['type']; children = node.get('children', [])
        value = inline(children) if children else html.escape(node.get('raw', ''))
        if kind == 'strong': value = '<b>' + value + '</b>'
        elif kind == 'emphasis': value = '<i>' + value + '</i>'
        elif kind == 'strikethrough': value = '<strike>' + value + '</strike>'
        elif kind == 'codespan': value = '<font name="Courier">' + value + '</font>'
        elif kind == 'footnote_ref':
            # ReportLab's default superscript rises by half the body font size,
            # which puts note markers noticeably above the cap height. Keep the
            # marker compact, but lower it so it remains visually attached to
            # the word it annotates.
            value = '<super size="7.5" rise="2.5">' + str(node['attrs']['index']) + '</super>'
        elif kind == 'linebreak': value = '<br/>'
        elif kind == 'softbreak': value = ' '
        elif kind == 'inline_html':
            # Accept typographic tags only; never pass arbitrary markup to ReportLab.
            value = {'<sup>':'<super>', '</sup>':'</super>', '<sub>':'<sub>', '</sub>':'</sub>', '<br>':'<br/>', '<br/>':'<br/>'}.get(node.get('raw','').lower(), '')
        elif kind == 'image': value = html.escape(node.get('attrs', {}).get('alt', ''))
        result.append(value)
    return ''.join(result)


def render_article(article: Article, output: Path, image_map=None, options: RenderOptions | None = None) -> int:
    import mistune
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import Table, TableStyle
    options = options or RenderOptions()
    if options.page_size not in ('letter','a4','half-letter') or options.typeface not in ('sans','serif'):
        raise ValueError('Invalid paper size or typeface.')
    if not 0.85 <= options.midpoint <= 1.35: raise ValueError('Image midpoint must be between 0.85 and 1.35.')
    regular, bold, italic = register_fonts(options.typeface)
    width, height = {'letter':letter, 'a4':A4, 'half-letter':(396,612)}[options.page_size]
    margin_x, margin_top, margin_bottom, gutter = 36, 48, 36, 18
    column_width = (width - 2 * margin_x - gutter) / 2
    frame_height = math.floor((height - margin_top - margin_bottom) / BASELINE) * BASELINE
    styles = {}
    for name, font, size in [('body',regular,10),('section',bold,10),('quote',italic,10),('caption',regular,8),('note',regular,8),('code','Courier',8)]:
        styles[name] = ParagraphStyle(name, fontName=font, fontSize=size, leading=BASELINE, textColor=INK, spaceAfter=BASELINE,
            allowWidows=0, allowOrphans=0, hyphenationLang='en_US', embeddedHyphenation=1,
            alignment=TA_CENTER if name == 'section' else TA_LEFT,
            leftIndent=12 if name=='quote' else 0)
    # Notes are a secondary text stream. They use a compact rhythm of their
    # own instead of occupying the 11.5 pt body-text baseline grid.
    styles['note'].leading = 9.5
    styles['note'].spaceAfter = 9.5
    styles['note'].bulletFontName = regular
    styles['note'].bulletFontSize = 8
    doc = BaseDocTemplate(str(output), pagesize=(width,height), title=article.title, author=article.author, pageCompression=1)
    def frame(x, id): return Frame(x, margin_bottom, column_width, frame_height, leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0,id=id)
    def decorate(canvas, doc):
        canvas.saveState(); canvas.setFillColor(INK); canvas.setFont(regular,7.5)
        if doc.page > 1:
            def fit(text, limit):
                while text and pdfmetrics.stringWidth(text,regular,7.5) > limit: text=text[:-1]
                return text
            canvas.drawString(margin_x,height-24,fit(article.title,column_width))
            canvas.drawRightString(width-margin_x,height-24,fit(article.author,column_width))
        canvas.drawCentredString(width-margin_x-column_width/2,18,str(doc.page)); canvas.restoreState()
    def opening(canvas, doc):
        decorate(canvas,doc)
        if options.start_on_right:
            title = Paragraph(html.escape(article.title), ParagraphStyle('title',fontName=regular,fontSize=28,leading=29.4,textColor=INK,hyphenationLang='en_US',embeddedHyphenation=1))
            _, h = title.wrap(column_width,frame_height)
            if h + 3 * BASELINE > frame_height: raise ValueError('The title is too long for the opening column.')
            title.drawOn(canvas,margin_x,margin_bottom+frame_height-h)
            if article.author:
                author = Paragraph(html.escape(article.author),styles['body']); _, ah=author.wrap(column_width,frame_height)
                author.drawOn(canvas,margin_x,margin_bottom+frame_height-h-BASELINE-ah)
    doc.addPageTemplates([
        PageTemplate('Opening',frames=[frame(margin_x+column_width+gutter,'opening-right')] if options.start_on_right else [frame(margin_x,'opening-left'),frame(margin_x+column_width+gutter,'opening-right')], onPage=opening,autoNextPageTemplate='Columns'),
        PageTemplate('Columns',frames=[frame(margin_x,'left'),frame(margin_x+column_width+gutter,'right')],onPage=decorate),
    ])
    source = article.source if article.source is not None else '\n\n'.join(('## ' if k in ('section','subhead') else '')+v for k,v in article.blocks)
    tokens = mistune.create_markdown(renderer='ast', plugins=['table','footnotes','strikethrough','task_lists'])(source)
    image_cache = {}; image_count = 0
    def image_node(node):
        children=node.get('children',[])
        if node['type'] != 'paragraph' or len(children)!=1: return None
        node=children[0]
        if node['type']=='link' and len(node.get('children',[]))==1: node=node['children'][0]
        return node if node['type']=='image' else None
    def figcaption_node(node):
        if node['type'] != 'block_html': return None
        match=re.fullmatch(r'\s*<figcaption(?:\s[^>]*)?>(.*?)</figcaption>\s*',node.get('raw',''),re.I|re.S)
        if not match: return None
        # A figcaption is the one supported HTML block. Strip nested markup and
        # escape its text before passing it to ReportLab.
        return html.escape(html.unescape(re.sub(r'<[^>]+>','',match.group(1))).strip())
    def flow(nodes, style='body', depth=0):
        nonlocal image_count
        nodes = [node for node in nodes if node["type"] != "blank_line"]
        result=[]; i=0
        while i < len(nodes):
            node=nodes[i]; kind=node['type']; children=node.get('children',[])
            image=image_node(node)
            if image:
                url=image['attrs']['url']
                caption=inline(image.get('children',[]))
                if re.fullmatch(r'(?:figure|image|photo|illustration|screenshot)(?:\s+\d+)?',re.sub(r'<[^>]+>','',caption).strip(),re.I): caption=''
                if i+1<len(nodes) and nodes[i+1]['type']=='paragraph':
                    candidate=inline(nodes[i+1].get('children',[]))
                    if re.match(r'^(?:<b>)?(?:Figure\s+\d+|Caption:|Photo\b|Image\b|Courtesy\b|Inka Essenhigh,|Moonlight,)',candidate,re.I):
                        caption=re.sub(r'^Caption:\s*','',candidate,flags=re.I);i+=1
                if i+1<len(nodes):
                    explicit_caption=figcaption_node(nodes[i+1])
                    if explicit_caption is not None:
                        caption=explicit_caption;i+=1
                # Drop linked duplicates emitted by article extractors after a caption.
                if i+1<len(nodes) and image_node(nodes[i+1]) and image_node(nodes[i+1])['attrs']['url']==url: i+=1
                if url not in image_cache:
                    image_count+=1
                    if image_count>40: raise ValueError('A document can contain at most 40 distinct figures.')
                    image_cache[url]=image_reader(url,options)
                result.append(GridFigure(image_cache[url],caption,styles['caption'],frame_height))
            elif kind == 'heading':
                content=inline(children)
                if content:
                    heading = Paragraph(content, styles['section'])
                    # Keep a heading with only the opening two lines of the next
                    # paragraph. ReportLab's keepWithNext groups the *whole*
                    # paragraph, which can leave most of a column empty when a
                    # long paragraph follows a heading near the column bottom.
                    next_node = nodes[i + 1] if i + 1 < len(nodes) else None
                    if next_node and next_node['type'] == 'paragraph' and not image_node(next_node):
                        next_content = inline(next_node.get('children', []))
                        mapping = next((path for prefix,path in (image_map or {}).items() if re.sub('<[^>]+>','',next_content).startswith(prefix)),None)
                        if next_content and not mapping:
                            paragraph = Paragraph(next_content, styles[style])
                            paragraph.wrap(column_width, frame_height)
                            parts = paragraph.split(column_width, 2 * BASELINE)
                            if parts:
                                result.append(KeepTogether([heading, parts[0]]))
                                result.extend(parts[1:])
                                i += 1
                            else:
                                result.append(heading)
                        else:
                            result.append(heading)
                    else:
                        result.append(heading)
            elif kind in ('paragraph','block_text'):
                content=inline(children)
                mapping=next((path for prefix,path in (image_map or {}).items() if re.sub('<[^>]+>','',content).startswith(prefix)),None)
                if mapping: result.append(GridFigure(image_reader(str(mapping),options),content,styles['caption'],frame_height))
                elif content: result.append(Paragraph(content,styles[style]))
            elif kind=='block_quote': result.extend(flow(children,'quote',depth+1))
            elif kind=='list':
                start=node.get('attrs',{}).get('start',1);ordered=node.get('attrs',{}).get('ordered',False)
                for number,item in enumerate(children,start):
                    items=flow(item.get('children',[]),style,depth+1)
                    marker=f'{number}.' if ordered else '•'
                    if item['type']=='task_list_item': marker='[x]' if item.get('attrs',{}).get('checked') else '[ ]'
                    if items and isinstance(items[0],Paragraph):
                        items[0].bulletText=marker
                        items[0].style=ParagraphStyle('list',parent=items[0].style,leftIndent=12*(depth+1),bulletIndent=12*depth)
                    result.extend(items)
            elif kind=='block_code':
                result.append(Paragraph(html.escape(node.get('raw','')).replace('\n','<br/>').replace('  ','&#160;&#160;'),styles['code']))
            elif kind=='table':
                rows=[]
                for group in children:
                    group_rows=[group] if group['type']=='table_head' else group.get('children',[])
                    for row in group_rows: rows.append([Paragraph(inline(cell.get('children',[])),styles['note']) for cell in row.get('children',[])])
                if rows:
                    table=Table(rows,colWidths=[column_width/len(rows[0])]*len(rows[0]),repeatRows=1,hAlign='LEFT')
                    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),4),('LINEBELOW',(0,0),(-1,0),0.4,INK)])); result.extend([table,Spacer(1,BASELINE)])
            elif kind=='footnotes':
                notes=[]
                for item in children:
                    paragraphs=flow(item.get('children',[]),'note')
                    if paragraphs and isinstance(paragraphs[0],Paragraph): paragraphs[0].bulletText=str(item['attrs']['index'])+'.'
                    notes.extend(paragraphs)
                heading=Paragraph('Notes',styles['section'])
                if notes and isinstance(notes[0],Paragraph):
                    first=notes[0]
                    first.wrap(column_width,frame_height)
                    parts=first.split(column_width,2*styles['note'].leading)
                    if parts:
                        result.append(KeepTogether([heading,parts[0]]))
                        result.extend(parts[1:])
                        result.extend(notes[1:])
                    else:
                        result.append(heading)
                        result.extend(notes)
                else:
                    result.append(heading)
                    result.extend(notes)
            elif kind=='block_html':
                raise ValueError('Raw HTML blocks are not supported. Use Markdown for figures, tables, and text.')
            i+=1
        return result
    story=[]
    if not options.start_on_right:
        story.append(Paragraph(html.escape(article.title),ParagraphStyle('title',fontName=regular,fontSize=28,leading=29.4,spaceAfter=BASELINE,hyphenationLang='en_US',embeddedHyphenation=1)))
        if article.author: story.append(Paragraph(html.escape(article.author),styles['body']))
    story.extend(flow(tokens))
    if not story: story=[Spacer(1,1)]
    doc.build(story)
    # Do not pad odd-length documents. A duplex printer naturally leaves the
    # reverse of the final sheet blank; embedding a synthetic PDF page only
    # creates an unwanted blank page in previews and exports.
    return len(PdfReader(str(output)).pages)


def main() -> int:
    parser=argparse.ArgumentParser(description='Typeset Markdown as a two-column PDF with embedded fonts.')
    parser.add_argument('input',type=Path);parser.add_argument('output',type=Path,nargs='?')
    parser.add_argument('--figure-map',type=Path)
    parser.add_argument('--title');parser.add_argument('--author')
    parser.add_argument('--page-size',choices=['letter','a4','half-letter'],default='letter')
    parser.add_argument('--typeface',choices=['sans','serif'],default='sans')
    parser.add_argument('--start-on-right',action=argparse.BooleanOptionalAction,default=True)
    parser.add_argument('--duplex',action=argparse.BooleanOptionalAction,default=True)
    parser.add_argument('--grayscale',action=argparse.BooleanOptionalAction,default=True)
    parser.add_argument('--midpoint',type=float,default=1.08)
    parser.add_argument('--web',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    output=args.output or Path('output/pdf')/f'{args.input.stem}-columns.pdf';output.parent.mkdir(parents=True,exist_ok=True)
    article=parse_article(args.input.read_text(encoding='utf-8'))
    if args.title is not None:article.title=args.title or article.title
    if args.author is not None:article.author=args.author
    image_map=json.loads(args.figure_map.read_text()) if args.figure_map else None
    count=render_article(article,output,image_map,RenderOptions(args.page_size,args.typeface,args.start_on_right,args.duplex,args.grayscale,args.midpoint,not args.web,args.input.resolve().parent))
    print(json.dumps({'output':str(output.resolve()),'pages':count}))
    return 0


if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,OSError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
