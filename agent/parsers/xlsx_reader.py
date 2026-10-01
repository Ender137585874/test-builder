# -*- coding: utf-8 -*-
"""零依赖的 .xlsx 读取器（仅用标准库 zipfile + xml 解析）。

仅读取工作簿中的第一个工作表，足以覆盖常见题库表格场景。
如需完整 Excel 能力，可安装 openpyxl——本模块会在可用时优先使用它。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import List, Optional
from xml.etree import ElementTree as ET

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
_CELL_REF = re.compile(r"([A-Z]+)(\d+)")


def read_xlsx(path: Path, sheet_index: int = 0) -> List[List[str]]:
    """读取 xlsx 第一个工作表，返回二维字符串列表。"""
    path = Path(path)
    if _has_openpyxl():
        return _read_with_openpyxl(path, sheet_index)
    return _read_with_stdlib(path, sheet_index)


def _has_openpyxl() -> bool:
    import importlib.util

    return importlib.util.find_spec("openpyxl") is not None


def _read_with_openpyxl(path: Path, sheet_index: int) -> List[List[str]]:
    import openpyxl  # type: ignore

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb.worksheets[sheet_index]
        rows: List[List[str]] = []
        for row in ws.iter_rows(values_only=True):
            rows.append(["" if v is None else str(v) for v in row])
        return _trim(rows)
    finally:
        wb.close()


def _read_with_stdlib(path: Path, sheet_index: int) -> List[List[str]]:
    with zipfile.ZipFile(path) as zf:
        shared: List[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            shared = _parse_shared_strings(zf.read("xl/sharedStrings.xml"))
        sheet_path = _resolve_sheet_path(zf, sheet_index)
        if sheet_path is None:
            raise ValueError(f"xlsx 中未找到工作表：{path}")
        rows = _parse_sheet(zf.read(sheet_path), shared)
    return _trim(rows)


def _parse_shared_strings(data: bytes) -> List[str]:
    root = ET.fromstring(data)
    strings: List[str] = []
    for si in root.findall("m:si", _NS):
        parts = [t.text or "" for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")]
        strings.append("".join(parts))
    return strings


def _resolve_sheet_path(zf: zipfile.ZipFile, sheet_index: int) -> Optional[str]:
    names = zf.namelist()
    try:
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        sheets = wb.find("m:sheets", _NS)
        if sheets is not None:
            items = list(sheets)
            if sheet_index < len(items):
                rid = items[sheet_index].get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
                rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
                for rel in rels:
                    if rel.get("Id") == rid:
                        target = rel.get("Target").lstrip("/")
                        if not target.startswith("xl/"):
                            target = "xl/" + target
                        if target in names:
                            return target
    except (KeyError, ET.ParseError):
        pass
    for candidate in ("xl/worksheets/sheet1.xml", "xl/worksheets/Sheet1.xml"):
        if candidate in names:
            return candidate
    return None


def _parse_sheet(data: bytes, shared: List[str]) -> List[List[str]]:
    root = ET.fromstring(data)
    sheet_data = root.find("m:sheetData", _NS)
    if sheet_data is None:
        return []

    rows: List[List[str]] = []
    for row_el in sheet_data.findall("m:row", _NS):
        cell_map = {}
        max_col = -1
        for c in row_el.findall("m:c", _NS):
            ref = c.get("r") or ""
            cm = _CELL_REF.match(ref)
            col = _col_to_index(cm.group(1)) if cm else len(cell_map)
            cell_map[col] = _cell_value(c, shared)
            max_col = max(max_col, col)
        rows.append([cell_map.get(i, "") for i in range(max_col + 1)])
    return rows


def _cell_value(cell, shared: List[str]) -> str:
    ctype = cell.get("t")
    if ctype == "inlineStr":
        is_el = cell.find("m:is", _NS)
        if is_el is not None:
            return "".join(t.text or "" for t in is_el.iter(
                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
        return ""
    v = cell.find("m:v", _NS)
    if v is None or v.text is None:
        return ""
    text = v.text
    if ctype == "s":
        try:
            return shared[int(text)]
        except (ValueError, IndexError):
            return ""
    return text


def _col_to_index(letters: str) -> int:
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _trim(rows: List[List[str]]) -> List[List[str]]:
    out = [[(c or "").strip() for c in row] for row in rows]
    while out and not any(out[-1]):
        out.pop()
    return out
