import pyodbc
import pandas as pd
import os

conn = pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=localhost\\SQLEXPRESS;"
        "DATABASE=AuthenticationManager;"
        "Trusted_Connection=yes;"
        "Encrypt=no;"
        "TrustServerCertificate=yes;"
)


# New, more detailed SQL query for feature extraction
sql = """
WITH BaseLogs AS (
    SELECT
        q.QueryLogID,
        q.EmployeeID,
        q.QueryTime,
        CAST(q.QueryTime AS DATE) AS QueryDate,
        q.QueryType,
        q.Affected_table,
        q.RowsExamined,
        q.RowsReturned,
        q.ExecutionTime,
        q.QueryLength,
        q.IsSensitive
    FROM QueryLogs q
),

-- Tổng hợp query theo ngày
DailyAgg AS (
    SELECT
        EmployeeID,
        QueryDate,
        COUNT(*) AS QueriesPerDay,
        SUM(RowsExamined) AS RowsExaminedPerDay
    FROM BaseLogs
    GROUP BY EmployeeID, QueryDate
),

-- Đếm số bảng DISTINCT (SQL Server–safe)
DistinctTables AS (
    SELECT DISTINCT
        EmployeeID,
        QueryDate,
        Affected_table
    FROM BaseLogs
),
TableSpread AS (
    SELECT
        EmployeeID,
        QueryDate,
        COUNT(*) AS DistinctTablesAccessedPerDay
    FROM DistinctTables
    GROUP BY EmployeeID, QueryDate
),

-- Session info
SessionInfo AS (
    SELECT
        a.EmployeeID,
        a.LoginTime,
        a.LogoutTime,
        a.SourceIP,
        a.DeviceInfo,
        a.LoginStatus
    FROM AuthenticationLogs a
)

SELECT
    -- identity
    bl.EmployeeID,
    e.Role,
    e.Department,

    -- time
    DATEPART(HOUR, bl.QueryTime) AS hour_of_day,
    CASE 
        WHEN DATEPART(HOUR, bl.QueryTime) BETWEEN 8 AND 18 THEN 0
        ELSE 1
    END AS IsAfterHours,

    -- query behavior
    bl.QueryType,
    bl.RowsExamined,
    bl.RowsReturned,
    bl.ExecutionTime,
    bl.QueryLength,
    bl.IsSensitive,

    -- daily aggregates
    da.QueriesPerDay,
    da.RowsExaminedPerDay,
    ts.DistinctTablesAccessedPerDay,

    -- session features
    DATEDIFF(
        MINUTE,
        si.LoginTime,
        ISNULL(si.LogoutTime, bl.QueryTime)
    ) AS SessionDurationMinutes

FROM BaseLogs bl
JOIN Employees e
    ON bl.EmployeeID = e.EmployeeID

LEFT JOIN DailyAgg da
    ON da.EmployeeID = bl.EmployeeID
   AND da.QueryDate = bl.QueryDate

LEFT JOIN TableSpread ts
    ON ts.EmployeeID = bl.EmployeeID
   AND ts.QueryDate = bl.QueryDate

LEFT JOIN SessionInfo si
    ON si.EmployeeID = bl.EmployeeID
   AND si.LoginTime <= bl.QueryTime
   AND (si.LogoutTime IS NULL OR si.LogoutTime >= bl.QueryTime)

ORDER BY bl.QueryTime;
"""

df = pd.read_sql(sql, conn)
# Fill numeric columns with 0, string/object columns with ''
for col in df.columns:
    if pd.api.types.is_numeric_dtype(df[col]):
        df[col] = df[col].fillna(0)
    else:
        df[col] = df[col].fillna("")

# Đảm bảo tạo đúng thư mục output

OUTPUT_DIR = "data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

csv_path = os.path.join(OUTPUT_DIR, "features_optimized.csv")

df.to_csv(csv_path, index=False)

print("Export feature thành công:")
print(csv_path)
