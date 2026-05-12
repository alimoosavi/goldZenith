#!/usr/bin/env python3
"""
Utility to load Parquet files into pandas DataFrames.
Works with both orderbook and trade data.
"""

import pandas as pd
from pathlib import Path
import sys


def load_parquet(file_path: str | Path) -> pd.DataFrame:
    """
    Load a Parquet file into a pandas DataFrame.

    Args:
        file_path: Path to the .parquet file (string or Path object)

    Returns:
        pandas DataFrame with the data

    Raises:
        FileNotFoundError: If the file doesn't exist
        Exception: If the file can't be read as Parquet
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not file_path.suffix == ".parquet":
        raise ValueError(f"Expected .parquet file, got: {file_path.suffix}")

    try:
        df = pd.read_parquet(file_path)
        print(f"✓ Loaded {file_path.name}")
        print(f"  Shape: {df.shape}")
        print(f"  Columns: {', '.join(df.columns)}")
        return df
    except Exception as e:
        raise Exception(f"Failed to read {file_path}: {e}")


def load_orderbook_parquet(file_path: str | Path) -> pd.DataFrame:
    """Load an orderbook Parquet file and return as DataFrame."""
    df = load_parquet(file_path)
    # Orderbooks have 'time' + depth level columns
    return df


def load_trades_parquet(file_path: str | Path) -> pd.DataFrame:
    """Load a trades Parquet file and return as DataFrame."""
    df = load_parquet(file_path)
    # Trades have nTran, hEven, volume, price, canceled columns
    return df


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python load_parquet.py <path_to_parquet_file>")
        print("\nExample:")
        print("  python load_parquet.py data/orderbooks/IRTKMOFD0001_1405-01-15.parquet")
        sys.exit(1)

    file_path = sys.argv[1]
    df = load_parquet(file_path)
    print("\nFirst 5 rows:")
    print(df.head())
