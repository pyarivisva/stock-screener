import pandas as pd


def add_bollinger_bands(
    df: pd.DataFrame, window: int = 20, std_multiplier: float = 2.0
) -> pd.DataFrame:
    """
    Menambahkan Bollinger Bands (upper, middle, lower, width).
    """
    result = df.copy()
    rolling_mean = result["close_price"].rolling(window=window, min_periods=window).mean()
    rolling_std = result["close_price"].rolling(window=window, min_periods=window).std()

    result["bb_middle"] = rolling_mean
    result["bb_upper"] = rolling_mean + (std_multiplier * rolling_std)
    result["bb_lower"] = rolling_mean - (std_multiplier * rolling_std)
    result["bb_width"] = result["bb_upper"] - result["bb_lower"]
    return result
