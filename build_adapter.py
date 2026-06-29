from __future__ import annotations

import argparse
from pathlib import Path
import re
import unicodedata

import pandas as pd

from field_profile import apply_field_profile, load_field_profile


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "output"
DEFAULT_SUB_MODEL_PATH = PROJECT_ROOT / "database" / "submodels.tsv"
DEFAULT_FITMENTS_PATH = PROJECT_ROOT / "database" / "4Afitment_base.tsv"
DEFAULT_SUB_MODEL_FACT_OUTPUT_PATH = PROJECT_ROOT / "data" / "tmp" / "submodels_adapter_fact.tsv"
DEFAULT_FITMENTS_FACT_OUTPUT_PATH = PROJECT_ROOT / "data" / "tmp" / "fitments_adapter_fact.tsv"
BACKSIZE_SOURCE_COLUMN = "最终尺码"
LEGACY_FRONT_MODEL_COLUMNS = ["车型名", "车姓名"]
ADAPTER_REQUIRED_COLUMNS = [
    "品牌",
    "前台车型",
    "子车系",
    "年份区间",
    BACKSIZE_SOURCE_COLUMN,
]
ADAPTER_FINAL_COLUMNS = [
    "YEAR",
    "MAKE",
    "MODEL",
    "SIZE",
]
ADAPTER_FACT_REQUIRED_COLUMNS = [
    "Year",
    "候选车型",
]
ADAPTER_FACT_FINAL_COLUMNS = [
    "YEAR",
    "MAKE",
    "MODEL",
]
ADAPTER_LOG_FINAL_COLUMNS = [
    "检查表",
    "YEAR",
    "MAKE",
    "MODEL",
    "SIZE",
    "结果",
    "原因",
]


def read_tsv(path: Path, encoding: str = "utf-8-sig") -> pd.DataFrame:
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


def to_int(value: object) -> int | None:
    text = normalize_text(value)
    if not text:
        return None

    try:
        return int(float(text))
    except ValueError:
        match = re.search(r"\d{4}", text)
        return int(match.group(0)) if match else None


def parse_year_range(value: object) -> list[int]:
    text = normalize_text(value)
    if not text:
        return []

    years: list[int] = []
    for segment in re.split(r"[;/,，；]", text):
        segment = normalize_text(segment)
        if not segment:
            continue
        parts = [part.strip() for part in segment.split("-")]
        start = to_int(parts[0]) if parts else None
        end = to_int(parts[1]) if len(parts) > 1 else start

        if start is None or end is None:
            continue

        lo, hi = sorted((start, end))
        years.extend(range(lo, hi + 1))

    return sorted(set(years))


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


def normalize_input_schema(df: pd.DataFrame, field_profile: dict[str, object] | None = None) -> pd.DataFrame:
    return apply_field_profile(df, field_profile)


def require_columns(df: pd.DataFrame, required_columns: list[str]) -> None:
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError("Input TSV is missing required columns: " + ", ".join(missing))


def has_columns(df: pd.DataFrame, columns: list[str]) -> bool:
    return all(column in df.columns for column in columns)


def split_make_model(value: object) -> tuple[str, str]:
    text = normalize_text(value)
    if "|" not in text:
        return "", text
    make, model = text.split("|", 1)
    return normalize_text(make), normalize_text(model)


def empty_adapter() -> pd.DataFrame:
    return pd.DataFrame(columns=ADAPTER_FINAL_COLUMNS)


def empty_adapter_log() -> pd.DataFrame:
    return pd.DataFrame(columns=ADAPTER_LOG_FINAL_COLUMNS)


def empty_adapter_fact() -> pd.DataFrame:
    return pd.DataFrame(columns=ADAPTER_FACT_FINAL_COLUMNS)


def atomize_adapter_fact_table(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work.columns = [normalize_text(column) for column in work.columns]
    if not all(column in work.columns for column in ADAPTER_FACT_REQUIRED_COLUMNS) and len(work.columns) >= 5:
        first_row = pd.DataFrame([dict(zip(work.columns, work.columns))])
        work = pd.concat([first_row, work], ignore_index=True)
        work = work.rename(
            columns={
                work.columns[0]: "Year",
                work.columns[1]: "主车型",
                work.columns[2]: "结构",
                work.columns[3]: "版本",
                work.columns[4]: "候选车型",
            }
        )
    require_columns(work, ADAPTER_FACT_REQUIRED_COLUMNS)

    work = work[ADAPTER_FACT_REQUIRED_COLUMNS].copy()
    for column in ADAPTER_FACT_REQUIRED_COLUMNS:
        work[column] = work[column].map(normalize_text)

    work["YEAR_LIST"] = work["Year"].map(parse_year_range)
    work["MODEL_RAW_LIST"] = work["候选车型"].map(split_model_raw_list)
    work = work.drop(columns=["Year", "候选车型"]).explode("YEAR_LIST").explode("MODEL_RAW_LIST")
    work = work[(work["YEAR_LIST"].notna()) & (work["MODEL_RAW_LIST"].notna())].copy()
    if work.empty:
        return empty_adapter_fact()

    work["YEAR"] = work["YEAR_LIST"].astype(int)
    work[["MAKE", "MODEL"]] = work["MODEL_RAW_LIST"].map(split_make_model).apply(pd.Series)
    result = work[ADAPTER_FACT_FINAL_COLUMNS].copy()
    result = result[(result["MAKE"] != "") & (result["MODEL"] != "")]
    return result.drop_duplicates().sort_values(ADAPTER_FACT_FINAL_COLUMNS, kind="mergesort").reset_index(drop=True)


def load_sub_model_fact_table(
    sub_model_path: Path = DEFAULT_SUB_MODEL_PATH,
    fact_output_path: Path | None = DEFAULT_SUB_MODEL_FACT_OUTPUT_PATH,
    encoding: str = "utf-8-sig",
) -> pd.DataFrame:
    if not sub_model_path.exists():
        raise FileNotFoundError(f"Sub-model fact source not found: {sub_model_path}")

    fact_df = atomize_adapter_fact_table(read_tsv(sub_model_path, encoding=encoding))
    if fact_output_path is not None:
        fact_output_path.parent.mkdir(parents=True, exist_ok=True)
        fact_df.to_csv(fact_output_path, sep="\t", index=False, encoding="utf-8-sig")
    return fact_df


def normalize_fitments_fact_table(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work.columns = [normalize_text(column).upper() for column in work.columns]
    require_columns(work, ADAPTER_FACT_FINAL_COLUMNS)

    work = work[ADAPTER_FACT_FINAL_COLUMNS].copy()
    for column in ADAPTER_FACT_FINAL_COLUMNS:
        work[column] = work[column].map(normalize_text)

    work["YEAR_LIST"] = work["YEAR"].map(parse_year_range)
    work = work.drop(columns=["YEAR"]).explode("YEAR_LIST")
    work = work[work["YEAR_LIST"].notna()].copy()
    if work.empty:
        return empty_adapter_fact()

    work["YEAR"] = work["YEAR_LIST"].astype(int)
    result = work[ADAPTER_FACT_FINAL_COLUMNS].copy()
    result = result[(result["MAKE"] != "") & (result["MODEL"] != "")]
    return result.drop_duplicates().sort_values(ADAPTER_FACT_FINAL_COLUMNS, kind="mergesort").reset_index(drop=True)


def load_fitments_fact_table(
    fitments_path: Path = DEFAULT_FITMENTS_PATH,
    fact_output_path: Path | None = DEFAULT_FITMENTS_FACT_OUTPUT_PATH,
    encoding: str = "utf-8-sig",
) -> pd.DataFrame:
    if not fitments_path.exists():
        raise FileNotFoundError(f"Fitments fact source not found: {fitments_path}")

    fact_df = normalize_fitments_fact_table(read_tsv(fitments_path, encoding=encoding))
    if fact_output_path is not None:
        fact_output_path.parent.mkdir(parents=True, exist_ok=True)
        fact_df.to_csv(fact_output_path, sep="\t", index=False, encoding="utf-8-sig")
    return fact_df


def build_raw_adapter(
    df: pd.DataFrame,
    remove_null_size: bool = False,
    field_profile: dict[str, object] | None = None,
) -> pd.DataFrame:
    df = normalize_input_schema(df, field_profile=field_profile)
    if not has_columns(df, ADAPTER_REQUIRED_COLUMNS):
        return empty_adapter()
    require_columns(df, ADAPTER_REQUIRED_COLUMNS)

    work = df[["子车系", "年份区间", BACKSIZE_SOURCE_COLUMN]].copy()
    for column in ["子车系", "年份区间", BACKSIZE_SOURCE_COLUMN]:
        work[column] = work[column].map(normalize_text)
    if (work["年份区间"] == "").any():
        bad_count = int((work["年份区间"] == "").sum())
        raise ValueError(f"适配器存在 {bad_count} 行年份区间为空，请补齐年份区间后再生成适配器。")

    size_mask = work[BACKSIZE_SOURCE_COLUMN] != ""
    if remove_null_size:
        size_mask &= work[BACKSIZE_SOURCE_COLUMN] != "无可用尺码"
    work = work[(work["子车系"] != "") & (work["年份区间"] != "") & size_mask].copy()
    if work.empty:
        return empty_adapter()

    combined = work.rename(columns={"子车系": "SUB_MODEL", "年份区间": "YEAR", BACKSIZE_SOURCE_COLUMN: "SIZE"})
    combined["MODEL_RAW_LIST"] = combined["SUB_MODEL"].map(split_model_raw_list)
    combined = combined.drop(columns=["SUB_MODEL"]).explode("MODEL_RAW_LIST")
    combined = combined[combined["MODEL_RAW_LIST"].notna()].copy()
    combined["MODEL_RAW"] = combined["MODEL_RAW_LIST"].map(normalize_text)
    combined = combined[combined["MODEL_RAW"] != ""].copy()

    combined[["MAKE", "MODEL"]] = combined["MODEL_RAW"].map(split_make_model).apply(pd.Series)
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
    return result.drop_duplicates().reset_index(drop=True)


def filter_adapter_by_fact_table(
    adapter_df: pd.DataFrame,
    fact_df: pd.DataFrame,
    check_name: str,
    reason: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if adapter_df.empty:
        return empty_adapter(), empty_adapter_log()
    if fact_df.empty:
        removed = adapter_df.copy()
        kept = empty_adapter()
    else:
        fact_keys = set(
            fact_df[ADAPTER_FACT_FINAL_COLUMNS].drop_duplicates().itertuples(index=False, name=None)
        )
        keep_mask = adapter_df.apply(
            lambda row: (int(row["YEAR"]), normalize_text(row["MAKE"]), normalize_text(row["MODEL"])) in fact_keys,
            axis=1,
        )
        kept = adapter_df[keep_mask].copy()
        removed = adapter_df[~keep_mask].copy()

    if removed.empty:
        return kept[ADAPTER_FINAL_COLUMNS].drop_duplicates().reset_index(drop=True), empty_adapter_log()

    log_df = removed[ADAPTER_FINAL_COLUMNS].copy()
    log_df.insert(0, "检查表", check_name)
    log_df["结果"] = "去除"
    log_df["原因"] = reason
    return (
        kept[ADAPTER_FINAL_COLUMNS].drop_duplicates().reset_index(drop=True),
        log_df[ADAPTER_LOG_FINAL_COLUMNS].reset_index(drop=True),
    )


def build_adapter_outputs(
    df: pd.DataFrame,
    sub_model_path: Path = DEFAULT_SUB_MODEL_PATH,
    fitments_path: Path = DEFAULT_FITMENTS_PATH,
    sub_model_fact_output_path: Path | None = DEFAULT_SUB_MODEL_FACT_OUTPUT_PATH,
    fitments_fact_output_path: Path | None = DEFAULT_FITMENTS_FACT_OUTPUT_PATH,
    encoding: str = "utf-8-sig",
    remove_null_size: bool = False,
    field_profile: dict[str, object] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw_adapter = build_raw_adapter(df, remove_null_size=remove_null_size, field_profile=field_profile)
    sub_model_fact_df = load_sub_model_fact_table(
        sub_model_path=sub_model_path,
        fact_output_path=sub_model_fact_output_path,
        encoding=encoding,
    )
    sub_model_adapter_df, sub_model_log_df = filter_adapter_by_fact_table(
        raw_adapter,
        sub_model_fact_df,
        check_name="sub_model",
        reason="YEAR/MAKE/MODEL 不在子车系事实表",
    )
    fitments_fact_df = load_fitments_fact_table(
        fitments_path=fitments_path,
        fact_output_path=fitments_fact_output_path,
        encoding=encoding,
    )
    adapter_df, fitments_log_df = filter_adapter_by_fact_table(
        sub_model_adapter_df,
        fitments_fact_df,
        check_name="fitments",
        reason="YEAR/MAKE/MODEL 不在适配器全量事实表",
    )
    logs = [log_df for log_df in [sub_model_log_df, fitments_log_df] if not log_df.empty]
    adapter_log_df = pd.concat(logs, ignore_index=True) if logs else empty_adapter_log()
    return adapter_df, adapter_log_df, sub_model_fact_df, fitments_fact_df


def transform_adapter(
    df: pd.DataFrame,
    sub_model_path: Path = DEFAULT_SUB_MODEL_PATH,
    fitments_path: Path = DEFAULT_FITMENTS_PATH,
    sub_model_fact_output_path: Path | None = DEFAULT_SUB_MODEL_FACT_OUTPUT_PATH,
    fitments_fact_output_path: Path | None = DEFAULT_FITMENTS_FACT_OUTPUT_PATH,
    encoding: str = "utf-8-sig",
    remove_null_size: bool = False,
    field_profile: dict[str, object] | None = None,
) -> pd.DataFrame:
    return build_adapter_outputs(
        df,
        sub_model_path=sub_model_path,
        fitments_path=fitments_path,
        sub_model_fact_output_path=sub_model_fact_output_path,
        fitments_fact_output_path=fitments_fact_output_path,
        encoding=encoding,
        remove_null_size=remove_null_size,
        field_profile=field_profile,
    )[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate adapter TSV and atomized adapter fact table.")
    parser.add_argument("input", type=Path, help="Path to the input allcars TSV file.")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated adapter files. Defaults to data/tmp.",
    )
    parser.add_argument(
        "--sub-model",
        dest="sub_model",
        type=Path,
        default=DEFAULT_SUB_MODEL_PATH,
        help="Sub-model source TSV for the first adapter check. Defaults to database/submodels.tsv.",
    )
    parser.add_argument(
        "--fitments",
        type=Path,
        default=DEFAULT_FITMENTS_PATH,
        help="Full fitments fact TSV for the second adapter check. Defaults to database/4Afitment_base.tsv.",
    )
    parser.add_argument(
        "--sub-model-fact-output",
        type=Path,
        default=None,
        help="Atomized sub-model fact output TSV. Defaults to output-dir/adapter/submodels_adapter_fact.tsv.",
    )
    parser.add_argument(
        "--fitments-fact-output",
        type=Path,
        default=None,
        help="Normalized fitments fact output TSV. Defaults to output-dir/adapter/fitments_adapter_fact.tsv.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8-sig",
        help="Input file encoding. Defaults to utf-8-sig.",
    )
    parser.add_argument(
        "--field-profile",
        type=Path,
        default=None,
        help="YAML file that maps input column names to the script's standard fields.",
    )
    parser.add_argument(
        "--remove-null-size",
        action="store_true",
        help="Filter out rows whose size is 无可用尺码. By default these rows are kept.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    adapter_dir = output_dir / input_path.stem / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    sub_model_fact_output = (
        args.sub_model_fact_output.resolve()
        if args.sub_model_fact_output is not None
        else adapter_dir / "submodels_adapter_fact.tsv"
    )
    fitments_fact_output = (
        args.fitments_fact_output.resolve()
        if args.fitments_fact_output is not None
        else adapter_dir / "fitments_adapter_fact.tsv"
    )

    field_profile = load_field_profile(args.field_profile.resolve() if args.field_profile else None)
    df = read_tsv(input_path, encoding=args.encoding)
    adapter_df, adapter_log_df, sub_model_fact_df, fitments_fact_df = build_adapter_outputs(
        df,
        sub_model_path=args.sub_model.resolve(),
        fitments_path=args.fitments.resolve(),
        sub_model_fact_output_path=sub_model_fact_output,
        fitments_fact_output_path=fitments_fact_output,
        encoding=args.encoding,
        remove_null_size=args.remove_null_size,
        field_profile=field_profile,
    )

    adapter_path = adapter_dir / f"{input_path.stem}_适配器.tsv"
    adapter_log_path = adapter_dir / f"{input_path.stem}_适配器log.tsv"
    adapter_df.to_csv(adapter_path, sep="\t", index=False, encoding="utf-8-sig")
    adapter_log_df.to_csv(adapter_log_path, sep="\t", index=False, encoding="utf-8-sig")

    print("写入完成")
    print(f"Adapter TSV: {adapter_path}")
    print(f"Adapter log TSV: {adapter_log_path}")
    print(f"Sub-model fact TSV: {sub_model_fact_output}")
    print(f"Fitments fact TSV: {fitments_fact_output}")


if __name__ == "__main__":
    main()
