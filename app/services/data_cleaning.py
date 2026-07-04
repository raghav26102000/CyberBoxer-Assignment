"""
Generic Pandas-based cleaning utilities.

These operate on a raw DataFrame read straight from an uploaded CSV and
return a cleaned DataFrame plus a list of file-level error strings
(e.g. missing required columns). Row-level business validation happens
later, in upload_service.py, because it needs to check against the
database (e.g. "does this policy_id exist?").
"""
import pandas as pd


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def check_required_columns(df: pd.DataFrame, required: list[str]) -> list[str]:
    """Returns a list of error strings for any required column that's missing."""
    missing = [col for col in required if col not in df.columns]
    if missing:
        return [f"Missing required column(s): {', '.join(missing)}"]
    return []


def trim_whitespace(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()
        # "nan" strings appear after astype(str) on real NaNs -- restore them
        df[col] = df[col].replace({"nan": None, "None": None, "": None})
    return df


def drop_duplicate_ids(df: pd.DataFrame, id_column: str) -> tuple[pd.DataFrame, int]:
    """Drops rows with a duplicate id (keeps first occurrence).
    Returns (deduped_df, number_dropped)."""
    before = len(df)
    df = df.drop_duplicates(subset=[id_column], keep="first")
    return df, before - len(df)


def parse_date_column(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Parses a column to datetime, invalid values become NaT (caught later)."""
    df = df.copy()
    df[column] = pd.to_datetime(df[column], errors="coerce")
    return df


def to_numeric_column(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Coerces a column to numeric, invalid values become NaN (caught later)."""
    df = df.copy()
    df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def read_csv_upload(file_bytes: bytes) -> pd.DataFrame:
    import io
    return pd.read_csv(io.BytesIO(file_bytes))
