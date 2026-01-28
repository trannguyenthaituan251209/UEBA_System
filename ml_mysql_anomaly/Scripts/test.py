import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

# =========================
# 1. SAMPLE INPUT DATA
# =========================
# Giả lập dữ liệu hành vi người dùng
data = pd.DataFrame([
    {
        "employee_id": 21,
        "role": "DB Admin",
        "hour": 2,
        "query_count": 480,
        "baseline_query": 120,
        "sensitive_ratio": 0.67,
        "failed_login": 1
    },
    {
        "employee_id": 3,
        "role": "Data Analyst",
        "hour": 10,
        "query_count": 90,
        "baseline_query": 100,
        "sensitive_ratio": 0.12,
        "failed_login": 0
    }
])

# =========================
# 2. FEATURE ENGINEERING
# =========================
def build_features(df):
    df = df.copy()
    df["after_hours"] = df["hour"].apply(lambda h: 1 if h < 8 or h > 18 else 0)
    df["query_spike"] = df["query_count"] / df["baseline_query"]
    return df

features_df = build_features(data)

feature_cols = [
    "after_hours",
    "query_spike",
    "sensitive_ratio",
    "failed_login"
]

X = features_df[feature_cols]

# =========================
# 3. ML MODEL
# =========================
model = IsolationForest(
    n_estimators=100,
    contamination=0.3,
    random_state=42
)

model.fit(X)
features_df["anomaly_score"] = model.decision_function(X)
features_df["is_anomaly"] = model.predict(X) == -1

# =========================
# 4. CONTEXT BUILDER
# =========================
def build_context(row):
    context = []

    if row["after_hours"]:
        context.append("accessed the database outside normal working hours")

    if row["query_spike"] > 3:
        context.append(
            f"performed query activity {row['query_spike']:.1f} times higher than their normal baseline"
        )

    if row["sensitive_ratio"] > 0.5:
        context.append("frequently accessed sensitive data")

    if row["failed_login"] > 0:
        context.append("had failed authentication attempts")

    return context

# =========================
# 5. NATURAL LANGUAGE GENERATOR
# =========================
def generate_explanation(row):
    behaviors = build_context(row)

    if not behaviors:
        return (
            f"Employee {row['employee_id']} shows normal database activity "
            f"with no significant deviations from baseline behavior."
        )

    severity = (
        "HIGH" if row["anomaly_score"] < -0.15 else
        "MEDIUM" if row["anomaly_score"] < -0.05 else
        "LOW"
    )

    explanation = (
        f"Employee {row['employee_id']} ({row['role']}) "
        f"{', and '.join(behaviors)}. "
        f"This behavior deviates from their typical usage patterns "
        f"and is assessed as {severity} risk."
    )

    return explanation

# =========================
# 6. RUN & OUTPUT
# =========================
for _, row in features_df.iterrows():
    print("=" * 80)
    print(generate_explanation(row))
    print(f"Anomaly score: {row['anomaly_score']:.3f}")
