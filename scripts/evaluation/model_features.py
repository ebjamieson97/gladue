"""The inputs used by the statistical models, built from data/processed/eval_features.parquet.

Shared by evaluate_3200.py (training and testing) and by anyone applying a saved model.
"""
import numpy as np
import pandas as pd

# Counts of phrases; each enters the model as log(1 + count).
COUNTS = ["n_sentenc", "n_head", "n_open", "n_close", "n_close500", "n_aggmit", "n_vocab", "n_fit",
          "n_reports", "n_operative", "n_dispo", "n_appeal_phrase", "n_conv_appeal", "n_voirdire",
          "n_bail", "n_guilty_plea", "n_do", "n_appellant", "n_appeal", "n_application", "n_close_orders"]
# Yes/no signals (1 or 0).
FLAGS = ["trial_court", "title_trial", "title_appeal", "statute718", "dispo_close", "abandoned",
         "bail_open", "bail_close", "newtrial_close", "not_decided", "proc_open", "chambers", "scc",
         "head_appeal", "open_appeal", "open_application", "open_guilty"]

FEATURE_NAMES = [f"log_{c}" for c in COUNTS] + FLAGS + ["log_chars", "density", "first_pos"]


def model_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Turn rows of eval_features.parquet into the 41 model inputs, in FEATURE_NAMES order."""
    X = pd.DataFrame({f"log_{c}": np.log1p(df[c].astype(float)) for c in COUNTS}, index=df.index)
    for c in FLAGS:
        X[c] = df[c].astype(float)
    X["log_chars"] = np.log(df["n_chars"].astype(float))
    X["density"] = np.minimum(df["n_sentenc"] * 10000.0 / df["n_chars"], 100)
    X["first_pos"] = df["first_pos"].astype(float)
    return X[FEATURE_NAMES]
