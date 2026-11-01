#!/usr/bin/env python3
"""ИрГУПС: оформление DOCX и проверка фактической вёрстки через Wordcraft.

Без аргументов — окно выбора файла. CLI: normokontrol.py input.docx --out DIR.
Не требует Codex, Word COM, сервера MCP или подключения к сети.
"""
from __future__ import annotations

import argparse
import copy
from collections import Counter
from contextlib import AbstractContextManager
from datetime import datetime
import hashlib
import html
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from urllib.parse import quote
from zipfile import ZipFile
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parent))
from irgups_data import prepare_metadata, REG_NUMBER_RE

FONT = "Times New Roman"
STAMP_FONT = "ISOCPEUR"
STAMP_SIZE = 9
FRAME_STROKE = 0.75  # Normokontrol.pdf §7.1.2, p.11.
MM = 72 / 25.4
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
SPECIAL = {"содержание", "введение", "заключение", "список использованных источников",
           "библиографический список", "список литературы", "аннотация", "нормативные ссылки", "обозначения и сокращения"}
CAPTION = re.compile(r"^(Таблица|Рисунок)\s+([А-ЯA-Z\d]+(?:\.\d+)*)\s*[–—-]", re.I)


def norm(text):
    return re.sub(r"\s+", " ", text.replace("\ufffc", "").replace("\u00a0", " ")).strip().casefold()


def byte_len(text):
    # Wordcraft's Pos.off and formatting run lengths are UTF-8 byte offsets.
    return len(text.encode("utf-8"))


def find_cli(explicit=None):
    candidates = [explicit, os.getenv("WORDCRAFT_CLI"), shutil.which("wordcraft-cli")]
    for base in (os.getenv("ProgramFiles"), os.getenv("LOCALAPPDATA")):
        if base:
            candidates.extend([str(Path(base) / "ArtCraft/WordCraft/wordcraft-cli.exe"),
                               str(Path(base) / "Programs/ArtCraft/WordCraft/wordcraft-cli.exe")])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise RuntimeError("Не найден wordcraft-cli. Установите Wordcraft или задайте --wordcraft ПУТЬ.")


class Wordcraft(AbstractContextManager):
    """Private headless MCP process; no changes to the user's open app/session."""
    def __init__(self, cli, timeout=60):
        self.timeout = timeout
        self.seq = 0
        self.responses = queue.Queue()
        self.proc = subprocess.Popen(
            [cli, "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._reader, daemon=True).start()
        self.rpc("initialize", {"protocolVersion": "2024-11-05",
                 "capabilities": {}, "clientInfo": {"name": "irgups-normokontrol", "version": "1.0"}})
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.proc.stdin.flush()

    def _reader(self):
        try:
            for line in self.proc.stdout:
                self.responses.put(json.loads(line))
        except Exception as error:
            self.responses.put(error)
        finally:
            self.responses.put(None)

    def rpc(self, method, params):
        self.seq += 1
        request = {"jsonrpc": "2.0", "id": self.seq, "method": method, "params": params}
        self.proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        while True:
            try:
                reply = self.responses.get(timeout=self.timeout)
            except queue.Empty:
                raise RuntimeError(f"Wordcraft не ответил за {self.timeout} секунд: {method}") from None
            if reply is None:
                raise RuntimeError("Wordcraft завершился до ответа.")
            if isinstance(reply, Exception):
                raise RuntimeError(f"Ошибка ответа Wordcraft: {reply}")
            if reply.get("id") != self.seq:
                continue
            if "error" in reply:
                raise RuntimeError(str(reply["error"]))
            return reply.get("result", {})

    def call(self, name, **arguments):
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})
        text = "\n".join(c["text"] for c in result.get("content", []) if c.get("type") == "text")
        if result.get("isError"):
            raise RuntimeError(f"Wordcraft ({name}): {text}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"Неизвестный формат ответа Wordcraft ({name}): {text[:300]}") from None

    def execute(self, command, **params):
        return self.call("execute", command=command, params=params)

    def batch(self, commands):
        if not commands:
            return []
        result = self.call("batch", commands=commands)
        for item in result:
            if not item.get("ok"):
                raise RuntimeError(f"Команда Wordcraft не выполнена: {item}")
        return [item.get("result") for item in result]

    def open(self, path):
        return self.call("open_document", path=str(path))

    def save(self, path):
        return self.call("save_document", path=str(path))

    def locate(self, path, off=0):
        result = self.batch([
            {"command": "caret.set", "params": {"pos": {"story": "body", "path": path, "off": off}}},
            {"command": "document.layout"}])[-1]
        caret = result["caret"]
        physical = caret["page"]
        return {"page": physical + 1, "number": result["pages"][physical]["number"],
                "x": caret["x"], "y": caret["y"], "h": caret["h"]}

    def break_before(self, index):
        self.batch([
            {"command": "caret.set", "params": {"pos": {"story": "body", "path": [index], "off": 0}}},
            {"command": "para.pageBreakBefore", "params": {"value": True}}])

    def __exit__(self, *args):
        if self.proc.stdin:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        if self.proc.stdout:
            self.proc.stdout.close()


def paragraphs(blocks, prefix=()):
    for index, block in enumerate(blocks):
        path = (*prefix, index)
        if block["kind"] == "para":
            yield list(path), block
        elif block["kind"] == "table":
            for ri, row in enumerate(block["rows"]):
                for ci, cell in enumerate(row["cells"]):
                    yield from paragraphs(cell["blocks"], (*path, ri, ci))


def heading_level(para, styles):
    text = norm(para.get("text", ""))
    if text in SPECIAL or re.fullmatch(r"приложение\s+[а-яa-z]", text):
        return 1
    if re.match(r"^\d+(?:\.\d+){0,3}\s+\S", text):
        return text.split()[0].count(".") + 1
    props = para.get("props", {})
    level = props.get("outlineLevel")
    style_id = props.get("style")
    seen = set()
    while level is None and style_id and style_id not in seen:
        seen.add(style_id)
        style = next((s for s in styles.get("styles", []) if s.get("id") == style_id), {}) if isinstance(styles, dict) else {}
        level = style.get("para", {}).get("outlineLevel")
        style_id = style.get("basedOn")
    return level + 1 if isinstance(level, int) and level < 9 else None


def has_image(block):
    if block.get("kind") == "table":
        return any(has_image(p) for _, p in paragraphs([block]))
    return any(o.get("type") in {"image", "shape", "textBox", "chart", "smartArt", "group"}
               for o in block.get("objects", []))


def font(para, size):
    props = {"font": FONT, "fontCs": FONT, "fontEa": FONT, "size": float(size),
             "sizeCs": float(size), "bold": False, "boldCs": False, "color": {"Rgb": [0, 0, 0]}}
    para.setdefault("mark", {}).update(props)
    for run in para.get("runs", []):
        run.setdefault("props", {}).update(props)


def next_block(body, index):
    for n in range(index + 1, len(body)):
        b = body[n]
        if b["kind"] != "para" or b.get("text", "").strip():
            return n, b
    return None, None


def detect_toc(body):
    return next(iter(detect_tocs(body)), None)


def auto_toc_text(body):
    """Strip only generated TOC field results, retaining text outside the field."""
    stack, result = [], {}
    generated = False
    for path, para in paragraphs(body):
        if generated and re.fullmatch(r'TOC[1-9]', para.get('props', {}).get('style', ''), re.I):
            result[tuple(path)] = ''
            continue
        generated = False
        objects = iter(para.get('objects', []))
        outside = []
        touched = any(stack)
        for char in para.get('text', ''):
            obj = next(objects, {}) if char == '\ufffc' else {}
            if obj.get('type') == 'field' and re.match(r'^TOC(?:\s|$)', obj.get('instr', ''), re.I):
                touched = generated = True
                continue
            if obj.get('type') == 'fieldStart':
                is_toc = bool(re.match(r'^TOC(?:\s|$)', obj.get('instr', ''), re.I))
                stack.append(is_toc or any(stack))
                touched |= any(stack)
                if any(stack):
                    continue
            elif obj.get('type') == 'fieldEnd' and stack:
                was_toc = stack.pop()
                if was_toc:
                    continue
            if not any(stack):
                outside.append(char)
        if touched:
            result[tuple(path)] = ''.join(outside)
    if any(stack):
        raise ValueError('Автооглавление имеет незакрытое поле TOC. Пересоздайте оглавление в редакторе и сохраните документ.')
    return result


def detect_tocs(body):
    found = []
    active = False
    for i, block in enumerate(body):
        if block["kind"] == "para":
            text = norm(block.get("text", ""))
            if text:
                active = text == "содержание"
        elif block["kind"] == "table":
            texts = [norm(p.get("text", "")) for _, p in paragraphs([block])]
            active = active or "содержание" in texts
            if active and any(2 <= len(r["cells"]) <= 4 for r in block.get("rows", [])):
                found.append(i)
            else:
                active = False
    return found


def table_caption(body, index):
    for i in range(index - 1, max(-1, index - 4), -1):
        b = body[i]
        if b["kind"] != "para":
            break
        if not b.get("text", "").strip():
            continue
        match = CAPTION.match(b["text"])
        return i if match and match.group(1).casefold() == "таблица" else None
    return None


def normalize_model(model, mode, changes):
    from list_formatting import normalize as normalize_list
    list_cache = {}
    body, styles = model["body"], model.get("styles", {})
    toc = detect_toc(body)
    start = body_start(model)
    auto_toc = auto_toc_text(body)
    refs = next((i for i, p in enumerate(body) if p["kind"] == "para" and
                 norm(p.get("text", "")) in {"список использованных источников", "библиографический список"}), None)
    for i, block in enumerate(body):
        if (i,) in auto_toc:
            continue  # Generated field entries are not document headings.
        if i < start:
            # Title typography and the signature table are taken from the user's document.
            continue
        if block["kind"] == "para":
            if not block.get("text", "").strip():
                continue  # Preserve the user's deliberate title/page spacing.
            level = heading_level(block, styles)
            props = block.setdefault("props", {})
            font(block, 14)
            props.update({"lineSpacing": {"rule": "multiple", "value": 1.5}, "widowControl": True})
            if not has_image(block):
                props.update({'spaceBefore': 0.0, 'spaceAfter': 0.0,
                              'spaceBeforeAuto': False, 'spaceAfterAuto': False})
                if not effective_para(model, block).get('numbering'):
                    props.update({'indentLeft': 0.0, 'indentRight': 0.0})
                trim_manual_indent(block)
            if level:
                props.update({"keepNext": True, "keepLines": True, "suppressHyphens": True})
                centered = effective_para(model, block).get('align') == 'center'
                props.update({'align': 'center' if centered else 'left',
                              'indentFirst': 0.0 if centered else 10 * MM})
                if level == 1 and i > start and norm(block["text"]) != "содержание":
                    props["pageBreakBefore"] = True
            elif CAPTION.match(block.get("text", "")):
                match = CAPTION.match(block["text"])
                props.update({"indentFirst": 0.0, "keepLines": True,
                              "align": "center" if match.group(1).casefold() == "рисунок" else "left"})
                if match.group(1).casefold() == "таблица":
                    props["keepNext"] = True
            elif not has_image(block):
                props.update({"align": "justify", "indentFirst": (10 if mode == "full" else 12.5) * MM,
                              "spaceAfter": 0.0})
                if "\n" in block["text"] and re.search(
                        r"(?:^|\n)\s*(?:for |done\b|if |fi\b|sudo |[A-Za-z_][A-Za-z_0-9]*=|-\w)", block["text"]):
                    # Justifying manual line breaks stretches shell commands across the page.
                    props.update({"align": "left", "indentFirst": 0.0, "suppressHyphens": True})
            else:
                # Changing an image paragraph's line height can clip its image.
                props["lineSpacing"] = {"rule": "multiple", "value": 1.0}
                props["keepNext"] = True
            normalize_list(model, block, level, list_cache)
        elif block["kind"] == "table":
            caption = table_caption(body, i)
            data_table = caption is not None
            size = 12 if data_table else 14
            for ri, row in enumerate(block["rows"]):
                rp = row.setdefault("props", {})
                rp["cantSplit"] = True
                if data_table:
                    rp.update({"height": max(rp.get("height") or 0, 8 * MM), "heightRule": "atLeast"})
                    if mode == "compact":
                        rp["header"] = ri == 0
                for cell in row["cells"]:
                    for _, para in paragraphs(cell["blocks"]):
                        font(para, size)
                        pp = para.setdefault("props", {})
                        pp["lineSpacing"] = {"rule": "multiple", "value": 1.0 if data_table else 1.5}
                        pp["spaceAfter"] = 0.0
                        if data_table:
                            pp["keepNext"] = mode == "full" and ri < len(block["rows"]) - 1
            if i in detect_tocs(body) or (refs is not None and i > refs and not any(
                    b["kind"] == "para" and re.fullmatch(r"приложение\s+[а-яa-z]", norm(b.get("text", "")))
                    for b in body[refs + 1:i])):
                edges = {edge: {"style": "none", "width": 0.0} for edge in
                         ("top", "bottom", "left", "right", "between", "insideH", "insideV")}
                block.setdefault("props", {})["borders"] = edges
                for row in block["rows"]:
                    for cell in row["cells"]:
                        cell.setdefault("props", {})["borders"] = edges.copy()
    if mode == "compact":
        if looks_framed(model):
            raise ValueError("В документе обнаружены штампы. Выберите полный профиль: обычные поля сместят текст относительно рамки.")
        sections = [model.get("lastSection", {})]
        sections.extend(b["section"] for b in body if b.get("section"))
        part_id = max((int(key) for key in model["parts"]), default=0) + 1
        page_para = {"kind": "para", "text": "\ufffc", "runs": [{"len": 3, "props": {}}],
                     "props": {"align": "center", "spaceAfter": 0.0},
                     "objects": [{"type": "field", "instr": "PAGE", "result": "1", "locked": False}]}
        font(page_para, 14)
        model["parts"][str(part_id)] = {"kind": "footer", "blocks": [page_para]}
        for section in sections:
            section.update({"marginLeft": 30 * MM, "marginRight": 15 * MM,
                            "marginTop": 20 * MM, "marginBottom": 20 * MM,
                            "pageW": (297 if section.get("landscape") else 210) * MM,
                            "pageH": (210 if section.get("landscape") else 297) * MM,
                            "footers": {"default": part_id, "first": part_id, "even": part_id}})
    changes.append("Шрифт и интервалы основного текста, заголовки, строки таблиц приведены к выбранному профилю. "
                   "Титульник, колонтитулы, рамки и штампы сохранены из исходника.")
    if mode == "compact":
        changes[-1] = ("Шрифт, интервалы, поля A4 и таблицы приведены к обычному учебному профилю; "
                       "внизу страниц добавлено поле PAGE по центру.")


def looks_framed(model):
    text = " ".join(p.get("text", "") for part in model.get("parts", {}).values()
                    for _, p in paragraphs(part.get("blocks", [])))
    return bool(re.search(r"(?:КР|КП|ПП|УП|ОП|ЛР|РГР|ДР|ДП)\.\d+", text) or
                ("Изм." in text and "Лист" in text))


def apply_frames(model, metadata, changes, issues):
    """Unscaled, page-anchored geometry: one outer rectangle, one stroke width.

    Millimetre coordinates share the very same endpoints. No imported group transforms
    or nearly overlapping line segments are used in the frame or stamp.
    """
    body = model["body"]
    old_texts = [" ".join(p.get("text", "") for _, p in paragraphs(part.get("blocks", [])))
                 for part in model["parts"].values()]
    all_text = "\n".join(b.get("text", "") for b in body) + "\n" + "\n".join(old_texts)
    code = REG_NUMBER_RE.search(all_text)
    group = re.search(r"[А-ЯA-Z]{2,5}\.\d+-\d{2}-\d+", all_text)
    values = {"code": code.group() if code else "", "group": group.group() if group else "",
              "author": "", "supervisor": "", "stamp_title": ""}
    for labels, key in ((("Разраб.",), "author"), (("Провер.", "Пров."), "supervisor")):
        for i, text in enumerate(old_texts[:-1]):
            if text.strip() in labels:
                values[key] = old_texts[i + 1].strip()
    for i, text in enumerate(old_texts[:-2]):
        if text.strip() in {"Утверд.", "Утв."}:
            for raw in old_texts[i + 2:i + 4]:
                candidate = raw.strip()
                if candidate and candidate not in {"Лит.", "Лист", "Листов"} and not re.match(r"^(КР|КП|ПП|УП|ОП|ЛР|РГР|ДР|ДП)\.", candidate):
                    values["stamp_title"] = candidate
                    break
    # Title signature table is used when the input has no stamps yet.
    for b in body:
        if b["kind"] == "table" and len(b.get("rows", [])) == 1 and len(b["rows"][0]["cells"]) == 2:
            for ci, key in ((0, "author"), (1, "supervisor")):
                texts = [p.get("text", "").strip() for _, p in paragraphs(b["rows"][0]["cells"][ci]["blocks"])]
                fio = next((t for t in texts if re.search(r"[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.", t)), "")
                if fio:
                    values[key] = fio
            break
    values.update({k: v for k, v in (metadata or {}).items() if v})
    if not values["stamp_title"]:
        values["stamp_title"] = values.get("title", "")
    for key, label in (("code", "шифр"), ("author", "автор"), ("supervisor", "руководитель"), ("group", "группа")):
        if not values[key]:
            add_issue(issues, "stamp-details", f"В штампе не заполнено поле «{label}»: укажите его в окне запуска или параметрах скрипта.")
    part_id = max((int(k) for k in model["parts"]), default=0)
    def part(kind, blocks):
        nonlocal part_id
        part_id += 1
        model["parts"][str(part_id)] = {"kind": kind, "blocks": blocks}
        if kind == "textBox":
            model["parts"][str(part_id)]["body"] = {"inset": [0, 0, 0, 0], "anchor": "center"}
        return part_id
    def text_part(text, size=STAMP_SIZE, field=None):
        p = {"kind": "para", "text": "\ufffc" if field else text,
             "runs": [{"len": 3 if field else byte_len(text), "props": {}}],
             "props": {"align": "center", "spaceBefore": 0.0, "spaceAfter": 0.0,
                       "lineSpacing": {"rule": "multiple", "value": 1.0}}}
        font(p, size)
        p['mark'].update(font=STAMP_FONT,fontCs=STAMP_FONT,fontEa=STAMP_FONT)
        for r in p["runs"]:
            r['props'].update(font=STAMP_FONT,fontCs=STAMP_FONT,fontEa=STAMP_FONT)
            r["props"]["italic"] = True
        if field:
            p["objects"] = [{"type": "field", "instr": field, "result": "1", "locked": False}]
        return part("textBox", [p])
    blank_header, blank_footer = part("header", []), part("footer", [])
    def header(width, height, big):
        objects = []
        left, top, right, bottom = 20 * MM, 5 * MM, width - 5 * MM, height - 5 * MM
        sy = bottom - (40 if big else 15) * MM
        # The 185 mm stamp is at the lower right on wider sheets.
        sx = right - 185 * MM
        def shape(kind, x, y, w, h, story=None, stroke=True):
            objects.append({"type": "shape", "kind": kind, "w": w, "h": h,
                            "fill": None, "stroke": [0, 0, 0] if stroke else None,
                            "stroke_width": FRAME_STROKE,
                            "float": {"wrap": "inFrontOfText", "hRel": "page", "vRel": "page",
                                      "x": x, "y": y, "dist": 0.0}, "story": story})
        def line(x1, y1, x2, y2):
            shape("line", sx + x1 * MM, sy + y1 * MM, (x2 - x1) * MM, (y2 - y1) * MM)
        def label(text, x, y, w, h, size=STAMP_SIZE, field=None):
            shape("rectangle", sx + x * MM + .5, sy + y * MM + .5,
                  w * MM - 1, h * MM - 1, text_part(text, size, field), stroke=False)
        shape("rectangle", left, top, right - left, bottom - top)
        # The outer rectangle already draws the stamp's bottom/right edges.
        line(0, 0, 185, 0)
        if sx > left + .1:
            line(0, 0, 0, 40 if big else 15)
        line(65, 0, 65, 40 if big else 15)
        for x in (7, 17, 40, 55):
            line(x, 0, x, 15)
        for y in ((5, 10, 15) if big else (5, 10)):
            line(0, y, 65, y)
        for text, x, w in (("Изм.", 0, 7), ("Лист", 7, 10), ("№ докум.", 17, 23), ("Подпись", 40, 15), ("Дата", 55, 10)):
            label(text, x, 10, w, 5)
        if big:
            # Fig. И.3, Normokontrol.pdf p.44: TEXT document title sheet, 185 × 40 mm.
            # Main title: 70 mm; right block: 50 mm = 15 + 15 + 20 mm.
            line(65, 15, 185, 15)
            line(135, 15, 135, 40)
            line(135, 25, 185, 25)
            line(135, 20, 185, 20)
            for x in (150, 165):
                line(x, 15, x, 25)
            for x in (140,145):
                line(x,20,x,25)
            for y in (20, 25, 30, 35):
                line(0, y, 65, y)
            for x in (17, 40, 55):
                line(x, 15, x, 40)
            for i, (title, name) in enumerate((("Разраб.", values["author"]), ("Пров.", values["supervisor"]), ("", ""), ("Н.контр.", ""), ("Утв.", ""))):
                label(title, 0, 15 + i * 5, 17, 5)
                label(name, 17, 15 + i * 5, 23, 5)
            label(values["code"], 65, 0, 120, 15)
            label(values["stamp_title"], 65, 15, 70, 25)
            for title, x, w in (("Литера", 135, 15), ("Лист", 150, 15), ("Листов", 165, 20)):
                label(title, x, 15, w, 5)
            label("", 150, 20, 15, 5, STAMP_SIZE, "PAGE")
            label("", 165, 20, 20, 5, STAMP_SIZE, "NUMPAGES")
            label("ИрГУПС\n" + values["group"], 135, 25, 50, 15)
        else:
            # Fig. И.4: 185 × 15 mm, 7 mm label and 8 mm page-number cell.
            line(175, 0, 175, 15)
            line(175, 7, 185, 7)
            label(values["code"], 65, 0, 110, 15)
            label("Лист", 175, 0, 10, 7)
            label("", 175, 7, 10, 8, STAMP_SIZE, "PAGE")
        p = {"kind": "para", "text": "\ufffc" * len(objects),
             "runs": [{"len": 3 * len(objects), "props": {"size": 1.0}}],
             "mark": {"size": 1.0},
             "props": {"spaceBefore": 0.0, "spaceAfter": 0.0, "lineSpacing": {"rule": "exactly", "value": 1.0}}, "objects": objects}
        return part("header", [p])
    start = body_start(model)
    if start and body[start - 1]["kind"] != "para":
        body.insert(start, {"kind": "para", "text": "", "runs": [], "props": {"lineSpacing": {"rule": "exactly", "value": 1.0}}})
        start += 1
    if start:
        title = copy.deepcopy(model["lastSection"])
        title.update({"headers": {"default": blank_header, "first": blank_header, "even": blank_header},
                      "footers": {"default": blank_footer, "first": blank_footer, "even": blank_footer}, "titlePage": False,
                      "header": 0.0, "footer": 0.0, "pageW": 210 * MM, "pageH": 297 * MM,
                      "marginTop": 18.15, "marginBottom": 85.05, "marginLeft": 77.95, "marginRight": 28.35})
        body[start - 1]["section"] = title
    toc_heading = next((i for i,b in enumerate(body) if b['kind']=='para' and norm(b.get('text',''))=='содержание'),None)
    if toc_heading is None:
        toc_heading = detect_toc(body)
    if toc_heading is not None and toc_heading > start:
        if body[toc_heading-1]['kind'] != 'para':
            body.insert(toc_heading, {'kind':'para','text':'','runs':[], 'mark':{'size':1.0}})
            toc_heading += 1
        body[toc_heading-1]['section'] = copy.deepcopy(model['lastSection'])
    sections = [(i, b["section"]) for i, b in enumerate(body) if b.get("section")]
    sections.append((len(body), model["lastSection"]))
    section_start = 0
    for end, section in sections:
        if start and end < start:
            section_start = end + 1
            continue
        w, h = (297 * MM, 210 * MM) if section.get("landscape") else (210 * MM, 297 * MM)
        small = header(w, h, False)
        big = header(w, h, True) if section_start == toc_heading else small
        section.update({"headers": {"default": small, "first": big, "even": small},
                        "footers": {"default": blank_footer, "first": blank_footer, "even": blank_footer},
                        "titlePage": True, "marginLeft": 27.5 * MM, "marginRight": 10 * MM,
                        "marginTop": max(section.get("marginTop", 0), 10 * MM),
                        "marginBottom": 30 * MM, "header": 0.0, "footer": 0.0, "start": "nextPage", "pageW": w, "pageH": h})
        section_start = end + 1
    # Discard unused old header/textbox stories: stale people's details must not survive in the package.
    reachable = set()
    def visit(value):
        if isinstance(value, dict):
            for k, v in value.items():
                if k == "story" and isinstance(v, int) and str(v) in model["parts"] and v not in reachable:
                    reachable.add(v)
                    visit(model["parts"][str(v)])
                elif k in ("headers", "footers") and isinstance(v, dict):
                    for pid in v.values():
                        if pid is not None and pid not in reachable:
                            reachable.add(pid)
                            visit(model["parts"][str(pid)])
                else:
                    visit(v)
        elif isinstance(value, list):
            for v in value:
                visit(v)
    visit(body)
    visit(model["lastSection"])
    for saved_part in model["parts"].values():
        if saved_part["kind"] not in {"header", "footer", "textBox"}:
            visit(saved_part)
    model["parts"] = {k: v for k, v in model["parts"].items() if int(k) in reachable or v["kind"] not in {"header", "footer", "textBox"}}
    changes.append("Построены штампы текстовых документов по И.3 и И.4 (стр.44): ISOCPEUR 9 пт, выравнивание по центру, линии 0,75 пт; титульник без рамки.")


def add_templates(model, toc_template, bibliography, changes, toc_entries=None, bibliography_entries=None):
    body = model["body"]
    templates = json.loads((Path(__file__).resolve().parent.parent / "assets" / "course-templates.json").read_text(encoding="utf-8"))
    def heading(text):
        p = {"kind": "para", "text": text, "runs": [{"len": byte_len(text), "props": {}}],
             "props": {"outlineLevel": 0, "align": "center", "keepNext": True,
                       "pageBreakBefore": True, "spaceAfter": 21.0}}
        font(p, 14)
        return p
    def table(widths, count):
        edges = {e: {"style": "none", "width": 0.0} for e in ("top", "bottom", "left", "right", "between", "insideH", "insideV")}
        return {"kind": "table", "props": {"borders": edges, "width": sum(widths)}, "grid": widths,
                "rows": [{"props": {"height": (30 if len(widths) == 1 else 8) * MM,
                                    "heightRule": "atLeast", "cantSplit": True},
                          "cells": [{"props": {"width": width, "borders": edges, "span": 1, "vmerge": "none"},
                                     "blocks": [{"kind": "para", "text": "", "runs": [], "mark": {"font": FONT, "size": 14.0},
                                                 "props": {"spaceAfter": 0.0}}]} for width in widths]} for _ in range(count)]}
    if toc_template or toc_entries:
        index = next((i for i, b in enumerate(body) if b["kind"] == "para" and norm(b.get("text", "")) == "содержание"), None)
        if index is None:
            index = body_start(model)
            body.insert(index, heading("Содержание"))
        if index + 1 >= len(body) or body[index + 1]["kind"] != "table":
            body.insert(index + 1, copy.deepcopy(templates["toc"]))
            changes.append("Добавлена пустая таблица содержания из курсача (15 строк, четыре столбца).")
        if toc_entries:
            target = body[index + 1]
            rows = []
            for entry in toc_entries:
                match = re.match(r"^(\d+(?:\.\d+)*)\s+(.+)$", entry.strip())
                row = copy.deepcopy(templates["toc"]["rows"][0])
                for ci, value in enumerate(("", match.group(1) if match else "", match.group(2) if match else entry.strip(), "")):
                    p = row["cells"][ci]["blocks"][0]
                    p["text"] = value
                    p["runs"] = [{"len": byte_len(value), "props": {"font": FONT, "size": 14.0}}]
                rows.append(row)
            target["rows"] = rows
            changes.append("Содержание заполнено введёнными строками; страницы пересчитаны для найденных заголовков.")
    if bibliography or bibliography_entries:
        aliases = {"список использованных источников", "библиографический список", "список литературы"}
        index = next((i for i, b in enumerate(body) if b["kind"] == "para" and norm(b.get("text", "")) in aliases), None)
        if index is None:
            index = len(body)
            body.append(heading("Список использованных источников"))
        if index + 1 >= len(body) or body[index + 1]["kind"] != "table":
            body.insert(index + 1, copy.deepcopy(templates["bibliography"]))
            changes.append("Добавлена пустая таблица источников из курсача (25 строк, два столбца).")
        if bibliography_entries:
            rows = []
            for n, entry in enumerate(bibliography_entries, 1):
                row = copy.deepcopy(templates["bibliography"]["rows"][0])
                for ci, value in enumerate((str(n), entry.strip())):
                    p = row["cells"][ci]["blocks"][0]
                    p["text"] = value
                    p["runs"] = [{"len": byte_len(value), "props": {"font": FONT, "size": 14.0}}]
                rows.append(row)
            body[index + 1]["rows"] = rows
            changes.append("Источники помещены в таблицу из курсача; номера без точки, описания сохранены без выдумывания данных.")


def body_start(model):
    body = model["body"]
    heading = next((i for i, b in enumerate(body) if b["kind"] == "para" and
                    (norm(b.get("text", "")) in SPECIAL or heading_level(b, model.get("styles", {})))), None)
    toc = detect_toc(body)
    if toc is not None:
        return min(heading, toc) if heading is not None else toc
    if heading is not None:
        return heading
    return next((i + 1 for i, b in enumerate(body[:-1]) if b.get("section")), 0)


def fill_cover(model, metadata, changes):
    metadata = {k: v for k, v in (metadata or {}).items() if v}
    body = model["body"]
    start = body_start(model)
    fresh = start == 0
    if fresh:
        template = json.loads((Path(__file__).resolve().parent.parent / "assets" / "course-templates.json").read_text(encoding="utf-8"))
        cover = copy.deepcopy(template["title"])
        for _, paragraph in paragraphs(cover):
            if paragraph.get("text", "").strip():
                font(paragraph, 14)
        cover[-1]["section"] = copy.deepcopy(model["lastSection"])
        body[:0] = cover
        start = len(cover)
        # The user's two manual spacers depend on the source document's styles.
        # In a new document reserve the signature table's height, without two extra 36 pt gaps.
        for p in body[14:16]:
            p.setdefault("props", {}).update({"spaceBefore": 0.0, "spaceAfter": 0.0,
                                              "lineSpacing": {"rule": "exactly", "value": 1.0}})
            p["mark"] = {"font": FONT, "size": 1.0}
        changes.append("Добавлен титульный лист из курсача; необязательные реквизиты без значений оставлены пустыми.")
    def replace(p, text):
        props = copy.deepcopy((p.get("runs") or [{"props": {}}])[0].get("props", {}))
        p["text"] = text
        p["runs"] = [{"len": byte_len(text), "props": props}]
        p.pop("objects", None)
        font(p, 14)
    if fresh:
        for index, key, prefix in ((5, "university", ""), (6, "university_short", ""), (7, "faculty", "Факультет "), (8, "department", "Кафедра ")):
            if metadata.get(key):
                value = metadata[key]
                if key == "university": value = '«' + value + '»'
                if key == "university_short": value = '(' + value + ')'
                if key in {"faculty", "department"}: value = '«' + value + '»'
                replace(body[index], prefix + value)
            elif key in {"faculty", "department"}:
                replace(body[index], prefix + '____________________')
        for index, key in ((9, "work_type"), (10, "discipline"), (11, "title"), (12, "code")):
            value = metadata.get(key, "")
            replace(body[index], f"по дисциплине «{value}»" if key == "discipline" and value else value)
        cells = body[13]["rows"][0]["cells"]
        for ci, pi, key in ((0, 1, "group"), (0, 2, "author"), (1, 1, "supervisor_title"), (1, 2, "supervisor")):
            value = metadata.get(key, "")
            replace(cells[ci]["blocks"][pi], f"студент гр. {value}" if key == "group" and value else value)
        replace(body[16], ", ".join(metadata[k] for k in ("city", "year") if metadata.get(k)))
    elif metadata:
        cover = body[:start]
        discipline_index = next((i for i, b in enumerate(cover) if b["kind"] == "para" and b.get("text", "").startswith("по дисциплине")), None)
        for cover_index, b in enumerate(cover):
            if b["kind"] == "para":
                t = b.get("text", "").replace("\ufffc", "").strip()
                for key, prefix in (("faculty", "Факультет"), ("department", "Кафедра")):
                    if metadata.get(key) and t.startswith(prefix):
                        replace(b, prefix + " «" + metadata[key] + "»")
                if metadata.get("university") and cover_index < 9 and "университет" in t.casefold():
                    replace(b, '«' + metadata["university"] + '»')
                if metadata.get("university_short") and t.startswith("(ФГБОУ"):
                    replace(b, '(' + metadata["university_short"] + ')')
                if metadata.get("work_type") and re.match(r"^(КУРСОВАЯ|КУРСОВОЙ|ОТЧ[ЕЁ]Т|ЛАБОРАТОРНАЯ|РЕФЕРАТ)", t, re.I):
                    replace(b, metadata["work_type"])
                if metadata.get("code") and REG_NUMBER_RE.match(t):
                    replace(b, metadata["code"])
                city_year = re.fullmatch(r'([А-ЯЁ][А-Яа-яЁё .-]*?)[,\s]+((?:19|20)\d{2})(?:\s*г\.?)?', t)
                if city_year and (metadata.get('city') or metadata.get('year')):
                    # Keep leading Word object markers and their attached objects.
                    raw = b.get('text', '')
                    prefix = raw[:raw.find(city_year.group(1))]
                    objects = copy.deepcopy(b.get('objects'))
                    replace(b, prefix + metadata.get('city', city_year.group(1)) + ', ' + metadata.get('year', city_year.group(2)))
                    if objects is not None:
                        b['objects'] = objects
            if b["kind"] == "table" and len(b.get("rows", [])) == 1 and len(b["rows"][0]["cells"]) == 2:
                cells = b["rows"][0]["cells"]
                for ci, pi, key in ((0, 1, "group"), (0, 2, "author"), (1, 1, "supervisor_title"), (1, 2, "supervisor")):
                    if metadata.get(key) and len(cells[ci]["blocks"]) > pi:
                        replace(cells[ci]["blocks"][pi], f"студент гр. {metadata[key]}" if key == "group" else metadata[key])
        if discipline_index is not None:
            if metadata.get("discipline"):
                replace(body[discipline_index], f"по дисциплине «{metadata['discipline']}»")
            if metadata.get("title") and discipline_index + 1 < start and body[discipline_index + 1]["kind"] == "para":
                replace(body[discipline_index + 1], metadata["title"])
        changes.append("Титульник заполнен только по указанным необязательным полям; остальные значения сохранены.")
    if metadata.get("year"):
        for _, p in paragraphs(body[:start]):
            if "____ г." in p.get("text", ""):
                replace(p, p["text"].replace("____ г.", metadata["year"] + " г."))
    if metadata.get("approval") and not any('К ЗАЩИТЕ ДОПУСКАЮ' in p.get('text','') for _,p in paragraphs(body[:start])):
        department_index = next((i for i,b in enumerate(body[:start]) if b['kind']=='para' and b.get('text','').startswith('Кафедра')), None)
        if department_index is not None:
            body[department_index].setdefault('props',{})['spaceAfter'] = 6.0
            lines = ['К ЗАЩИТЕ ДОПУСКАЮ', metadata.get('approval_title',''), metadata.get('approval_person',''), '(дата, подпись)']
            block={'kind':'para','text':'\n'.join(lines),'runs':[], 'props':{'align':'right','spaceAfter':6.0,'lineSpacing':{'rule':'multiple','value':1.0}}}
            block['runs']=[{'len':byte_len(block['text']),'props':{}}]
            font(block,14)
            body.insert(department_index+1,block)
            changes.append('Добавлен необязательный гриф допуска к защите (§6.2д). ФИО и регалии взяты только из ввода.')


def add_optional_sections(model, selected, changes):
    selected=set(selected or ())
    labels={'annotation':'Аннотация','normative':'Нормативные ссылки','abbreviations':'Обозначения и сокращения'}
    unknown=selected-labels.keys()
    if unknown:
        raise ValueError('Неизвестные заготовки разделов: '+', '.join(sorted(unknown)))
    body=model['body']
    for key in ('annotation','normative','abbreviations'):
        if key not in selected or any(b['kind']=='para' and norm(b.get('text',''))==norm(labels[key]) for b in body):
            continue
        if key=='annotation':
            index=body_start(model)
        else:
            index=next((i for i,b in enumerate(body) if b['kind']=='para' and norm(b.get('text',''))=='введение'),None)
            if index is None:
                toc=detect_toc(body)
                index=toc+1 if toc is not None else body_start(model)
            if key=='abbreviations':
                prior=next((i for i,b in enumerate(body) if b['kind']=='para' and norm(b.get('text',''))=='нормативные ссылки'),None)
                if prior is not None:
                    index=max(index,prior+2)
        text=labels[key]
        p={'kind':'para','text':text,'runs':[{'len':byte_len(text),'props':{}}],
           'props':{'outlineLevel':0,'align':'center','pageBreakBefore':True,'keepNext':True,'spaceAfter':21.0}}
        font(p,14)
        body[index:index]=[p,{'kind':'para','text':'','runs':[],'mark':{'font':FONT,'size':14.0}}]
        changes.append(f'Добавлена пустая заготовка «{text}» (§6.1); содержание раздела не выдумывалось.')


def inventory(path):
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
        text = Counter(t.text or "" for t in root.findall(".//w:t", NS))
        media = Counter(hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()
                        if name.startswith("word/media/") and not name.endswith("/"))
        return {"text": text, "media": media, "tables": len(root.findall(".//w:tbl", NS)),
                "sections": len(root.findall(".//w:sectPr", NS)),
                "revisions": bool(root.findall(".//w:ins", NS) or root.findall(".//w:del", NS)),
                "signed": any("signature" in name.casefold() for name in archive.namelist())}


def stable_text(model, toc):
    # Exclude generated TOC page cells and field results; preserve everything else including duplicate text.
    result = []
    toc_tables = set(detect_tocs(model["body"]))
    auto_toc = auto_toc_text(model['body'])
    for path, para in paragraphs(model["body"]):
        if tuple(path) in auto_toc:
            if auto_toc[tuple(path)]:
                result.append(auto_toc[tuple(path)])
            continue
        if path[0] in toc_tables and len(path) > 2:
            row = model["body"][path[0]]["rows"][path[1]]
            if len(row["cells"]) > 1 and path[2] == len(row["cells"]) - 1:
                continue
        if para.get("fields"):
            # Page/REF results can legitimately change. Retain a count and report it separately.
            continue
        text = para.get('text', '')
        objects = iter(para.get('objects', []))
        text = ''.join(c for c in text if c != '\ufffc' or next(objects, {}).get('type') not in {'bookmarkStart', 'bookmarkEnd'})
        if not para.get('objects') and not para.get('fields') and '\n' not in text:
            text = text.lstrip(' \t\u00a0')
        if text:
            result.append(text)
    return result


def table_positions(wc, index, table):
    rows = table.get("rows", [])
    if not rows:
        return []
    positions = []
    # First row establishes the beginning; every last-row cell covers uneven row content.
    for ri in sorted({0, len(rows) - 1}):
        for ci, cell in enumerate(rows[ri]["cells"]):
            ps = list(paragraphs(cell["blocks"], (index, ri, ci)))
            if ps:
                path, para = ps[0] if ri == 0 else ps[-1]
                off = 0 if ri == 0 else byte_len(para.get("text", ""))
                positions.append(wc.locate(path, off))
    return positions


def repair_layout(wc, model, mode, changes, issues, do_fix=True):
    body = model["body"]
    forced = set()
    for pass_no in range(4):
        changed = False
        for i, table in enumerate(body):
            if table["kind"] != "table":
                continue
            caption = table_caption(body, i)
            if caption is None:
                continue  # TOC, bibliography and title/layout tables may span pages.
            positions = table_positions(wc, i, table)
            if not positions:
                continue
            caption_pos = wc.locate([caption])
            pages = {p["page"] for p in positions}
            split = len(pages) > 1
            detached = caption_pos["page"] != min(pages)
            if detached or (mode == "full" and split):
                if do_fix and caption not in forced:
                    wc.break_before(caption)
                    forced.add(caption)
                    changes.append(f"Явный перенос перед «{body[caption]['text']}» по фактической вёрстке.")
                    changed = True
                elif not changed:
                    why = "занимает несколько страниц; требуется деление по смыслу" if split else "оторвана от названия"
                    add_issue(issues, "table-layout", f"{body[caption]['text']}: таблица {why}.", caption_pos["page"])
        if not changed:
            break
    # Figure paragraphs: don't detach captions from directly preceding inline images.
    for i, block in enumerate(body):
        if block["kind"] != "para" or not re.match(r"^Рисунок\s", block.get("text", ""), re.I):
            continue
        previous = body[i - 1] if i else None
        if previous and previous["kind"] == "para" and has_image(previous):
            image_pos, caption_pos = wc.locate([i - 1]), wc.locate([i])
            if image_pos["page"] != caption_pos["page"]:
                if do_fix:
                    wc.break_before(i - 1)
                    changes.append(f"Рисунок перенесён вместе с подписью «{block['text']}».")
                    image_pos, caption_pos = wc.locate([i - 1]), wc.locate([i])
                if image_pos["page"] != caption_pos["page"]:
                    add_issue(issues, "figure-layout", f"Рисунок не помещается вместе с подписью: {block['text']}", image_pos["page"])


def add_issue(issues, code, message, page=None):
    item = {"code": code, "message": message, "page": page}
    if item not in issues:
        issues.append(item)


def update_toc(wc, model, issues, do_fix=True):
    toc = detect_toc(model["body"])
    if toc is None:
        if auto_toc_text(model['body']):
            add_issue(issues, 'toc-auto-review', 'Автоматическое оглавление распознано и сохранено. Проверьте его строки и номера страниц в итоговом PDF; построчная проверка реализована для содержания-таблицы.')
            return
        if len(wc.execute("document.layout")["pages"]) > 10:
            add_issue(issues, "toc-missing", "Не найдено содержание в виде таблицы из двух или четырёх столбцов.")
        return
    body, styles = model["body"], model.get("styles", {})
    heads = {}
    for i, para in enumerate(body):
        if para["kind"] == "para" and heading_level(para, styles) and norm(para.get("text", "")) != "содержание":
            heads.setdefault(norm(para["text"]), []).append(i)
    for _ in range(4):
        changed = False
        for toc in detect_tocs(body):
            for ri, row in enumerate(body[toc]["rows"]):
                cells = row["cells"]
                if len(cells) < 2:
                    continue
                cell_text = [" ".join(p.get("text", "") for _, p in paragraphs(c["blocks"])) for c in cells]
                title = norm(" ".join(cell_text[:-1]))
                if not title:
                    continue  # Intentionally blank rows in the course's contents template.
                candidates = heads.get(title, [])
                if len(candidates) != 1:
                    reason = 'не найден заголовок с таким же текстом' if not candidates else 'найдено несколько одинаковых заголовков'
                    add_issue(issues, "toc-match", f"Содержание «{title}»: {reason}. Проверьте формулировку и разбиение заголовка на абзацы; наличие гиперссылки здесь не проверяется.")
                    continue
                location = wc.locate([candidates[0]])
                value = str(location["number"])
                ps = list(paragraphs(cells[-1]["blocks"], (toc, ri, len(cells) - 1)))
                if len(ps) != 1:
                    add_issue(issues, "toc-cell", f"Сложная ячейка номера страницы в содержании: {title}")
                    continue
                path, para = ps[0]
                old = para.get("text", "")
                if old != value:
                    if do_fix:
                        start = {"story": "body", "path": path, "off": 0}
                        end = {"story": "body", "path": path, "off": byte_len(old)}
                        wc.batch([{"command": "select.range", "params": {"anchor": start, "focus": end}},
                                  {"command": "text.insert", "params": {"text": value, "raw": True}}])
                        para["text"] = value
                        changed = True
                    else:
                        add_issue(issues, "toc-page", f"Содержание: «{title}» — указано {old}, фактически {value}.")
        if not changed:
            return
    add_issue(issues, "toc-convergence", "Содержание не стабилизировалось за четыре пересчёта; проверьте страницы вручную.")


def structural_checks(wc, model, mode, issues):
    body = model["body"]
    automatic_contents = auto_toc_text(body)
    toc = detect_toc(body)
    required = ("введение", "заключение", "список использованных источников") if mode == "full" else ()
    for title in required:
        accepted = {title, "библиографический список", "список литературы"} if title == "список использованных источников" else {title}
        if not any(p["kind"] == "para" and norm(p.get("text", "")) in accepted for p in body):
            add_issue(issues, "structure", f"Не найден раздел «{title.capitalize()}».")
    if mode == "full":
        if any(p['kind'] == 'para' and norm(p.get('text', '')) == 'список литературы' for p in body):
            add_issue(issues, 'bibliography-title', 'Раздел «Список литературы» найден. По §6.10 используйте название «Список использованных источников» или «Библиографический список».')
        refs = next((i for i, b in enumerate(body) if b["kind"] == "para" and
                     norm(b.get("text", "")) in {"список использованных источников", "библиографический список"}), None)
        if refs is not None:
            _, block = next_block(body, refs)
            if not block or block["kind"] != "table":
                add_issue(issues, "bibliography-table", "Список источников не оформлен таблицей без границ.")
    if mode == "full":
        layout = wc.execute("document.layout")
        if body_start(model) and wc.locate([body_start(model)])["page"] > 2:
            add_issue(issues, "title-pages", "Титульный лист занимает больше одной страницы: сократите длинные реквизиты или интервалы.")
        text=' '.join(b.get('text','') for b in body)
        if re.search(r'(?:ДП|ДР|МД)\.\d{6}\.',text) and len(layout['pages'])>100:
            add_issue(issues,'vkr-volume','Объём ВКР превышает 100 листов вместе с приложениями (§7.1.5).')
        parts = model.get("parts", {})
        frame_text = " ".join(p.get("text", "") for part in parts.values()
                              for _, p in paragraphs(part.get("blocks", [])))
        code = REG_NUMBER_RE.search(frame_text)
        if not code:
            add_issue(issues, "stamp-code", "Не найден шифр работы в колонтитулах/штампе. Чужие ФИО и реквизиты автоматически не подставляются.")
        for index, page in enumerate(layout["pages"]):
            if index and page.get("header") is None and page.get("footer") is None:
                add_issue(issues, "frame-missing", "Нет колонтитула с рамкой/штампом. Нужен оформленный шаблон; скрипт не рисует рамку поверх текста.", index + 1)
        if len(layout["pages"]) > 1 and toc is not None:
            toc_page = wc.locate([toc])["page"]
            default_page = next((p for i, p in enumerate(layout["pages"], 1) if i > toc_page), None)
            tp = layout["pages"][toc_page - 1]
            if default_page and (tp.get("header"), tp.get("footer")) == (default_page.get("header"), default_page.get("footer")):
                add_issue(issues, "large-stamp", "На содержании и обычном листе одинаковые колонтитулы: проверьте большой штамп содержания.")
    for i, p in enumerate(body):
        if (i,) in automatic_contents:
            continue
        if p["kind"] != "para":
            continue
        text = p.get("text", "")
        match = CAPTION.match(text)
        if match:
            number = match.group(2)
            other = "\n".join(b.get("text", "") for path, b in paragraphs(body)
                              if path != (i,) and path[0] not in detect_tocs(body)
                              and not CAPTION.match(b.get("text", "")))
            if not reference_exists(other, match.group(1), number):
                add_issue(issues, "reference", f"Не найдена текстовая ссылка: {match.group(1)} {number}.")
        if heading_level(p, model.get("styles", {})) and text.rstrip().endswith("."):
            add_issue(issues, "heading-dot", f"Точка в конце заголовка: {text}")
    start = next((i for i, p in enumerate(body) if p["kind"] == "para" and
                  (norm(p.get("text", "")) in SPECIAL or heading_level(p, model.get("styles", {})))), 0)
    for i, block in enumerate(body):
        if block["kind"] != "table" or table_caption(body, i) is None:
            continue
        for ri, row in enumerate(block["rows"]):
            if (row.get("props", {}).get("height") or 0) < 8 * MM - .1:
                add_issue(issues, "row-height", f"Для строки {ri + 1} таблицы не задан минимум 8 мм: {body[table_caption(body, i)]['text']}")
            if not row.get("props", {}).get("cantSplit"):
                add_issue(issues, "row-split", f"Разрешён разрыв строки {ri + 1}: {body[table_caption(body, i)]['text']}")
    # Font checks resolve inheritance through the native style table below.
    for path, para in paragraphs(body):
        if tuple(path) in automatic_contents:
            continue
        if not para.get("text", "").strip():
            continue
        main_text = len(path) == 1 and path[0] >= start
        if main_text and not has_image(para):
            spacing = effective_para(model, para).get("lineSpacing", {})
            if spacing.get("rule") != "multiple" or abs(spacing.get("value", 0) - 1.5) > .01:
                add_issue(issues, "line-spacing", f"Межстрочный интервал отличается от 1,5: {para['text'][:100]}")
        for run, run_text in visible_text_runs(para):
            props = effective_char(model, para, run)
            if props.get("bold"):
                add_issue(issues, "bold", f"Полужирный текст: {para['text'][:100]}")
            if main_text or (len(path) > 1 and path[0] >= start):
                if props.get("font") and props["font"] != FONT:
                    add_issue(issues, "font", f"Шрифт {props['font']} во фрагменте «{run_text[:100]}» (абзац: {para['text'][:100]}).")
                allowed = (14,) if main_text else (12, 14)
                if props.get("size") and all(abs(props["size"] - size) > .1 for size in allowed):
                    add_issue(issues, "font-size", f"Кегль {props['size']} во фрагменте «{run_text[:100]}» (абзац: {para['text'][:100]}).")


def trim_manual_indent(para):
    # Positional objects/fields need separate handling; never shift them blindly.
    if para.get('objects') or para.get('fields') or '\n' in para.get('text', ''):
        return
    text = para.get('text', '')
    cleaned = text.lstrip(' \t\u00a0')
    remaining = byte_len(text) - byte_len(cleaned)
    if not remaining:
        return
    runs = []
    for run in para.get('runs', []):
        take = min(remaining, run['len'])
        remaining -= take
        if run['len'] > take:
            item = copy.deepcopy(run)
            item['len'] -= take
            runs.append(item)
    para['text'], para['runs'] = cleaned, runs


def visible_text_runs(para):
    """Only actual text: object markers and whitespace carry no visible font."""
    data = para.get('text', '').encode('utf-8')
    offset = 0
    for run in para.get('runs', []):
        length = run.get('len', 0)
        text = data[offset:offset + length].decode('utf-8')
        offset += length
        visible = text.replace('\ufffc', '').strip()
        if visible:
            yield run, visible


def reference_exists(text, kind, number):
    stem = r"(?:рисун(?:ок|к\w*)|рис\.)" if kind.casefold() == "рисунок" else r"(?:таблиц\w*|табл\.)"
    token = r"(?:[а-яa-z]\.)?\d+(?:\.\d+)*"
    number = norm(number)
    target = tuple(number.split("."))
    for match in re.finditer(r"(?<!\w)" + stem + r"\s+(" + token + r"(?:\s*(?:[–—-]|,|и)\s*" + token + r")*)(?![\w.]*\d)", norm(text), re.I):
        phrase = match.group(1)
        numbers = re.findall(token, phrase)
        if number in numbers:
            return True
        for left, right in re.findall("(" + token + r")\s*[–—-]\s*(" + token + ")", phrase):
            lo, hi = tuple(left.split(".")), tuple(right.split("."))
            if lo[:-1] == hi[:-1] == target[:-1] and len(lo) == len(hi) == len(target):
                if target[-1].isdigit() and int(lo[-1]) <= int(target[-1]) <= int(hi[-1]):
                    return True
    return False


def effective_char(model, para, run):
    styles = model.get("styles", {})
    props = dict(styles.get("defaultChr", {}))
    if isinstance(styles, dict):
        chain, seen = [], set()
        style_id = para.get("props", {}).get("style", "Normal")
        while style_id and style_id not in seen:
            seen.add(style_id)
            st = next((s for s in styles.get("styles", []) if s.get("id") == style_id), {})
            chain.append(st)
            style_id = st.get("basedOn")
        for st in reversed(chain):
            props.update(st.get("chr", {}))
        chain, seen = [], set()
        style_id = run.get("props", {}).get("style")
        while style_id and style_id not in seen:
            seen.add(style_id)
            st = next((s for s in styles.get("styles", []) if s.get("id") == style_id), {})
            chain.append(st)
            style_id = st.get("basedOn")
        for st in reversed(chain):
            props.update(st.get("chr", {}))
    props.update(run.get("props", {}))
    return props


def effective_para(model, para):
    styles = model.get("styles", {})
    props = dict(styles.get("defaultPara", {}))
    chain, seen = [], set()
    style_id = para.get("props", {}).get("style", "Normal")
    while style_id and style_id not in seen:
        seen.add(style_id)
        st = next((s for s in styles.get("styles", []) if s.get("id") == style_id), {})
        chain.append(st)
        style_id = st.get("basedOn")
    for st in reversed(chain):
        props.update(st.get("para", {}))
    props.update(para.get("props", {}))
    return props


def write_report(path, report):
    esc = html.escape
    findings = "".join(f"<li>{esc(x['message'])}" +
                       (f" <strong>(стр. {x['page']})</strong>" if x.get("page") else "") + "</li>"
                       for x in report["issues"]) or "<li>В выполненных автоматических проверках замечаний не найдено.</li>"
    changes = "".join(f"<li>{esc(s)}</li>" for s in report["changes"]) or "<li>Оформление не изменялось.</li>"
    text = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Нормоконтроль</title>
<style>body{{font:17px/1.6 system-ui;max-width:950px;margin:40px auto;padding:0 24px;color:#20242b}}
h1{{font-size:28px}}li{{margin:8px 0}}.note{{background:#f0f3f6;padding:18px;border-radius:10px}}
a{{color:#1257a4}}small{{color:#596574}}</style>
<h1>Нормоконтроль ИрГУПС</h1><p>{esc(report['input'])}</p>
<p><a href="{quote(report['docx_name'])}">Открыть DOCX</a> · <a href="{quote(report['pdf_name'])}">Открыть PDF</a></p>
<p>Страниц: <strong>{report['pages']}</strong>. Профиль: {esc(report['mode'])}. Wordcraft: {esc(report['wordcraft'])}.</p>
<h2>Что сделано</h2><ul>{changes}</ul><h2>Что проверить</h2><ul>{findings}</ul>
<p class="note">Это результат автоматической проверки оформления, а не подпись нормоконтролёра.
Проверьте PDF глазами: титульник, рамки и штампы, рисунки, таблицы, пустые места и последний лист.
Смысл текста, правильность ФИО и шифра, актуальность источников, порядок приложений и грамматика
табличных заголовков требуют отдельной проверки. PDF создан Wordcraft; совпадение вёрстки с Microsoft Word не проверялось.</p>
<small>Исходный файл не изменён. {esc(report['created'])}</small></html>'''
    path.write_text(text, encoding="utf-8")


def process(source, out=None, mode="full", format_text=True, check_only=False, cli=None, progress=print, metadata=None,
            toc_template=False, bibliography_template=False, toc_entries=None, bibliography_entries=None, optional_sections=None):
    metadata = prepare_metadata(metadata)
    source = Path(source).expanduser().resolve()
    if not source.is_file() or source.suffix.casefold() != ".docx":
        raise ValueError("Выберите существующий файл .docx.")
    before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    original = inventory(source)
    if original["revisions"]:
        raise ValueError("В документе есть отслеживаемые исправления. Сначала сохраните отдельную копию с принятыми или отклонёнными правками.")
    cli = find_cli(cli)
    version = subprocess.run([cli, "--version"], capture_output=True, text=True, encoding="utf-8",
                             timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    if out:
        output = Path(out).expanduser().resolve()
    else:
        output = source.parent / f"{source.stem}_нормоконтроль_{datetime.now():%Y%m%d_%H%M%S}"
    # Results must never replace the input or a previous run.
    docx_path, pdf_path = output / (source.stem + "_нк.docx"), output / (source.stem + "_нк.pdf")
    for p in (docx_path, pdf_path, output / "report.html", output / "report.json"):
        if p.resolve() == source or p.exists():
            raise ValueError(f"Результат уже существует: {p}. Выберите другую папку.")
    output.mkdir(parents=True, exist_ok=True)
    issues, changes = [], []
    if original["signed"]:
        add_issue(issues, "signature", "Исходный DOCX содержит цифровую подпись; изменённая копия не сохраняет её действительность.")
    progress("Читаю документ через Wordcraft…")
    with tempfile.TemporaryDirectory(prefix="wordcraft-normokontrol-") as temp:
        temp = Path(temp)
        with Wordcraft(cli) as wc:
            wc.open(source)
            wc.save(temp / "source.json")
            model = json.loads((temp / "source.json").read_text(encoding="utf-8"))
            if not isinstance(model.get("body"), list) or not isinstance(model.get("parts"), dict):
                raise RuntimeError("Версия формата Wordcraft не поддерживается: нет body/parts.")
            initial_tables = sum(b["kind"] == "table" for b in model["body"])
            if not check_only:
                if mode == "full":
                    fill_cover(model, metadata, changes)
                add_templates(model, toc_template, bibliography_template, changes, toc_entries, bibliography_entries)
                add_optional_sections(model, optional_sections, changes)
            from captions import fill_captions
            from whitespace_cleanup import clean
            if format_text or check_only:
                clean(model, changes, issues, check_only=check_only)
            fill_captions(model, changes, issues, check_only=check_only)
            expected_text = stable_text(model, detect_toc(model["body"]))
            expected_tables = original["tables"] + sum(b["kind"] == "table" for b in model["body"]) - initial_tables
            if mode == "full" and not check_only:
                progress("Строю рамки и штампы с точными стыками…")
                apply_frames(model, metadata, changes, issues)
            if format_text and not check_only:
                normalize_model(model, mode, changes)
            if not check_only:
                (temp / "formatted.json").write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
                wc.open(temp / "formatted.json")
            expected_sections = 1 + sum(bool(b.get("section")) for b in model["body"])
            progress("Проверяю переносы таблиц и рисунков…")
            repair_layout(wc, model, mode, changes, issues, do_fix=not check_only)
            progress("Пересчитываю содержание и поля штампов…")
            if not check_only:
                wc.execute("references.updateFields", all=True)
            update_toc(wc, model, issues, do_fix=not check_only)
            if not check_only:
                wc.execute("references.updateFields", all=True)
            progress("Сохраняю DOCX и PDF…")
            wc.save(temp / "result.docx")
            # Reopen what will actually be delivered, not only the in-memory document.
            wc.open(temp / "result.docx")
            wc.save(temp / "result.pdf")
            wc.save(temp / "reopened.json")
            final = json.loads((temp / "reopened.json").read_text(encoding="utf-8"))
            if stable_text(final, detect_toc(final["body"])) != expected_text:
                raise RuntimeError("Проверка сохранности текста не пройдена. Результат не выдан: проверьте совместимость документа с Wordcraft.")
            result_inventory = inventory(temp / "result.docx")
            if result_inventory["tables"] != expected_tables or result_inventory["sections"] != expected_sections:
                raise RuntimeError("После сохранения изменилось число таблиц или разделов. Результат не выдан.")
            if result_inventory["media"] != original["media"]:
                add_issue(issues, "media", "Набор файлов изображений изменился при сохранении: проверьте рисунки и объекты. Возможна перекодировка формата.")
            structural_checks(wc, final, mode, issues)
            # Recheck final table/caption geometry without mutating it.
            repair_layout(wc, final, mode, [], issues, do_fix=False)
            update_toc(wc, final, issues, do_fix=False)
            pages = len(wc.execute("document.layout")["pages"])
        try:
            import pymupdf
            with pymupdf.open(temp / "result.pdf") as pdf:
                if len(pdf) != pages:
                    raise RuntimeError("Число страниц PDF не совпадает с повторно открытым DOCX.")
                for i, page in enumerate(pdf):
                    if not page.get_text().strip() and not page.get_images():
                        add_issue(issues, "empty-page", "Возможно, пустая страница.", i + 1)
                    anchors=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans']
                             if s['text'].strip() in {'Изм.','Разраб.','Литера','Пров.'} and s['bbox'][1]>page.rect.height-45*MM]
                    if anchors and any('ISOCPEUR' not in s['font'].upper() for s in anchors):
                        add_issue(issues,'stamp-font','ISOCPEUR не отрисован: установите ISOCPEUR Regular/Italic и повторите обработку. В PDF обнаружена подстановка шрифта.',i+1)
        except ImportError:
            add_issue(issues, "pdf-inspection", "PyMuPDF не установлен: дополнительная проверка PDF пропущена.")
        if hashlib.sha256(source.read_bytes()).hexdigest() != before_hash:
            raise RuntimeError("Исходник изменился во время работы. Повторите запуск после сохранения файла.")
        shutil.copyfile(temp / "result.docx", docx_path)
        shutil.copyfile(temp / "result.pdf", pdf_path)
    report = {"input": str(source), "input_sha256": before_hash, "created": datetime.now().isoformat(timespec="seconds"),
              "mode": "Полный нормоконтроль" if mode == "full" else "Обычная учебная работа",
              "wordcraft": version, "pages": pages, "changes": changes, "issues": issues,
              "docx_name": docx_path.name, "pdf_name": pdf_path.name,
              "automated_only": True, "word_render_verified": False,
              "output": str(output), "check_only": check_only}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(output / "report.html", report)
    progress(f"Готово: {pages} стр., замечаний: {len(issues)}. {output}")
    return report


def create_document(out, **options):
    cli = find_cli(options.get("cli"))
    with tempfile.TemporaryDirectory(prefix="normokontrol-new-") as folder:
        source = Path(folder) / "Новая работа.docx"
        with Wordcraft(cli) as wc:
            wc.call("new_document", template="blank")
            wc.save(source)
        report = process(source, out, **options)
        report["input"] = "Новый документ из шаблона курсача"
        report["created_from_template"] = True
        folder = Path(report["output"])
        (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        write_report(folder / "report.html", report)
        return report


def gui(initial=None):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from normokontrol_gui import show
    show(process, create_document, initial)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--out", type=Path, help="Новая папка результатов; существующие файлы не перезаписываются")
    parser.add_argument("--mode", choices=("full", "compact"), default="full")
    parser.add_argument("--no-format", action="store_true", help="Сохранить оформление, довести переносы и содержание")
    parser.add_argument("--check-only", action="store_true", help="Не исправлять оформление, поля, переносы и содержание")
    parser.add_argument("--wordcraft", help="Путь к wordcraft-cli.exe")
    parser.add_argument("--toc-template", action="store_true", help="Добавить пустую таблицу содержания из курсача")
    parser.add_argument("--bibliography-template", action="store_true", help="Добавить пустую таблицу-заготовку источников")
    parser.add_argument("--toc-file", type=Path, help="UTF-8 файл: по одному заголовку содержания на строку")
    parser.add_argument("--bibliography-file", type=Path, help="UTF-8 файл: по одному источнику на строку, без номера")
    parser.add_argument("--new", action="store_true", help="Создать новый документ (нужен --out)")
    parser.add_argument('--generate-code',action='store_true',help='Собрать шифр по §6.2 из полей ниже')
    parser.add_argument('--include-year',action='store_true',help='Год в учебном шифре только по кафедральному образцу; для ВКР год обязателен')
    parser.add_argument('--approval',action='store_true',help='Добавить гриф допуска к защите')
    for key in ('annotation','normative','abbreviations'):
        parser.add_argument('--'+key+'-template',action='store_true',help='Добавить необязательную заготовку раздела (§6.1)')
    fields = ("code", "author", "supervisor", "group", "stamp-title", "supervisor-title", "title", "discipline", "work-type", "city", "year", "university", "university-short", "faculty", "department", 'work-code','division-code','specialty','account','document-code','approval-person','approval-title')
    for field in fields:
        parser.add_argument("--" + field, help="Реквизит штампа")
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()
    if args.gui or (args.input is None and not args.new):
        gui(args.input)
        return 0
    try:
        metadata = {field.replace("-", "_"): getattr(args, field.replace("-", "_")) for field in fields}
        metadata.update(generate_code=args.generate_code,include_year=args.include_year,approval=args.approval)
        options = dict(mode=args.mode, format_text=not args.no_format, check_only=args.check_only, cli=args.wordcraft,
                       metadata=metadata, toc_template=args.toc_template, bibliography_template=args.bibliography_template,
                       toc_entries=[s.strip() for s in args.toc_file.read_text(encoding="utf-8-sig").splitlines() if s.strip()] if args.toc_file else None,
                       bibliography_entries=[s.strip() for s in args.bibliography_file.read_text(encoding="utf-8-sig").splitlines() if s.strip()] if args.bibliography_file else None,
                       optional_sections=[key for key in ('annotation','normative','abbreviations') if getattr(args,key+'_template')])
        if args.new and (not args.out or args.check_only):
            raise ValueError("Для --new задайте --out и отключите --check-only.")
        report = create_document(args.out, **options) if args.new else process(args.input, args.out, **options)
        return 2 if report["issues"] else 0
    except Exception as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
