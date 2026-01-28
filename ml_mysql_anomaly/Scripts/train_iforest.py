import pandas as pd
import joblib
import os
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest

df = pd.read_csv("data/features.csv")

features = [
    "hour_of_day",
    "query_count",
    "rows_returned_sum",
    "avg_execution_time",
    "max_execution_time",
    "sensitive_query_count",
    "sensitive_ratio",
    "unique_ip_count",
    "failed_login_count"
]

X = df[features].fillna(0)

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

model = IsolationForest(
    n_estimators=200,
    contamination=0.05,
    random_state=42
)

model.fit(X_scaled)

os.makedirs("model", exist_ok=True)
joblib.dump(model, "model/iforest.pkl")
joblib.dump(scaler, "model/scaler.pkl")

print("🎉 TRAINING FROM CSV COMPLETED")
print(f"✅ Model and scaler saved to 'model/' directory")