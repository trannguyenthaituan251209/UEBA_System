
import pandas as pd
import joblib
import os
import numpy as np
from sklearn.preprocessing import RobustScaler, StandardScaler
from sklearn.ensemble import IsolationForest

df = pd.read_csv("data/features_optimized.csv")
os.makedirs("model", exist_ok=True)

features = [
    "hour_of_day",
    "IsAfterHours",
    "RowsExamined",
    "RowsReturned",
    "ExecutionTime",
    "QueryLength",
    "IsSensitive",
    "QueriesPerDay",
    "RowsExaminedPerDay",
    "DistinctTablesAccessedPerDay",
    "SessionDurationMinutes"
]
for col in ["IsAfterHours", "IsSensitive"]:
    if col in df.columns:
        df[col] = df[col].astype(int)
X = df[features].fillna(0).copy()

# Log-transform các feature lớn (tránh log(0))
log_features = ["RowsExamined", "RowsReturned", "QueriesPerDay", "RowsExaminedPerDay", "SessionDurationMinutes"]
for col in log_features:
    if col in X.columns:
        X[col] = np.log1p(X[col])

scalers = {
    'RobustScaler': RobustScaler(),
    'StandardScaler': StandardScaler()
}

for scaler_name, scaler in scalers.items():
    print(f"\n===== {scaler_name} =====")
    X_scaled = scaler.fit_transform(X)
    iforest = IsolationForest(
        n_estimators=200,
        contamination=0.15,
        max_samples=0.8,
        random_state=42
    )
    iforest.fit(X_scaled)
    # Lưu model/scaler nếu là RobustScaler (dùng cho API)
    if scaler_name == 'RobustScaler':
        tmp_iforest_path = "model/iforest_tmp.pkl"
        tmp_scaler_path = "model/scaler_tmp.pkl"
        joblib.dump(iforest, tmp_iforest_path)
        joblib.dump(scaler, tmp_scaler_path)
        os.replace(tmp_iforest_path, "model/iforest.pkl")
        os.replace(tmp_scaler_path, "model/scaler.pkl")
    scores_all = iforest.decision_function(X_scaled)
    # Top 10 outlier (anomaly_score thấp nhất)
    outlier_idx = np.argsort(scores_all)[:10]
    print("Top 10 anomaly_score thấp nhất:")
    for rank, idx in enumerate(outlier_idx, 1):
        eid = df.iloc[idx]["EmployeeID"]
        score = scores_all[idx]
        print(f"Top {rank}: EmployeeID: {eid}, anomaly_score: {score}")
    # In anomaly_score và rank của user 22
    user22_idx = df.index[df["EmployeeID"] == 22].tolist()
    if user22_idx:
        for i in user22_idx:
            score = scores_all[i]
            rank = (scores_all < score).sum() + 1
            print(f"User 22: index {i}, anomaly_score: {score}, rank: {rank} (thấp nhất là 1)")
    else:
        print("Không tìm thấy user 22 trong dữ liệu!")

print("\n✅ Đã train Isolation Forest với cả RobustScaler và StandardScaler. Model/scaler RobustScaler đã lưu cho API!")