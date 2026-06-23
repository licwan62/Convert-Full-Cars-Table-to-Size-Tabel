from __future__ import annotations

import argparse
from pathlib import Path
import re
import unicodedata

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "output"
REQUIRED_COLUMNS = [
    "主车型",
    "品牌",
    "车型名",
    "子车系",
    "分类",
    "结构",
    "版本",
    "年份区间",
    "对应尺码",
]
PICKUP_REQUIRED_COLUMNS = REQUIRED_COLUMNS + [
    "驾驶室类型",
    "货斗长度_ft",
]
NON_PICKUP_FINAL_COLUMNS = [
    "主车型",
    "BRAND",
    "MODEL",
    "YEAR",
    "Const",
    "VERSION",
    "BackSize",
    "桥接状态",
    "原始年份列表",
]
NON_PICKUP_INTERMEDIATE_COLUMNS = [
    "主车型",
    "BRAND",
    "MODEL",
    "SUB_MODEL",
    "YEAR",
    "Const",
    "VERSION",
    "BackSize",
    "桥接状态",
    "原始年份列表",
]
PICKUP_FINAL_COLUMNS = [
    "主车型",
    "BRAND",
    "MODEL",
    "YEAR",
    "Const",
    "VERSION",
    "CAB",
    "BED_FT",
    "BackSize",
    "桥接状态",
    "原始年份列表",
]
PICKUP_INTERMEDIATE_COLUMNS = [
    "主车型",
    "BRAND",
    "MODEL",
    "SUB_MODEL",
    "YEAR",
    "Const",
    "VERSION",
    "CAB",
    "BED_FT",
    "BackSize",
    "桥接状态",
    "原始年份列表",
]
ADAPTER_FINAL_COLUMNS = [
    "YEAR",
    "MAKE",
    "MODEL",
    "SIZE",
]


def read_tsv(path: Path, encoding: str = "utf-8-sig") -> pd.DataFrame:
    """Read a TSV file while preserving text-like values as strings."""
    return pd.read_csv(path, sep="\t", dtype=str, encoding=encoding, keep_default_na=False)


def normalize_text(value: object) -> str:
    if pd.isna(value):
        return ""

    text = str(value)
    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    return text.strip()


def parse_year_list(value: object) -> list[int]:
    text = normalize_text(value).replace("，", "/").replace(",", "/")
    years: list[int] = []

    for part in text.split("/"):
        part = part.strip()
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


def to_int(value: object) -> int | None:
    text = normalize_text(value)
    if not text:
        return None

    try:
        return int(float(text))
    except ValueError:
        match = re.search(r"\d{4}", text)
        return int(match.group(0)) if match else None


def combine_year_text(values: pd.Series) -> str:
    years: set[int] = set()
    for value in values:
        for part in normalize_text(value).split("/"):
            year = to_int(part)
            if year is not None:
                years.add(year)
    return "/".join(str(year) for year in sorted(years))


def combine_versions(values: pd.Series) -> str:
    versions = [normalize_text(value) for value in values]
    has_base = "" in versions
    non_blank = sorted(set(value for value in versions if value))

    if not non_blank:
        return ""
    if has_base:
        return "INCL: " + "/".join(non_blank)
    return "/".join(non_blank)


def split_dedupe_versions(values: pd.Series, add_incl: bool = False) -> str:
    merged = "/".join(normalize_text(value) for value in values if not pd.isna(value))
    merged = merged.replace("INCL:", "").replace("EXCL:", "")

    result: list[str] = []
    seen: set[str] = set()
    for part in merged.split("/"):
        version = normalize_text(part)
        if version and version not in seen:
            seen.add(version)
            result.append(version)

    if not result:
        return ""
    text = "/".join(result)
    return f"INCL: {text}" if add_incl else text


def combine_pickup_versions(values: pd.Series) -> str:
    versions = [normalize_text(value) for value in values]
    return split_dedupe_versions(pd.Series(versions), add_incl="" in versions)


def bridge_status(year_text: object) -> str:
    years = parse_year_list(year_text)
    if not years:
        return "连续年份"

    segment_count = 1
    for previous, current in zip(years, years[1:]):
        if current != previous + 1:
            segment_count += 1

    return "已桥接断档" if segment_count > 1 else "连续年份"


def build_excl_list(group: pd.DataFrame) -> str:
    special_rows = group[
        (group["BackSize"].map(normalize_text) == "无可用尺码")
        & (group["VERSION"].map(normalize_text).str.startswith("INCL:"))
    ]
    versions = []
    for value in special_rows["VERSION"]:
        version = normalize_text(value)
        versions.append(version.split("INCL:", 1)[1].strip())
    return "/".join(sorted(set(value for value in versions if value)))


def build_pickup_excl_list(group: pd.DataFrame) -> str:
    special_rows = group[
        (group["BackSize"].map(normalize_text) == "无可用尺码")
        & (group["VERSION"].map(normalize_text).str.startswith("INCL:"))
    ]
    return split_dedupe_versions(special_rows["VERSION"], add_incl=False)


def combine_bed_ft(values: pd.Series) -> str:
    beds_text: list[str] = []
    seen: set[str] = set()
    for value in values:
        bed = normalize_text(value)
        if bed and bed not in seen:
            seen.add(bed)
            beds_text.append(bed)

    if not beds_text:
        return ""

    beds_num: list[float] = []
    for bed in beds_text:
        try:
            beds_num.append(float(bed))
        except ValueError:
            pass

    if len(beds_num) == len(beds_text):
        minimum = min(beds_num)
        maximum = max(beds_num)
        if minimum == maximum:
            return format_number(minimum)
        return f"{format_number(minimum)}-{format_number(maximum)}"

    return "/".join(sorted(beds_text))


def format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def split_model_raw_list(value: object) -> list[str]:
    text = normalize_text(value)
    text = text.replace("；", ";").replace("\n", ";").replace("\r", ";").replace("｜", "|")
    if not text:
        return []

    result: list[str] = []
    seen: set[str] = set()
    for part in text.split(";"):
        model_raw = normalize_text(part)
        if model_raw and model_raw not in seen:
            seen.add(model_raw)
            result.append(model_raw)
    return result


def parse_year_range(value: object) -> list[int]:
    text = normalize_text(value)
    if not text:
        return []

    parts = [part.strip() for part in text.split("-")]
    start = to_int(parts[0]) if parts else None
    end = to_int(parts[1]) if len(parts) > 1 else start

    if start is None or end is None:
        return []

    lo, hi = sorted((start, end))
    return list(range(lo, hi + 1))


def require_columns(df: pd.DataFrame, required_columns: list[str] | None = None) -> None:
    columns = required_columns or REQUIRED_COLUMNS
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError("Input TSV is missing required columns: " + ", ".join(missing))


def build_non_pickup_compressed(renamed: pd.DataFrame, include_sub_model: bool) -> pd.DataFrame:
    model_keys = ["主车型", "BRAND", "MODEL"]
    if include_sub_model:
        model_keys.append("SUB_MODEL")

    second_keys = [*model_keys, "Const", "BackSize"]
    output_columns = NON_PICKUP_INTERMEDIATE_COLUMNS if include_sub_model else NON_PICKUP_FINAL_COLUMNS
    if renamed.empty:
        return pd.DataFrame(columns=output_columns)

    grouped = (
        renamed.groupby(second_keys, dropna=False, sort=False)
        .agg(
            year_start=("year_start", "min"),
            year_end=("year_end", "max"),
            VERSION=("VERSION_RAW", combine_versions),
            原始年份列表=("原始年份列表", combine_year_text),
        )
        .reset_index()
    )

    grouped["YEAR"] = grouped.apply(
        lambda row: str(int(row["year_start"]))
        if row["year_start"] == row["year_end"]
        else f"{int(row['year_start'])}-{int(row['year_end'])}",
        axis=1,
    )
    grouped["桥接状态"] = grouped["原始年份列表"].map(bridge_status)

    sort_columns = [*model_keys, "Const", "VERSION", "year_start", "year_end"]
    grouped = grouped.sort_values(sort_columns, kind="mergesort").reset_index(drop=True)

    excl_keys = [*model_keys, "year_start", "year_end", "Const"]
    excl_list = (
        grouped.groupby(excl_keys, dropna=False, sort=False)
        .apply(build_excl_list)
        .reset_index(name="EXCL_LIST")
    )

    merged = grouped.merge(excl_list, on=excl_keys, how="left")

    def update_version(row: pd.Series) -> str:
        version = normalize_text(row["VERSION"])
        excl = normalize_text(row["EXCL_LIST"])
        size = normalize_text(row["BackSize"])

        if excl and size and size != "无可用尺码":
            return f"EXCL: {excl}" if not version else f"{version} EXCL: {excl}"
        return version

    merged["VERSION"] = merged.apply(update_version, axis=1)
    merged["year_start"] = merged["year_start"].astype(int)
    merged["year_end"] = merged["year_end"].astype(int)
    result = merged.sort_values(
        [*model_keys, "Const", "year_start", "year_end", "VERSION", "BackSize"],
        kind="mergesort",
    )[output_columns].reset_index(drop=True)

    return result


def transform_non_pickup(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convert the non-pickup Power Query logic into compressed and intermediate tables."""
    require_columns(df)

    text_columns = ["主车型", "品牌", "车型名", "子车系", "分类", "结构", "版本", "年份区间", "对应尺码"]
    work = df.copy()
    for column in text_columns:
        work[column] = work[column].map(normalize_text)

    work = work[
        ~work["分类"].str.contains("皮卡", na=False)
        & (work["对应尺码"] != "")
        & (work["年份区间"] != "")
    ].copy()

    if work.empty:
        return pd.DataFrame(columns=NON_PICKUP_FINAL_COLUMNS), pd.DataFrame(columns=NON_PICKUP_INTERMEDIATE_COLUMNS)

    work["YEAR_LIST"] = work["年份区间"].map(parse_year_list)
    work = work.explode("YEAR_LIST")
    work = work[work["YEAR_LIST"].notna()].copy()
    work["YEAR_SINGLE"] = work["YEAR_LIST"].astype(int)

    first_keys = ["主车型", "品牌", "车型名", "子车系", "结构", "版本", "对应尺码"]
    first_grouped = (
        work.groupby(first_keys, dropna=False, sort=False)
        .agg(
            year_start=("YEAR_SINGLE", "min"),
            year_end=("YEAR_SINGLE", "max"),
            原始年份列表=("YEAR_SINGLE", lambda s: "/".join(str(year) for year in sorted(set(s.astype(int))))),
        )
        .reset_index()
    )

    renamed = first_grouped.rename(
        columns={
            "品牌": "BRAND",
            "车型名": "MODEL",
            "子车系": "SUB_MODEL",
            "结构": "Const",
            "版本": "VERSION_RAW",
            "对应尺码": "BackSize",
        }
    )

    for column in ["主车型", "BRAND", "MODEL", "SUB_MODEL", "Const", "VERSION_RAW", "BackSize", "原始年份列表"]:
        renamed[column] = renamed[column].map(normalize_text)

    compressed = build_non_pickup_compressed(renamed, include_sub_model=False)
    intermediate = build_non_pickup_compressed(renamed, include_sub_model=True)
    return compressed, intermediate


def build_pickup_compressed(renamed: pd.DataFrame, include_sub_model: bool) -> pd.DataFrame:
    model_keys = ["主车型", "BRAND", "MODEL"]
    if include_sub_model:
        model_keys.append("SUB_MODEL")

    second_keys = [*model_keys, "Const", "CAB", "BED_FT", "BackSize"]
    output_columns = PICKUP_INTERMEDIATE_COLUMNS if include_sub_model else PICKUP_FINAL_COLUMNS
    if renamed.empty:
        return pd.DataFrame(columns=output_columns)

    grouped = (
        renamed.groupby(second_keys, dropna=False, sort=False)
        .agg(
            year_start=("year_start", "min"),
            year_end=("year_end", "max"),
            VERSION=("VERSION_RAW", combine_pickup_versions),
            原始年份列表=("原始年份列表", combine_year_text),
        )
        .reset_index()
    )

    grouped["YEAR"] = grouped.apply(
        lambda row: str(int(row["year_start"]))
        if row["year_start"] == row["year_end"]
        else f"{int(row['year_start'])}-{int(row['year_end'])}",
        axis=1,
    )
    grouped["桥接状态"] = grouped["原始年份列表"].map(bridge_status)

    sort_columns = [*model_keys, "Const", "CAB", "BED_FT", "VERSION", "year_start", "year_end"]
    grouped = grouped.sort_values(sort_columns, kind="mergesort").reset_index(drop=True)

    excl_keys = [*model_keys, "year_start", "year_end", "Const", "CAB", "BED_FT"]
    excl_list = (
        grouped.groupby(excl_keys, dropna=False, sort=False)
        .apply(build_pickup_excl_list)
        .reset_index(name="EXCL_LIST")
    )

    merged = grouped.merge(excl_list, on=excl_keys, how="left")

    def update_version(row: pd.Series) -> str:
        version = normalize_text(row["VERSION"])
        excl = normalize_text(row["EXCL_LIST"])
        size = normalize_text(row["BackSize"])

        if excl and size and size != "无可用尺码":
            return f"EXCL: {excl}" if not version else f"{version} EXCL: {excl}"
        return version

    merged["VERSION"] = merged.apply(update_version, axis=1)

    third_keys = [
        *model_keys,
        "year_start",
        "year_end",
        "YEAR",
        "Const",
        "VERSION",
        "CAB",
        "BackSize",
        "桥接状态",
        "原始年份列表",
    ]
    grouped_beds = (
        merged.groupby(third_keys, dropna=False, sort=False)
        .agg(BED_FT=("BED_FT", combine_bed_ft))
        .reset_index()
    )

    grouped_beds["year_start"] = grouped_beds["year_start"].astype(int)
    grouped_beds["year_end"] = grouped_beds["year_end"].astype(int)
    result = grouped_beds.sort_values(
        [*model_keys, "Const", "CAB", "BED_FT", "year_start", "year_end", "VERSION", "BackSize"],
        kind="mergesort",
    )[output_columns].reset_index(drop=True)

    return result


def transform_pickup(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convert the pickup Power Query logic into compressed and intermediate tables."""
    require_columns(df, PICKUP_REQUIRED_COLUMNS)

    text_columns = [
        "主车型",
        "分类",
        "品牌",
        "车型名",
        "子车系",
        "结构",
        "版本",
        "年份区间",
        "驾驶室类型",
        "货斗长度_ft",
        "对应尺码",
    ]
    work = df.copy()
    for column in text_columns:
        work[column] = work[column].map(normalize_text)

    work = work[
        work["分类"].str.contains("皮卡", na=False)
        & (work["对应尺码"] != "")
        & (work["年份区间"] != "")
    ].copy()

    if work.empty:
        return pd.DataFrame(columns=PICKUP_FINAL_COLUMNS), pd.DataFrame(columns=PICKUP_INTERMEDIATE_COLUMNS)

    work["YEAR_LIST"] = work["年份区间"].map(parse_year_list)
    work = work.explode("YEAR_LIST")
    work = work[work["YEAR_LIST"].notna()].copy()
    work["YEAR_SINGLE"] = work["YEAR_LIST"].astype(int)

    first_keys = ["主车型", "品牌", "车型名", "子车系", "结构", "版本", "驾驶室类型", "货斗长度_ft", "对应尺码"]
    first_grouped = (
        work.groupby(first_keys, dropna=False, sort=False)
        .agg(
            year_start=("YEAR_SINGLE", "min"),
            year_end=("YEAR_SINGLE", "max"),
            原始年份列表=("YEAR_SINGLE", lambda s: "/".join(str(year) for year in sorted(set(s.astype(int))))),
        )
        .reset_index()
    )

    renamed = first_grouped.rename(
        columns={
            "品牌": "BRAND",
            "车型名": "MODEL",
            "子车系": "SUB_MODEL",
            "结构": "Const",
            "版本": "VERSION_RAW",
            "驾驶室类型": "CAB",
            "货斗长度_ft": "BED_FT",
            "对应尺码": "BackSize",
        }
    )

    for column in [
        "主车型",
        "BRAND",
        "MODEL",
        "SUB_MODEL",
        "Const",
        "VERSION_RAW",
        "CAB",
        "BED_FT",
        "BackSize",
        "原始年份列表",
    ]:
        renamed[column] = renamed[column].map(normalize_text)

    compressed = build_pickup_compressed(renamed, include_sub_model=False)
    intermediate = build_pickup_compressed(renamed, include_sub_model=True)
    return compressed, intermediate


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible alias for the non-pickup table."""
    return transform_non_pickup(df)[0]


def transform_all(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    non_pickup_compressed, non_pickup_intermediate = transform_non_pickup(df)
    pickup_compressed, pickup_intermediate = transform_pickup(df)
    return non_pickup_compressed, pickup_compressed, non_pickup_intermediate, pickup_intermediate


def transform_adapter(non_pickup_intermediate: pd.DataFrame, pickup_intermediate: pd.DataFrame) -> pd.DataFrame:
    adapter_columns = ["SUB_MODEL", "YEAR", "BackSize"]
    non_pickup_source = non_pickup_intermediate[
        non_pickup_intermediate["BackSize"] != "无可用尺码"
    ][adapter_columns]
    pickup_source = pickup_intermediate[pickup_intermediate["BackSize"] != "无可用尺码"][adapter_columns]

    combined = pd.concat([non_pickup_source, pickup_source], ignore_index=True)
    if combined.empty:
        return pd.DataFrame(columns=ADAPTER_FINAL_COLUMNS)

    combined = combined.rename(columns={"BackSize": "SIZE"})
    combined["MODEL_RAW_LIST"] = combined["SUB_MODEL"].map(split_model_raw_list)
    combined = combined.drop(columns=["SUB_MODEL"]).explode("MODEL_RAW_LIST")
    combined = combined[combined["MODEL_RAW_LIST"].notna()].copy()
    combined["MODEL_RAW"] = combined["MODEL_RAW_LIST"].map(normalize_text)
    combined = combined[combined["MODEL_RAW"] != ""].copy()

    combined["MAKE"] = combined["MODEL_RAW"].map(
        lambda value: normalize_text(value.split("|", 1)[0]) if "|" in value else ""
    )
    combined["MODEL"] = combined["MODEL_RAW"].map(
        lambda value: normalize_text(value.split("|", 1)[1]) if "|" in value else normalize_text(value)
    )
    combined = combined.drop(columns=["MODEL_RAW_LIST", "MODEL_RAW"])

    combined["YEAR_LIST"] = combined["YEAR"].map(parse_year_range)
    combined = combined.drop(columns=["YEAR"]).explode("YEAR_LIST")
    combined = combined[combined["YEAR_LIST"].notna()].copy()
    combined["YEAR"] = combined["YEAR_LIST"].astype(int)
    combined = combined.drop(columns=["YEAR_LIST"])

    for column in ["MAKE", "MODEL", "SIZE"]:
        combined[column] = combined[column].map(normalize_text)

    result = combined[ADAPTER_FINAL_COLUMNS].copy()
    result = result[(result["MAKE"] != "") & (result["MODEL"] != "")]
    result = result.drop_duplicates().reset_index(drop=True)
    return result


def transform_all_outputs(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    non_pickup_compressed, pickup_compressed, non_pickup_intermediate, pickup_intermediate = transform_all(df)
    adapter_df = transform_adapter(non_pickup_intermediate, pickup_intermediate)
    return non_pickup_compressed, pickup_compressed, adapter_df, non_pickup_intermediate, pickup_intermediate


def write_outputs(
    non_pickup_df: pd.DataFrame,
    pickup_df: pd.DataFrame,
    adapter_df: pd.DataFrame,
    non_pickup_intermediate_df: pd.DataFrame,
    pickup_intermediate_df: pd.DataFrame,
    input_path: Path,
    output_dir: Path,
) -> dict[str, Path]:
    stem = input_path.stem
    run_output_dir = output_dir / stem
    run_output_dir.mkdir(parents=True, exist_ok=True)

    non_pickup_tsv_path = run_output_dir / f"{stem}_非皮卡尺码压缩.tsv"
    pickup_tsv_path = run_output_dir / f"{stem}_皮卡尺码压缩.tsv"
    adapter_tsv_path = run_output_dir / f"{stem}_适配器.tsv"
    non_pickup_intermediate_tsv_path = run_output_dir / f"{stem}_非皮卡中间压缩.tsv"
    pickup_intermediate_tsv_path = run_output_dir / f"{stem}_皮卡中间压缩.tsv"
    xlsx_path = run_output_dir / f"{stem}_output.xlsx"

    non_pickup_df.to_csv(non_pickup_tsv_path, sep="\t", index=False, encoding="utf-8-sig")
    pickup_df.to_csv(pickup_tsv_path, sep="\t", index=False, encoding="utf-8-sig")
    adapter_df.to_csv(adapter_tsv_path, sep="\t", index=False, encoding="utf-8-sig")
    non_pickup_intermediate_df.to_csv(non_pickup_intermediate_tsv_path, sep="\t", index=False, encoding="utf-8-sig")
    pickup_intermediate_df.to_csv(pickup_intermediate_tsv_path, sep="\t", index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        non_pickup_df.to_excel(writer, sheet_name="非皮卡", index=False)
        pickup_df.to_excel(writer, sheet_name="皮卡", index=False)
        adapter_df.to_excel(writer, sheet_name="适配器", index=False)
        non_pickup_intermediate_df.to_excel(writer, sheet_name="非皮卡中间", index=False)
        pickup_intermediate_df.to_excel(writer, sheet_name="皮卡中间", index=False)

    return {
        "output_dir": run_output_dir,
        "non_pickup_tsv": non_pickup_tsv_path,
        "pickup_tsv": pickup_tsv_path,
        "adapter_tsv": adapter_tsv_path,
        "non_pickup_intermediate_tsv": non_pickup_intermediate_tsv_path,
        "pickup_intermediate_tsv": pickup_intermediate_tsv_path,
        "xlsx": xlsx_path,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert a TSV file using pandas.")
    parser.add_argument("input", type=Path, help="Path to the input TSV file.")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated files. Defaults to data/output.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8-sig",
        help="Input file encoding. Defaults to utf-8-sig.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    df = read_tsv(input_path, encoding=args.encoding)
    non_pickup_df, pickup_df, adapter_df, non_pickup_intermediate, pickup_intermediate = transform_all_outputs(df)
    output_paths = write_outputs(
        non_pickup_df,
        pickup_df,
        adapter_df,
        non_pickup_intermediate,
        pickup_intermediate,
        input_path,
        args.output_dir,
    )

    print(f"Non-pickup rows: {len(non_pickup_df)}")
    print(f"Pickup rows: {len(pickup_df)}")
    print(f"Adapter rows: {len(adapter_df)}")
    print(f"Non-pickup intermediate rows: {len(non_pickup_intermediate)}")
    print(f"Pickup intermediate rows: {len(pickup_intermediate)}")
    print(f"Output dir: {output_paths['output_dir']}")
    print(f"Non-pickup TSV: {output_paths['non_pickup_tsv']}")
    print(f"Pickup TSV: {output_paths['pickup_tsv']}")
    print(f"Adapter TSV: {output_paths['adapter_tsv']}")
    print(f"Non-pickup intermediate TSV: {output_paths['non_pickup_intermediate_tsv']}")
    print(f"Pickup intermediate TSV: {output_paths['pickup_intermediate_tsv']}")
    print(f"Excel: {output_paths['xlsx']}")


if __name__ == "__main__":
    main()
