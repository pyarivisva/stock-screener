import pandas as pd


def add_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """
    Menambahkan MA5, MA20, dan MA50 ke dataframe.
    """
    result = df.copy()
    result["ma5"] = result["close_price"].rolling(window=5, min_periods=5).mean()
    result["ma20"] = result["close_price"].rolling(window=20, min_periods=20).mean()
    result["ma50"] = result["close_price"].rolling(window=50, min_periods=50).mean()
    return result
