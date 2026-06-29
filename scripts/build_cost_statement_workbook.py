#!/usr/bin/env python3
"""Build a 원가계산서 workbook from upstream input workbooks.

The generator uses the sample 원가계산보고서 workbook as a template and replaces
the two upstream source sheets used by the cost statement formula chain:

  단가대비표, 내역서

This keeps the sample 원가계산서 layout/formulas intact while allowing users to
provide the upstream sheets as separate Excel files. 집계표 is generated from
the 내역서 total row unless a summary workbook is explicitly supplied.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", REL_NS)

SUMMARY_SHEET = "집계표"
DETAIL_SHEET = "내역서"
UNIT_COST_DETAIL_SHEET = "일위대가표"
SUPPLEMENTAL_WORKBOOKS = {
    "expense": {
        "filename": "경비_산출표.xlsx",
        "visible_sheets": ["경비", "산재", "고용", "건강", "연금", "장기", "석면", "임금", "퇴공", "안전"],
    },
    "general": {
        "filename": "일반관리비_산출표.xlsx",
        "visible_sheets": ["일반", "일반비율"],
    },
    "profit": {
        "filename": "이윤_산출표.xlsx",
        "visible_sheets": ["이윤", "이윤비율"],
    },
}


@dataclass(frozen=True)
class CellPayload:
    address: str
    formula: str | None
    value: str | None
    value_type: str | None


class CostInputError(ValueError):
    """Raised when an input workbook fails required cell/range validation."""


# 입력 역할별로 주입 전에 갖춰야 하는 최소 비어있지 않은 셀 수.
# 잘못된/빈 시트가 단일 시트 fallback으로 선택돼 조용히 빈 입력이 주입되는 사고를 막는다.
MIN_INPUT_CELLS = {
    "단가대비표": 1,
    "내역서": 1,
    "일위대가표": 1,
    "집계표": 1,
}


def non_empty_cell_count(cells: list[CellPayload]) -> int:
    count = 0
    for cell in cells:
        if cell.formula is not None and cell.formula.strip() != "":
            count += 1
        elif cell.value is not None and str(cell.value).strip() != "":
            count += 1
    return count


def evaluate_input_payloads(
    payloads: dict[str, list[CellPayload]],
    detail_total_row: int | None,
    summary_supplied: bool,
) -> list[str]:
    """입력 payload에 대한 필수 cell/range 검증 결과(문제 목록)를 돌려준다.

    IO를 하지 않는 순수 함수라 작은 합성 payload로 단위 테스트할 수 있다.
    """
    problems: list[str] = []
    for sheet_name, cells in payloads.items():
        minimum = MIN_INPUT_CELLS.get(sheet_name, 1)
        found = non_empty_cell_count(cells)
        if found < minimum:
            problems.append(
                f"입력 시트 '{sheet_name}'에 사용할 셀 데이터가 없습니다 "
                f"(필요 최소 {minimum}, 발견 {found}). 올바른 파일/시트인지 확인하세요."
            )
    if not summary_supplied and detail_total_row is None:
        problems.append(
            "내역서에서 '합계' 행을 찾지 못했습니다. 집계표 자동 연결을 위해 "
            "A~C열에 '합계' 라벨과 금액(F/H/J/K열)이 있는 행이 필요합니다."
        )
    return problems


def q(tag: str) -> str:
    return f"{{{MAIN_NS}}}{tag}"


def is_comment_part(filename: str) -> bool:
    normalized = filename.replace("\\", "/")
    return (
        re.fullmatch(r"xl/comments\d+\.xml", normalized) is not None
        or re.fullmatch(r"xl/threadedComments\d+\.xml", normalized) is not None
        or re.fullmatch(r"xl/drawings/vmlDrawing\d+\.vml", normalized) is not None
        or normalized.startswith("xl/persons/")
    )


def strip_comment_sheet_refs(sheet_xml: bytes) -> bytes:
    text = sheet_xml.decode("utf-8")
    text = re.sub(r"<(?:\w+:)?legacyDrawing(?:HF)?\b[^>]*/>", "", text)
    text = re.sub(
        r"<(?:\w+:)?legacyDrawing(?:HF)?\b[^>]*>.*?</(?:\w+:)?legacyDrawing(?:HF)?>",
        "",
        text,
        flags=re.S,
    )
    return text.encode("utf-8")


def is_external_link_part(filename: str) -> bool:
    # 템플릿이 들고 온 외부 통합문서 링크(externalLinks). 생성물 수식은 외부참조 [N]를
    # 쓰지 않으므로 죽은 링크다. 그대로 두면 Excel/한셀이 "링크 업데이트"를 묻거나
    # 손상으로 판정할 수 있어 통째로 제거한다.
    return filename.replace("\\", "/").startswith("xl/externalLinks/")


# 아래 strip 함수들은 절대로 ElementTree 재직렬화를 쓰지 않는다.
# ET.fromstring→tostring은 mc/x14ac/hs 같은 확장 네임스페이스 prefix를
# ns0/ns1...로 바꿔 mc:Ignorable 참조를 깨뜨려 Excel 손상을 유발했었다(회귀 방지).
def strip_relationships(rels_xml: bytes) -> bytes:
    text = rels_xml.decode("utf-8")

    def keep(match: re.Match) -> str:
        rel = match.group(0)
        low = rel.lower()
        if "externallink" in low:
            return ""
        if any(token in low for token in ("/comments", "threadedcomment", "vmldrawing", "/person", "persons/")):
            return ""
        return rel

    return re.sub(r"<Relationship\b[^>]*/>", keep, text).encode("utf-8")


def strip_content_types(content_types_xml: bytes) -> bytes:
    text = content_types_xml.decode("utf-8")
    text = re.sub(r'<Default\b[^>]*\bExtension="vml"[^>]*/>', "", text, flags=re.I)

    def keep(match: re.Match) -> str:
        node = match.group(0)
        low = node.lower()
        if any(token in low for token in (
            "/xl/comments",
            "/xl/threadedcomments",
            "/xl/persons/",
            "externallink",
            "spreadsheetml.comments",
            "threadedcomments",
        )):
            return ""
        return node

    return re.sub(r"<Override\b[^>]*/>", keep, text).encode("utf-8")


def scrub_workbook_part(filename: str, data: bytes) -> bytes:
    normalized = filename.replace("\\", "/")
    if normalized == "[Content_Types].xml":
        return strip_content_types(data)
    if normalized.startswith("xl/worksheets/") and normalized.endswith(".xml"):
        return strip_comment_sheet_refs(data)
    if normalized.endswith(".rels"):
        return strip_relationships(data)
    return data


def load_importer():
    path = REPO_ROOT / "scripts" / "import_sample_ver1_cost_workbook.py"
    spec = importlib.util.spec_from_file_location("costimp", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["costimp"] = mod
    spec.loader.exec_module(mod)
    return mod


def text_of(node: ET.Element | None) -> str:
    return "" if node is None or node.text is None else node.text


def xml_escape(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def find_default_template(repo_root: Path, version: str) -> Path:
    marker = "ver2" if version == "ver2" else "ver1"
    matches = sorted(repo_root.glob(f"docs/원가계산보고서샘플/*{marker}*.xlsx*"))
    if not matches:
        raise FileNotFoundError(f"template workbook not found for {version}")
    return matches[0]


def sheet_by_role_or_name(imp, archive: zipfile.ZipFile, preferred_name: str, role: str):
    sheets = imp.read_sheets(archive)
    exact = next((sheet for sheet in sheets if sheet.name == preferred_name), None)
    if exact is not None:
        return exact
    by_role = next((sheet for sheet in sheets if imp.infer_sheet_role(sheet.name) == role), None)
    if by_role is not None:
        return by_role
    if len(sheets) == 1:
        return sheets[0]
    available = ", ".join(sheet.name for sheet in sheets)
    raise ValueError(f"cannot find sheet {preferred_name!r}/{role!r}; available: {available}")


def sheet_by_name(imp, archive: zipfile.ZipFile, name: str):
    sheets = imp.read_sheets(archive)
    sheet = next((candidate for candidate in sheets if candidate.name == name), None)
    if sheet is None:
        available = ", ".join(candidate.name for candidate in sheets)
        raise ValueError(f"template sheet {name!r} not found; available: {available}")
    return sheet


def extract_cells(imp, archive: zipfile.ZipFile, sheet, shared_strings: list[str]) -> list[CellPayload]:
    root = ET.fromstring(archive.read(sheet.path))
    cells: list[CellPayload] = []
    for cell in root.iter(q("c")):
        address = cell.attrib.get("r", "")
        if not address:
            continue
        formula_node = cell.find(q("f"))
        formula = text_of(formula_node) if formula_node is not None else None
        value, value_type = imp.cell_value(cell, shared_strings)
        if formula is None and (value is None or str(value).strip() == ""):
            continue
        cells.append(CellPayload(address=address, formula=formula, value=value, value_type=value_type))
    return sorted(cells, key=lambda item: (imp.row_number(item.address), imp.column_number(item.address)))


def find_detail_total_row(input_path: Path) -> int:
    imp = load_importer()
    with zipfile.ZipFile(input_path) as archive:
        shared_strings = imp.read_shared_strings(archive)
        sheet = sheet_by_role_or_name(imp, archive, DETAIL_SHEET, "detail")
        root = ET.fromstring(archive.read(sheet.path))
        rows: dict[int, dict[str, str]] = {}
        for cell in root.iter(q("c")):
            address = cell.attrib.get("r", "")
            if not address:
                continue
            value, _value_type = imp.cell_value(cell, shared_strings)
            if value is None or str(value).strip() == "":
                continue
            row_no = imp.row_number(address)
            col_name = column_name(imp.column_number(address))
            rows.setdefault(row_no, {})[col_name] = str(value).strip()

    candidates: list[int] = []
    for row_no, values in rows.items():
        label_text = "".join(values.get(col, "") for col in ("A", "B", "C")).replace(" ", "")
        has_total_label = "합계" in label_text
        has_amounts = any(values.get(col) not in (None, "", "0") for col in ("F", "H", "J", "K"))
        if has_total_label and has_amounts:
            candidates.append(row_no)

    if not candidates:
        raise ValueError(f"cannot find 내역서 합계 row in {input_path}")
    return min(candidates)


def auto_summary_sheet_xml(template_xml: bytes, detail_total_row: int) -> bytes:
    text = template_xml.decode("utf-8")
    text = re.sub(r"내역서!([FHJ])\d+", rf"내역서!\g<1>{detail_total_row}", text)
    return text.encode("utf-8")


def dimension_for(imp, cells: list[CellPayload]) -> str:
    if not cells:
        return "A1"
    max_row = max(imp.row_number(cell.address) for cell in cells)
    max_col = max(imp.column_number(cell.address) for cell in cells)
    return f"A1:{column_name(max_col)}{max_row}"


def column_name(number: int) -> str:
    chars: list[str] = []
    while number:
        number, remainder = divmod(number - 1, 26)
        chars.append(chr(65 + remainder))
    return "".join(reversed(chars))


def rows_xml(imp, cells: list[CellPayload]) -> str:
    by_row: dict[int, list[CellPayload]] = {}
    for cell in cells:
        by_row.setdefault(imp.row_number(cell.address), []).append(cell)

    rows: list[str] = []
    for row_no in sorted(by_row):
        cells_xml: list[str] = []
        for cell in by_row[row_no]:
            formula_xml = f"<f>{xml_escape(cell.formula)}</f>" if cell.formula is not None else ""
            value = cell.value
            if cell.value_type in ("s", "str", "inlineStr") and value is not None and cell.formula is None:
                cells_xml.append(
                    f'<c r="{cell.address}" t="inlineStr"><is><t>{xml_escape(value)}</t></is></c>'
                )
            elif cell.value_type == "e" and value is not None:
                cells_xml.append(f'<c r="{cell.address}" t="e">{formula_xml}<v>{xml_escape(value)}</v></c>')
            elif value is not None and str(value).strip() != "":
                cells_xml.append(f'<c r="{cell.address}">{formula_xml}<v>{xml_escape(value)}</v></c>')
            else:
                cells_xml.append(f'<c r="{cell.address}">{formula_xml}</c>')
        rows.append(f'<row r="{row_no}">{"".join(cells_xml)}</row>')
    return "".join(rows)


def replace_sheet_data(imp, template_xml: bytes, cells: list[CellPayload]) -> bytes:
    text = template_xml.decode("utf-8")
    dimension = dimension_for(imp, cells)
    row_block = f"<sheetData>{rows_xml(imp, cells)}</sheetData>"
    if re.search(r"<dimension[^>]*/>", text):
        text = re.sub(r"<dimension[^>]*/>", f'<dimension ref="{dimension}"/>', text, count=1)
    else:
        text = re.sub(
            r"(<worksheet\b[^>]*>)",
            rf'\1<dimension ref="{dimension}"/>',
            text,
            count=1,
        )
    if re.search(r"<sheetData>.*?</sheetData>", text, flags=re.S):
        text = re.sub(r"<sheetData>.*?</sheetData>", row_block, text, count=1, flags=re.S)
    else:
        text = text.replace("</worksheet>", f"{row_block}</worksheet>")
    # Merge/style ranges from the template source sheets may not match the user input.
    text = re.sub(r"<mergeCells[^>]*>.*?</mergeCells>", "", text, flags=re.S)
    return text.encode("utf-8")


_CALC_ATTRS = (("calcMode", "auto"), ("fullCalcOnLoad", "1"), ("forceFullCalc", "1"))


def strip_external_references(workbook_xml_text: str) -> str:
    # 죽은 외부참조 묶음 제거. 수식이 [N] 외부참조를 쓰지 않을 때만 안전하다(생성물은 안 씀).
    return re.sub(r"<externalReferences>.*?</externalReferences>", "", workbook_xml_text, flags=re.S)


def force_recalculation(workbook_xml: bytes) -> bytes:
    """workbook.xml의 calcPr에 재계산 속성을 설정한다(문자열 편집, 네임스페이스 보존)."""
    text = strip_external_references(workbook_xml.decode("utf-8"))
    match = re.search(r"<calcPr\b([^>]*?)\s*(/?)>", text)
    if match:
        attrs = match.group(1)
        for name, value in _CALC_ATTRS:
            if re.search(rf'\s{name}="[^"]*"', attrs):
                attrs = re.sub(rf'\s{name}="[^"]*"', f' {name}="{value}"', attrs, count=1)
            else:
                attrs = f"{attrs.rstrip()} {name}=\"{value}\""
        tag = f"<calcPr {attrs.strip()}{' />' if match.group(2) else '>'}"
        text = text[: match.start()] + tag + text[match.end():]
    else:
        new = '<calcPr calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>'
        if "</definedNames>" in text:
            text = text.replace("</definedNames>", "</definedNames>" + new, 1)
        elif "</sheets>" in text:
            text = text.replace("</sheets>", "</sheets>" + new, 1)
        else:
            text = text.replace("</workbook>", new + "</workbook>", 1)
    return text.encode("utf-8")


def set_visible_sheets(workbook_xml: bytes, visible_sheet_names: list[str]) -> bytes:
    """지정 시트만 보이게 하고 나머지는 hidden 처리한다(문자열 편집, 네임스페이스 보존)."""
    visible = set(visible_sheet_names)
    text = workbook_xml.decode("utf-8")
    state = {"index": 0, "first_visible": None}

    def replace_sheet(match: re.Match) -> str:
        tag = match.group(0)
        index = state["index"]
        state["index"] += 1
        name_match = re.search(r'\bname="([^"]*)"', tag)
        name = name_match.group(1) if name_match else ""
        if name in visible:
            if state["first_visible"] is None:
                state["first_visible"] = index
            return re.sub(r'\s+state="[^"]*"', "", tag)
        if re.search(r'\bstate="[^"]*"', tag):
            return re.sub(r'\bstate="[^"]*"', 'state="hidden"', tag)
        return tag[:-2] + ' state="hidden"/>' if tag.endswith("/>") else tag

    text = re.sub(r"<sheet\b[^>]*/>", replace_sheet, text)
    active = state["first_visible"] or 0

    def update_view(match: re.Match) -> str:
        tag = match.group(0)
        tag = re.sub(r'\s+activeTab="[^"]*"', "", tag)
        tag = re.sub(r'\s+firstSheet="[^"]*"', "", tag)
        inject = f' firstSheet="{active}" activeTab="{active}"'
        return tag[:-2] + inject + "/>" if tag.endswith("/>") else tag[:-1] + inject + ">"

    text = re.sub(r"<workbookView\b[^>]*?/?>", update_view, text, count=1)
    return text.encode("utf-8")


def export_visible_sheet_workbook(source_path: Path, output_path: Path, visible_sheet_names: list[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source_path) as source_archive:
        workbook_xml = set_visible_sheets(source_archive.read("xl/workbook.xml"), visible_sheet_names)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as output_archive:
            for info in source_archive.infolist():
                if info.filename == "xl/workbook.xml":
                    output_archive.writestr(info, workbook_xml)
                else:
                    output_archive.writestr(info, source_archive.read(info.filename))


def export_supplemental_workbooks(source_path: Path, output_dir: Path) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for key, spec in SUPPLEMENTAL_WORKBOOKS.items():
        output_path = output_dir / spec["filename"]
        export_visible_sheet_workbook(source_path, output_path, spec["visible_sheets"])
        outputs.append({
            "kind": key,
            "output": str(output_path),
            "visible_sheets": spec["visible_sheets"],
        })
    return outputs


def read_source_payload(input_path: Path, preferred_name: str, role: str) -> list[CellPayload]:
    imp = load_importer()
    with zipfile.ZipFile(input_path) as archive:
        shared_strings = imp.read_shared_strings(archive)
        sheet = sheet_by_role_or_name(imp, archive, preferred_name, role)
        return extract_cells(imp, archive, sheet, shared_strings)


def build_workbook(args: argparse.Namespace) -> dict[str, Any]:
    imp = load_importer()
    template_path = args.template
    if template_path is None:
        template_path = find_default_template(REPO_ROOT, args.template_version)
    if not template_path.is_absolute():
        template_path = REPO_ROOT / template_path

    output_path = args.output
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    source_specs = [
        ("단가대비표", "price_comparison", args.price_comparison),
        ("내역서", "detail", args.detail),
    ]
    if args.unit_cost is not None:
        source_specs.append((UNIT_COST_DETAIL_SHEET, "unit_price_detail", args.unit_cost))
    if args.summary is not None:
        source_specs.append((SUMMARY_SHEET, "summary", args.summary))
    source_payloads = {
        sheet_name: read_source_payload(input_path, sheet_name, role)
        for sheet_name, role, input_path in source_specs
    }
    summary_supplied = args.summary is not None
    if summary_supplied:
        detail_total_row = None
    else:
        try:
            detail_total_row = find_detail_total_row(args.detail)
        except ValueError:
            detail_total_row = None

    if not getattr(args, "skip_input_validation", False):
        problems = evaluate_input_payloads(source_payloads, detail_total_row, summary_supplied)
        if problems:
            raise CostInputError("입력 파일 검증 실패:\n- " + "\n- ".join(problems))

    with zipfile.ZipFile(template_path) as template_archive:
        target_sheets = {
            sheet_name: sheet_by_name(imp, template_archive, sheet_name)
            for sheet_name, _role, _input_path in source_specs
        }
        replacements = {
            target_sheets[sheet_name].path: replace_sheet_data(
                imp,
                template_archive.read(target_sheets[sheet_name].path),
                source_payloads[sheet_name],
            )
            for sheet_name in source_payloads
        }
        if detail_total_row is not None:
            summary_sheet = sheet_by_name(imp, template_archive, SUMMARY_SHEET)
            replacements[summary_sheet.path] = auto_summary_sheet_xml(
                template_archive.read(summary_sheet.path),
                detail_total_row,
            )
        replacements["xl/workbook.xml"] = force_recalculation(template_archive.read("xl/workbook.xml"))

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as output_archive:
            for info in template_archive.infolist():
                if is_comment_part(info.filename) or is_external_link_part(info.filename):
                    continue
                if info.filename in replacements:
                    data = replacements[info.filename]
                else:
                    data = template_archive.read(info.filename)
                output_archive.writestr(info, scrub_workbook_part(info.filename, data))

    supplemental_outputs: list[dict[str, Any]] = []
    if args.supplemental_dir is not None:
        supplemental_dir = args.supplemental_dir
        if not supplemental_dir.is_absolute():
            supplemental_dir = REPO_ROOT / supplemental_dir
        supplemental_outputs = export_supplemental_workbooks(output_path, supplemental_dir)

    return {
        "output": str(output_path),
        "template": str(template_path),
        "auto_summary": detail_total_row is not None,
        "detail_total_row": detail_total_row,
        "replaced_sheets": [
            {"sheet": sheet_name, "cells": len(source_payloads[sheet_name])}
            for sheet_name in source_payloads
        ],
        "supplemental_outputs": supplemental_outputs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--price-comparison", type=Path, required=True, help="단가대비표 Excel file")
    parser.add_argument("--unit-cost", type=Path, help="일위대가표 Excel file")
    parser.add_argument("--detail", type=Path, required=True, help="내역서 Excel file")
    parser.add_argument("--summary", type=Path, help="집계표 Excel file; omitted to auto-generate from 내역서")
    parser.add_argument("--output", type=Path, required=True, help="Generated 원가계산서 workbook")
    parser.add_argument("--template", type=Path, help="원가계산보고서 template workbook")
    parser.add_argument("--template-version", choices=("ver1", "ver2"), default="ver1")
    parser.add_argument("--supplemental-dir", type=Path, help="Directory for 경비/일반관리비/이윤 split workbooks")
    parser.add_argument(
        "--skip-input-validation",
        action="store_true",
        help="입력 파일 필수 cell/range 검증을 건너뛴다(운영 외 디버깅용).",
    )
    args = parser.parse_args()

    try:
        report = build_workbook(args)
    except CostInputError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(f"wrote {report['output']}")
    print(f"template={report['template']}")
    if report["auto_summary"]:
        print(f"집계표=auto from 내역서 row {report['detail_total_row']}")
    for item in report["replaced_sheets"]:
        print(f"{item['sheet']}={item['cells']} cells")
    for item in report["supplemental_outputs"]:
        print(f"{item['kind']}={item['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
