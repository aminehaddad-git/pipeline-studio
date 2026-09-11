"""
forecasting.py — Time-series forecasting engine for the BIAT ETL platform.

Implements four classical forecasting methods and an automatic model-selection
protocol based on a train / validation / test split.

No external dependencies (pure Python) — avoids install issues.
"""

import math
import psycopg2
from psycopg2.extras import RealDictCursor

import os
from dotenv import load_dotenv
load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "options": "-c client_encoding=UTF8",
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

SEASON_LENGTH = 12          # monthly data → yearly seasonality
TEST_HORIZON  = 6           # months held out for final evaluation


# ═══════════════════════════════════════════════════════════
#  1. DATA EXTRACTION — build monthly time series
# ═══════════════════════════════════════════════════════════

SERIES_QUERIES = {
    "transactions_count": {
        "label": "Transaction Volume",
        "unit": "transactions",
        "sql": """
            SELECT TO_CHAR(date_transaction, 'YYYY-MM') AS period,
                   COUNT(*)::float AS value
            FROM datawarehouse.fait_transactions
            WHERE date_transaction IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """,
    },
    "transactions_amount": {
        "label": "Transaction Amount",
        "unit": "TND",
        "sql": """
            SELECT TO_CHAR(date_transaction, 'YYYY-MM') AS period,
                   COALESCE(SUM(montant), 0)::float AS value
            FROM datawarehouse.fait_transactions
            WHERE date_transaction IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """,
    },
    "account_openings": {
        "label": "New Accounts Opened",
        "unit": "accounts",
        "sql": """
            SELECT TO_CHAR(date_ouverture, 'YYYY-MM') AS period,
                   COUNT(*)::float AS value
            FROM datawarehouse.dim_compte
            WHERE date_ouverture IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """,
    },
}


def load_series(metric):
    """Return (periods, values) as monthly aggregated lists."""
    if metric not in SERIES_QUERIES:
        raise ValueError(f"Unknown metric: {metric}")
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(SERIES_QUERIES[metric]["sql"])
    rows = cur.fetchall()
    cur.close(); conn.close()
    periods = [r["period"] for r in rows]
    values = [float(r["value"]) for r in rows]
    return periods, values


def next_periods(last_period, h):
    """Given 'YYYY-MM', produce the next h month labels."""
    y, m = int(last_period[:4]), int(last_period[5:7])
    out = []
    for _ in range(h):
        m += 1
        if m > 12:
            m = 1; y += 1
        out.append(f"{y:04d}-{m:02d}")
    return out


# ═══════════════════════════════════════════════════════════
#  2. FORECASTING METHODS
# ═══════════════════════════════════════════════════════════

def moving_average(y, h, window=3):
    """Baseline: forecast = mean of the last `window` observations."""
    hist = list(y); out = []
    w = min(window, len(hist))
    for _ in range(h):
        out.append(sum(hist[-w:]) / w)
        hist.append(out[-1])
    return out


def linear_regression(y, h):
    """Ordinary least-squares trend line extrapolated forward."""
    n = len(y)
    if n < 2:
        return [y[-1] if y else 0.0] * h
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(y) / n
    num = sum((xs[i] - mx) * (y[i] - my) for i in range(n))
    den = sum((x - mx) ** 2 for x in xs) or 1e-9
    b = num / den
    a = my - b * mx
    return [a + b * (n + i) for i in range(h)]


def holt_linear(y, h, alpha=0.3, beta=0.1):
    """Holt's double exponential smoothing: level + trend."""
    if len(y) < 2:
        return [y[-1] if y else 0.0] * h
    level = y[0]
    trend = y[1] - y[0]
    for t in range(1, len(y)):
        prev = level
        level = alpha * y[t] + (1 - alpha) * (level + trend)
        trend = beta * (level - prev) + (1 - beta) * trend
    return [level + (i + 1) * trend for i in range(h)]


def holt_winters(y, h, m=SEASON_LENGTH, alpha=0.2, beta=0.05, gamma=0.3):
    """Holt-Winters triple exponential smoothing (multiplicative seasonality)."""
    if len(y) < 2 * m:
        return holt_linear(y, h, alpha, max(beta, 0.05))

    n_seasons = len(y) // m
    season_avgs = [sum(y[i * m:(i + 1) * m]) / m for i in range(n_seasons)]
    season_avgs = [a if a != 0 else 1e-9 for a in season_avgs]

    seasonal = []
    for i in range(m):
        seasonal.append(
            sum(y[j * m + i] / season_avgs[j] for j in range(n_seasons)) / n_seasons
        )
    seasonal = [s if s != 0 else 1e-9 for s in seasonal]

    level = sum(y[:m]) / m
    trend = (sum(y[m:2 * m]) - sum(y[:m])) / (m * m)

    for t in range(len(y)):
        idx = t % m
        prev = level
        denom = seasonal[idx] or 1e-9
        level = alpha * (y[t] / denom) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev) + (1 - beta) * trend
        seasonal[idx] = gamma * (y[t] / (level or 1e-9)) + (1 - gamma) * seasonal[idx]

    return [(level + (i + 1) * trend) * seasonal[(len(y) + i) % m] for i in range(h)]


METHODS = {
    "moving_average":    {"fn": moving_average,    "label": "Moving Average",     "models": "No trend, no seasonality (baseline)"},
    "linear_regression": {"fn": linear_regression, "label": "Linear Regression",  "models": "Linear trend"},
    "holt_linear":       {"fn": holt_linear,       "label": "Holt Linear",        "models": "Adaptive level + trend"},
    "holt_winters":      {"fn": holt_winters,      "label": "Holt-Winters",       "models": "Level + trend + seasonality"},
}


# ═══════════════════════════════════════════════════════════
#  3. ACCURACY METRICS
# ═══════════════════════════════════════════════════════════

def compute_metrics(actual, predicted):
    """MAE, RMSE, MAPE and R² between actual and predicted values."""
    n = len(actual)
    if n == 0:
        return {"MAE": None, "RMSE": None, "MAPE": None, "R2": None}

    mae = sum(abs(actual[i] - predicted[i]) for i in range(n)) / n
    rmse = math.sqrt(sum((actual[i] - predicted[i]) ** 2 for i in range(n)) / n)

    denom = [a for a in actual if a != 0]
    mape = (sum(abs((actual[i] - predicted[i]) / actual[i])
                for i in range(n) if actual[i] != 0) / len(denom) * 100) if denom else None

    mean = sum(actual) / n
    ss_tot = sum((a - mean) ** 2 for a in actual) or 1e-9
    ss_res = sum((actual[i] - predicted[i]) ** 2 for i in range(n))
    r2 = 1 - ss_res / ss_tot

    return {
        "MAE":  round(mae, 2),
        "RMSE": round(rmse, 2),
        "MAPE": round(mape, 2) if mape is not None else None,
        "R2":   round(r2, 3),
    }


# ═══════════════════════════════════════════════════════════
#  4. PARAMETER TUNING (on a validation split inside training)
# ═══════════════════════════════════════════════════════════

HOLT_GRID = [(a / 20, b / 50) for a in range(1, 20) for b in range(1, 16)]
HW_GRID = [(a, b, g)
           for a in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
           for b in (0.02, 0.05, 0.1, 0.15, 0.2)
           for g in (0.1, 0.2, 0.3, 0.4, 0.5)]


def _tune(fn, train_full, grid, h, seasonal=False):
    """Grid-search parameters on a validation window carved from training data."""
    if len(train_full) <= h + 2:
        return grid[0]
    tr, val = train_full[:-h], train_full[-h:]
    best, best_err = grid[0], float("inf")
    for params in grid:
        try:
            pred = fn(tr, h, SEASON_LENGTH, *params) if seasonal else fn(tr, h, *params)
            err = sum((val[i] - pred[i]) ** 2 for i in range(h))
        except Exception:
            continue
        if err < best_err:
            best, best_err = params, err
    return best


# ═══════════════════════════════════════════════════════════
#  5. MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════

def forecast(metric, horizon=6, method="auto"):
    """
    Run the full forecasting protocol:
      - load the monthly series
      - hold out the last TEST_HORIZON months as an untouched test set
      - tune parameters on a validation split inside the training data
      - evaluate every method on the test set
      - select the best method (lowest RMSE) if method == 'auto'
      - refit on the complete series and forecast `horizon` months ahead
    """
    periods, values = load_series(metric)
    meta = SERIES_QUERIES[metric]

    if len(values) < 6:
        return {
            "error": "Not enough historical data to forecast. "
                     "At least 6 months are required.",
            "months_available": len(values),
        }

    h_test = min(TEST_HORIZON, max(2, len(values) // 5))
    train, test = values[:-h_test], values[-h_test:]

    # ── tune parameters on validation split ──
    holt_params = _tune(holt_linear, train, HOLT_GRID, h_test)
    hw_params = _tune(holt_winters, train, HW_GRID, h_test, seasonal=True)
    tuned = {"holt_linear": holt_params, "holt_winters": hw_params}

    # ── evaluate each method on the held-out test set ──
    comparison = []
    for key, spec in METHODS.items():
        try:
            if key == "holt_linear":
                pred = spec["fn"](train, h_test, *holt_params)
            elif key == "holt_winters":
                pred = spec["fn"](train, h_test, SEASON_LENGTH, *hw_params)
            else:
                pred = spec["fn"](train, h_test)
            m = compute_metrics(test, pred)
        except Exception as e:
            m = {"MAE": None, "RMSE": None, "MAPE": None, "R2": None, "error": str(e)}

        comparison.append({
            "method": key,
            "label": spec["label"],
            "models": spec["models"],
            "params": (list(tuned[key]) if key in tuned else None),
            **m,
        })

    # ── select the best method ──
    valid = [c for c in comparison if c.get("RMSE") is not None]
    best = min(valid, key=lambda c: c["RMSE"])["method"] if valid else "linear_regression"
    selected = best if method == "auto" else method
    if selected not in METHODS:
        selected = "linear_regression"

    # ── refit on the FULL series and forecast forward ──
    spec = METHODS[selected]
    if selected == "holt_linear":
        future = spec["fn"](values, horizon, *holt_params)
    elif selected == "holt_winters":
        future = spec["fn"](values, horizon, SEASON_LENGTH, *hw_params)
    else:
        future = spec["fn"](values, horizon)

    future = [max(0.0, round(v, 2)) for v in future]
    future_periods = next_periods(periods[-1], horizon)

    # ── fitted values over the test window (for the chart) ──
    if selected == "holt_linear":
        backtest = spec["fn"](train, h_test, *holt_params)
    elif selected == "holt_winters":
        backtest = spec["fn"](train, h_test, SEASON_LENGTH, *hw_params)
    else:
        backtest = spec["fn"](train, h_test)
    backtest = [round(v, 2) for v in backtest]

    # ── simple confidence band from test-set RMSE ──
    sel_metrics = next((c for c in comparison if c["method"] == selected), {})
    rmse = sel_metrics.get("RMSE") or 0

    return {
        "metric": metric,
        "label": meta["label"],
        "unit": meta["unit"],
        "history": [{"period": periods[i], "value": round(values[i], 2)}
                    for i in range(len(periods))],
        "forecast": [{"period": future_periods[i],
                      "value": future[i],
                      "lower": max(0.0, round(future[i] - 1.96 * rmse, 2)),
                      "upper": round(future[i] + 1.96 * rmse, 2)}
                     for i in range(horizon)],
        "backtest": [{"period": periods[len(train) + i],
                      "actual": round(test[i], 2),
                      "predicted": backtest[i]}
                     for i in range(h_test)],
        "comparison": comparison,
        "selected_method": selected,
        "selected_label": METHODS[selected]["label"],
        "auto_selected": method == "auto",
        "train_size": len(train),
        "test_size": h_test,
        "horizon": horizon,
        "months_available": len(values),
    }


def available_metrics():
    return [{"key": k, "label": v["label"], "unit": v["unit"]}
            for k, v in SERIES_QUERIES.items()]
