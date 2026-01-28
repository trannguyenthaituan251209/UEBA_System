import pyodbc
import pandas as pd
import joblib

print("🔍 START UEBA DEMO SCAN")

# =========================
# 1. CONNECT TO DATABASE
# =========================
conn = pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=localhost\\SQLEXPRESS;"
        "DATABASE=AuthenticationManager;"
        "Trusted_Connection=yes;"
        "Encrypt=no;"
        "TrustServerCertificate=yes;"
)

# =========================
# 2. LOAD MODEL & SCALER
# =========================
model = joblib.load("model/iforest.pkl")
scaler = joblib.load("model/scaler.pkl")
print("🧠 Model & scaler loaded")

# =========================
# 3. FEATURE QUERY (GIỐNG TRAIN CSV)
# =========================
sql = """
WITH TimeBuckets AS (
    SELECT
        q.EmployeeID,
        DATEADD(hour, DATEDIFF(hour, 0, q.QueryTime), 0) AS TimeBucket,
        COUNT(*) AS query_count,
        SUM(q.RowsReturned) AS rows_returned_sum,
        AVG(q.ExecutionTime) AS avg_execution_time,
        MAX(q.ExecutionTime) AS max_execution_time,
        SUM(CASE WHEN q.IsSensitive = 1 THEN 1 ELSE 0 END) AS sensitive_query_count
    FROM QueryLogs q
    GROUP BY
        q.EmployeeID,
        DATEADD(hour, DATEDIFF(hour, 0, q.QueryTime), 0)
),
AuthAgg AS (
    SELECT
        EmployeeID,
        DATEADD(hour, DATEDIFF(hour, 0, LoginTime), 0) AS TimeBucket,
        COUNT(DISTINCT SourceIP) AS unique_ip_count,
        SUM(CASE WHEN LoginStatus = 'FAIL' THEN 1 ELSE 0 END) AS failed_login_count
    FROM AuthenticationLogs
    GROUP BY
        EmployeeID,
        DATEADD(hour, DATEDIFF(hour, 0, LoginTime), 0)
)
SELECT
    t.EmployeeID,
    t.TimeBucket,
    DATEPART(hour, t.TimeBucket) AS hour_of_day,
    t.query_count,
    t.rows_returned_sum,
    t.avg_execution_time,
    t.max_execution_time,
    t.sensitive_query_count,
    CAST(t.sensitive_query_count AS FLOAT) / NULLIF(t.query_count, 0) AS sensitive_ratio,
    ISNULL(a.unique_ip_count, 0) AS unique_ip_count,
    ISNULL(a.failed_login_count, 0) AS failed_login_count
FROM TimeBuckets t
LEFT JOIN AuthAgg a
    ON t.EmployeeID = a.EmployeeID
    AND t.TimeBucket = a.TimeBucket
"""

df = pd.read_sql(sql, conn)
df.fillna(0, inplace=True)

print(f"📥 Rows loaded for demo: {len(df)}")

# =========================
# 4. FEATURE MATRIX (PHẢI KHỚP CSV TRAIN)
# =========================
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

X = df[features]

# =========================
# 5. SCALE & PREDICT
# =========================
X_scaled = scaler.transform(X)

df["anomaly_score"] = model.decision_function(X_scaled)
df["is_anomaly"] = model.predict(X_scaled)   # -1 = anomaly

# =========================
# 6. OUTPUT RESULT
# =========================
anomalies = df[df["is_anomaly"] == -1]

print(f"🚨 Total anomalies detected: {len(anomalies)}\n")

print(
    anomalies[
        [
            "EmployeeID",
            "TimeBucket",
            "anomaly_score",
            "query_count",
            "rows_returned_sum",
            "sensitive_ratio",
            "unique_ip_count",
            "failed_login_count",
        ]
    ]
    .sort_values("anomaly_score")
    .head(10)
)

print("\n✅ DEMO COMPLETED SUCCESSFULLY")
