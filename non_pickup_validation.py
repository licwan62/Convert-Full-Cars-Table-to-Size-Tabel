from __future__ import annotations

import re
import unicodedata

import pandas as pd


def normalize_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value)
    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    return text.strip()


def to_int(value: object) -> int | None:
    text = normalize_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        match = re.search(r"\d{4}", text)
        return int(match.group(0)) if match else None


def parse_year_list(value: object) -> list[int]:
    text = normalize_text(value).replace("，", "/").replace(",", "/").replace(";", "/")
    years: list[int] = []
    for part in text.split("/"):
        part = normalize_text(part)
        if not part:
            continue
        pieces = [item.strip() for item in part.split("-")]
        start = to_int(pieces[0]) if pieces else None
        end = to_int(pieces[1]) if len(pieces) >= 2 else start
        if start is None or end is None:
            continue
        lo, hi = sorted((start, end))
        years.extend(range(lo, hi + 1))
    return sorted(set(years))


def split_output_tokens(value: object) -> set[str]:
    text = normalize_text(value)
    if not text:
        return set()
    return {part for part in (normalize_text(item) for item in text.split("/")) if part}


def split_version_tokens(value: object) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []
    text = re.sub(r"\b(?:INCL|Incl|incl|EXCL|Excl|excl|EXP|Exp|exp)\s*:", "", text)
    text = re.sub(r"\b([A-Za-z])\s*/\s*([A-Za-z])\b", r"\1__VERSION_SLASH__\2", text)
    result: list[str] = []
    seen: set[str] = set()
    for part in text.split("/"):
        version = normalize_text(part).replace("__VERSION_SLASH__", "/")
        if version and version not in seen:
            seen.add(version)
            result.append(version)
    return result


def record_version_matches(record_version: object, atom_version: object) -> bool:
    record_text = normalize_text(record_version)
    atom_text = normalize_text(atom_version)
    if not record_text:
        return atom_text == ""
    atom_tokens = set(split_version_tokens(atom_text))
    lower = record_text.lower()
    if lower.startswith("incl:"):
        tokens = set(split_version_tokens(record_text))
        return atom_text == "" or atom_text in tokens or bool(atom_tokens & tokens)
    tokens = set(split_version_tokens(record_text))
    return atom_text in tokens or bool(atom_tokens & tokens)


def split_model_expression(value: object) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for part in text.split("/"):
        model = normalize_text(part)
        if model and model not in seen:
            seen.add(model)
            result.append(model)
    return result


def model_expression_matches(record_model: object, atom_model: object) -> bool:
    if normalize_text(record_model) == normalize_text(atom_model):
        return True
    models = split_model_expression(record_model)
    atom = normalize_text(atom_model)
    return atom in models if models else atom == ""


def row_value(row: pd.Series, *columns: str) -> object:
    for column in columns:
        if column in row.index:
            return row.get(column, "")
    return ""


def atom_year_value(atom: pd.Series) -> int | None:
    value = row_value(atom, "YEAR_SINGLE", "YEAR")
    return to_int(value)


def record_years(record: pd.Series) -> set[int]:
    if "year_start" in record.index and "year_end" in record.index:
        start = to_int(record.get("year_start", ""))
        end = to_int(record.get("year_end", ""))
        if start is not None and end is not None:
            lo, hi = sorted((start, end))
            return set(range(lo, hi + 1))
    return set(parse_year_list(row_value(record, "YEAR")))


def non_pickup_record_matches_atom_size(record: pd.Series, atom: pd.Series) -> str | None:
    if normalize_text(row_value(record, "BRAND", "MAKE")) != normalize_text(row_value(atom, "BRAND", "MAKE")):
        return None
    if not model_expression_matches(row_value(record, "MODEL"), row_value(atom, "MODEL")):
        return None

    atom_year = atom_year_value(atom)
    if atom_year is None or atom_year not in record_years(record):
        return None

    record_consts = split_output_tokens(row_value(record, "CONST")) or split_output_tokens(row_value(record, "RAW-CONST"))
    atom_const = normalize_text(row_value(atom, "Const", "CONST"))
    if record_consts and atom_const not in record_consts:
        return None

    if not record_version_matches(row_value(record, "VERSION"), row_value(atom, "VERSION_RAW", "VERSION")):
        return None
    return normalize_text(row_value(record, "BACKSIZE"))


def non_pickup_atom_matches(records: pd.DataFrame, atom: pd.Series) -> list[tuple[object, str]]:
    matches: list[tuple[object, str]] = []
    for record_index, record in records.iterrows():
        size = non_pickup_record_matches_atom_size(record, atom)
        if size:
            matches.append((record_index, size))
    return matches


def non_pickup_candidate_validation_reason(records: pd.DataFrame, atoms: pd.DataFrame) -> str:
    for _, atom in atoms.iterrows():
        matches = non_pickup_atom_matches(records, atom)
        matched_sizes = [size for _, size in matches]
        atom_brand = normalize_text(row_value(atom, "BRAND", "MAKE"))
        atom_model = normalize_text(row_value(atom, "MODEL"))
        atom_year = atom_year_value(atom)
        atom_const = normalize_text(row_value(atom, "Const", "CONST"))
        atom_size = normalize_text(row_value(atom, "BackSize", "BACKSIZE"))
        if len(matched_sizes) > 1:
            return f"{atom_brand} {atom_model} {atom_year} {atom_const} 原子事实对应多条候选记录"
        if not matched_sizes:
            return f"{atom_brand} {atom_model} {atom_year} {atom_const} 原子事实未被候选记录覆盖"
        if matched_sizes[0] != atom_size:
            return f"{atom_brand} {atom_model} {atom_year} 命中尺码 {matched_sizes[0]} != 原子尺码 {atom_size}"
    return ""


def non_pickup_atoms_in_record_scope(atoms: pd.DataFrame, record: pd.Series | dict[str, object]) -> pd.DataFrame:
    scoped_indexes: list[object] = []
    record_series = record if isinstance(record, pd.Series) else pd.Series(record)
    for atom_index, atom in atoms.iterrows():
        if non_pickup_record_matches_atom_size(record_series, atom):
            scoped_indexes.append(atom_index)
    return atoms.loc[scoped_indexes]
