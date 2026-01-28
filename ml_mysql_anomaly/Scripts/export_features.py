import pyodbc
import pandas as pd

conn = pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=localhost\\SQLEXPRESS;"
        "DATABASE=AuthenticationManager;"
        "Trusted_Connection=yes;"
        "Encrypt=no;"
        "TrustServerCertificate=yes;"
)

sql = """
-- ⚠️ CHỈ DATA BÌNH THƯỜNG (KHÔNG INSERT ATTACK TRƯỚC KHI EXPORT)
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

df.to_csv("./data/features.csv", index=False)
print(f"✅ Exported {len(df)} rows to ./data/features.csv")