#!/usr/bin/env python3
"""Verify sample_ver1 golden values against workbook cached values.

This script is intentionally small and conservative. It does not try to become
Excel; it evaluates the formula subset used by the current cost-total path and
falls back to cached values when a formula is outside that subset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import import_sample_ver1_cost_workbook as workbook_importer


TARGET_CELLS = [
    ("원가계산서", "E34"),
    ("결과", "J10"),
]

ROLLUP_CELLS = [
    ("원가계산서", "E7"),
    ("원가계산서", "E9"),
    ("원가계산서", "E10"),
    ("원가계산서", "E12"),
    ("원가계산서", "E30"),
    ("원가계산서", "E31"),
    ("원가계산서", "E32"),
    ("원가계산서", "E33"),
    ("원가계산서", "E34"),
    ("결과", "J10"),
]


@dataclass(frozen=True)
class CellRecord:
    sheet: str
    address: str
    formula: str | None
    cached_value: str | None
    cached_value_type: str | None


class ExcelBlank:
    def __float__(self) -> float:
        return 0.0

    def __bool__(self) -> bool:
        return False

    def __add__(self, other: Any) -> float:
        return float(other)

    def __radd__(self, other: Any) -> float:
        return float(other)

    def __sub__(self, other: Any) -> float:
        return -float(other)

    def __rsub__(self, other: Any) -> float:
        return float(other)

    def __mul__(self, other: Any) -> float:
        return 0.0

    def __rmul__(self, other: Any) -> float:
        return 0.0

    def __truediv__(self, other: Any) -> float:
        return 0.0

    def __repr__(self) -> str:
        return "BLANK"


BLANK = ExcelBlank()


def clean_address(address: str) -> str:
    return address.replace("$", "")


def cell_key(sheet: str, address: str) -> tuple[str, str]:
    return sheet, clean_address(address)


def numeric_value(value: str | int | float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, ExcelBlank):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def printable_number(value: float | None) -> int | float | None:
    if value is None:
        return None
    if abs(value - round(value)) < 0.000001:
        return int(round(value))
    return value


def column_name_to_number(column: str) -> int:
    return workbook_importer.column_number(column)


def number_to_column_name(number: int) -> str:
    chars: list[str] = []
    while number:
        number, remainder = divmod(number - 1, 26)
        chars.append(chr(65 + remainder))
    return "".join(reversed(chars))


def split_address(address: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]{1,3})(\d+)", clean_address(address))
    if not match:
        raise ValueError(f"invalid cell address: {address}")
    return column_name_to_number(match.group(1)), int(match.group(2))


def expand_range(address_range: str) -> list[str]:
    start, end = [clean_address(part) for part in address_range.split(":", 1)]
    start_col, start_row = split_address(start)
    end_col, end_row = split_address(end)
    addresses: list[str] = []
    for row in range(min(start_row, end_row), max(start_row, end_row) + 1):
        for col in range(min(start_col, end_col), max(start_col, end_col) + 1):
            addresses.append(f"{number_to_column_name(col)}{row}")
    return addresses


def read_workbook_cells(path: Path) -> dict[tuple[str, str], CellRecord]:
    cells: dict[tuple[str, str], CellRecord] = {}
    with zipfile.ZipFile(path) as archive:
        shared_strings = workbook_importer.read_shared_strings(archive)
        for sheet in workbook_importer.read_sheets(archive):
            root = ET.fromstring(archive.read(sheet.path))
            for cell in root.iter(workbook_importer.q("c")):
                address = cell.attrib.get("r", "")
                if not address:
                    continue
                formula_node = cell.find(workbook_importer.q("f"))
                formula = workbook_importer.text_of(formula_node) if formula_node is not None else None
                value, value_type = workbook_importer.cell_value(cell, shared_strings)
                if formula_node is not None or value is not None:
                    cells[cell_key(sheet.name, address)] = CellRecord(
                        sheet=sheet.name,
                        address=clean_address(address),
                        formula=formula,
                        cached_value=value,
                        cached_value_type=value_type,
                    )
    return cells


class FormulaEvaluator:
    def __init__(self, cells: dict[tuple[str, str], CellRecord]) -> None:
        self.cells = cells
        self.memo: dict[tuple[str, str], float | ExcelBlank] = {}
        self.formula_fallbacks: list[dict[str, Any]] = []
        self.missing_cells: set[tuple[str, str]] = set()

    def evaluate_cell(self, sheet: str, address: str, stack: tuple[tuple[str, str], ...] = ()) -> float | ExcelBlank:
        key = cell_key(sheet, address)
        if key in self.memo:
            return self.memo[key]
        if key in stack:
            raise ValueError(f"circular reference at {sheet}!{address}")

        record = self.cells.get(key)
        if record is None:
            self.missing_cells.add(key)
            self.memo[key] = BLANK
            return BLANK

        if record.formula:
            try:
                value = self.evaluate_formula(record.formula, sheet, stack + (key,))
                self.memo[key] = value
                return value
            except Exception as exc:  # noqa: BLE001 - record fallback reason for audit output
                cached = numeric_value(record.cached_value)
                if cached is not None:
                    self.formula_fallbacks.append(
                        {
                            "cell": f"{sheet}!{address}",
                            "formula": record.formula,
                            "cached_value": printable_number(cached),
                            "reason": str(exc),
                        }
                    )
                    self.memo[key] = cached
                    return cached
                raise

        cached = numeric_value(record.cached_value)
        if cached is None:
            self.memo[key] = BLANK
            return BLANK
        self.memo[key] = cached
        return cached

    def evaluate_formula(
        self,
        formula: str,
        current_sheet: str,
        stack: tuple[tuple[str, str], ...],
    ) -> float:
        expression = formula.strip()
        if not expression:
            raise ValueError("blank formula")
        expression = expression.replace("^", "**")
        expression = re.sub(r"(?<![A-Za-z0-9_])(\d+(?:\.\d+)?)%", r"(\1/100)", expression)

        placeholders: list[tuple[str, str]] = []

        def hold(replacement: str) -> str:
            key = f"__p{len(placeholders)}__"
            placeholders.append((key, replacement))
            return key

        address = r"\$?[A-Z]{1,3}\$?\d+"
        address_range = rf"{address}:{address}"

        def sheet_range_repl(match: re.Match[str]) -> str:
            sheet = match.group("quoted") or match.group("plain")
            return hold(f'RANGE("{sheet}","{clean_address(match.group("range"))}")')

        def sheet_cell_repl(match: re.Match[str]) -> str:
            sheet = match.group("quoted") or match.group("plain")
            return hold(f'CELL("{sheet}","{clean_address(match.group("address"))}")')

        quoted = r"'(?P<quoted>[^']+)'!"
        plain = r"(?P<plain>[A-Za-z0-9_가-힣 .\-\(\)\[\]]+)!"
        expression = re.sub(rf"(?:{quoted}|{plain})(?P<range>{address_range})", sheet_range_repl, expression)
        expression = re.sub(rf"(?:{quoted}|{plain})(?P<address>{address})", sheet_cell_repl, expression)
        expression = re.sub(
            rf"(?<![A-Za-z0-9_])(?P<range>{address_range})(?![A-Za-z0-9_])",
            lambda match: hold(f'RANGE("{current_sheet}","{clean_address(match.group("range"))}")'),
            expression,
        )
        expression = re.sub(
            rf"(?<![A-Za-z0-9_])(?P<address>{address})(?![A-Za-z0-9_])",
            lambda match: hold(f'CELL("{current_sheet}","{clean_address(match.group("address"))}")'),
            expression,
        )

        for key, replacement in placeholders:
            expression = expression.replace(key, replacement)

        expression = expression.replace("<>", "!=")
        expression = re.sub(r"(?<![<>=])=(?!=)", "==", expression)

        def cell(sheet: str, address_value: str) -> float | ExcelBlank:
            return self.evaluate_cell(sheet, address_value, stack)

        def cell_range(sheet: str, range_value: str) -> list[float | ExcelBlank]:
            return [self.evaluate_cell(sheet, address, stack) for address in expand_range(range_value)]

        def flatten(values: tuple[Any, ...], *, ignore_blanks: bool = False) -> list[float]:
            flattened: list[float] = []
            for value in values:
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, ExcelBlank) and ignore_blanks:
                            continue
                        flattened.append(float(item))
                else:
                    if isinstance(value, ExcelBlank) and ignore_blanks:
                        continue
                    flattened.append(float(value))
            return flattened

        def excel_sum(*values: Any) -> float:
            return sum(flatten(values))

        def excel_min(*values: Any) -> float:
            flattened = flatten(values, ignore_blanks=True)
            return min(flattened) if flattened else 0.0

        def excel_max(*values: Any) -> float:
            flattened = flatten(values, ignore_blanks=True)
            return max(flattened) if flattened else 0.0

        def excel_sumif(range_values: list[float], criteria: Any, sum_range: list[float] | None = None) -> float:
            values_to_sum = sum_range or range_values
            total = 0.0
            for index, criteria_value in enumerate(range_values):
                if index >= len(values_to_sum):
                    break
                if matches_criteria(criteria_value, criteria):
                    total += float(values_to_sum[index])
            return total

        def matches_criteria(value: Any, criteria: Any) -> bool:
            value_number = numeric_value(value)
            criteria_text = str(criteria)
            operator_match = re.fullmatch(r"(>=|<=|<>|>|<|=)?\s*(.+)", criteria_text)
            if not operator_match:
                return str(value) == criteria_text
            operator = operator_match.group(1) or "="
            operand_text = operator_match.group(2)
            operand_number = numeric_value(operand_text)
            if value_number is not None and operand_number is not None:
                if operator == ">=":
                    return value_number >= operand_number
                if operator == "<=":
                    return value_number <= operand_number
                if operator == "<>":
                    return value_number != operand_number
                if operator == ">":
                    return value_number > operand_number
                if operator == "<":
                    return value_number < operand_number
                return value_number == operand_number
            if operator == "<>":
                return str(value) != operand_text
            return str(value) == operand_text

        def trunc(value: float, digits: float = 0) -> float:
            digits_int = int(digits)
            if digits_int >= 0:
                factor = 10**digits_int
                return math.trunc(float(value) * factor) / factor
            factor = 10 ** abs(digits_int)
            return math.trunc(float(value) / factor) * factor

        allowed = {
            "CELL": cell,
            "RANGE": cell_range,
            "SUM": excel_sum,
            "SUMIF": excel_sumif,
            "MIN": excel_min,
            "MAX": excel_max,
            "TRUNC": trunc,
            "ROUNDDOWN": trunc,
            "ROUND": lambda value, digits=0: round(float(value), int(digits)),
            "ABS": abs,
            "IF": lambda condition, true_value, false_value=0: true_value if condition else false_value,
        }
        return float(eval(expression, {"__builtins__": {}}, allowed))


def build_cell_check(evaluator: FormulaEvaluator, cells: dict[tuple[str, str], CellRecord], sheet: str, address: str) -> dict[str, Any]:
    record = cells[cell_key(sheet, address)]
    cached = numeric_value(record.cached_value)
    evaluated = evaluator.evaluate_cell(sheet, address)
    difference = None if cached is None else evaluated - cached
    passed = cached is not None and abs(difference or 0.0) < 0.000001
    return {
        "cell": f"{sheet}!{address}",
        "formula": record.formula,
        "excel_cached_value": printable_number(cached),
        "db_candidate_value": printable_number(evaluated),
        "difference": printable_number(difference),
        "passed": passed,
    }


def build_report(input_path: Path) -> dict[str, Any]:
    cells = read_workbook_cells(input_path)
    evaluator = FormulaEvaluator(cells)
    checks = [build_cell_check(evaluator, cells, sheet, address) for sheet, address in TARGET_CELLS]
    rollup = [build_cell_check(evaluator, cells, sheet, address) for sheet, address in ROLLUP_CELLS]

    result_total = evaluator.evaluate_cell("결과", "J10")
    cost_total = evaluator.evaluate_cell("원가계산서", "E34")
    comparison_difference = result_total - cost_total

    return {
        "source_path": str(input_path.as_posix()),
        "source_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "checks": checks,
        "comparisons": [
            {
                "left": "결과!J10",
                "right": "원가계산서!E34",
                "left_db_candidate_value": printable_number(result_total),
                "right_db_candidate_value": printable_number(cost_total),
                "difference": printable_number(comparison_difference),
                "passed": abs(comparison_difference) < 0.000001,
            }
        ],
        "rollup_cells": rollup,
        "formula_fallbacks": evaluator.formula_fallbacks[:50],
        "formula_fallback_count": len(evaluator.formula_fallbacks),
        "missing_cell_count": len(evaluator.missing_cells),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="Path to sample_ver1 xlsx")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/sample_ver1_cost_db/golden_value_check.json"),
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    input_path = args.input or workbook_importer.find_default_workbook(repo_root)
    if not input_path.is_absolute():
        input_path = repo_root / input_path
    output_path = args.output
    if not output_path.is_absolute():
        output_path = repo_root / output_path

    report = build_report(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    passed_checks = sum(1 for check in report["checks"] if check["passed"])
    passed_comparisons = sum(1 for check in report["comparisons"] if check["passed"])
    print(f"wrote {output_path}")
    print(
        f"checks={passed_checks}/{len(report['checks'])} "
        f"comparisons={passed_comparisons}/{len(report['comparisons'])} "
        f"formula_fallbacks={report['formula_fallback_count']} "
        f"missing_cells={report['missing_cell_count']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
