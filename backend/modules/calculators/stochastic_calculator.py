import numpy as np
import pandas as pd


def add_stochastic_oscillator(
    df: pd.DataFrame, k_period: int = 14, d_period: int = 3
) -> pd.DataFrame:
    """
    Menambahkan kolom stochastic %K dan %D.
    """
    result = df.copy()
    lowest_low = result["low_price"].rolling(window=k_period, min_periods=k_period).min()
    highest_high = result["high_price"].rolling(window=k_period, min_periods=k_period).max()

    denominator = highest_high - lowest_low
    denominator = denominator.replace(0, np.nan)

    result["stoch_k"] = ((result["close_price"] - lowest_low) / denominator) * 100
    result["stoch_d"] = result["stoch_k"].rolling(window=d_period, min_periods=d_period).mean()
    return result
