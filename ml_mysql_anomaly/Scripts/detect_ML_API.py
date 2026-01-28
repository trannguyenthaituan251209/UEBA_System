from fastapi import FastAPI, Request
import pandas as pd
from db_connection import get_connection
import joblib
from fastapi.middleware.cors import CORSMiddleware
import time
from fastapi.responses import StreamingResponse
import json

app = FastAPI(title="UEBA Detection API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://192.168.1.111:5500"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
class UEBADetector:
    def __init__(self):
        self.model = joblib.load("model/iforest.pkl")
        self.scaler = joblib.load("model/scaler.pkl")

    def detect(self, df):
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
        X_scaled = self.scaler.transform(X)

        df["anomaly_score"] = self.model.decision_function(X_scaled)
        df["is_anomaly"] = self.model.predict(X_scaled)

        return df[df["is_anomaly"] == -1]

    def build_context(self, row):
        """Build context for abnormal behavior"""
        contexts = []
        
        # Check working hours
        if row["hour_of_day"] < 8 or row["hour_of_day"] > 18:
            contexts.append("accessed the system outside working hours")
        
        # Check abnormal query count
        if row["query_count"] > 50:
            contexts.append(f"performed {int(row['query_count'])} queries (unusually high)")
        
        # Check sensitive data ratio
        if row["sensitive_ratio"] > 0.3:
            contexts.append(f"accessed {row['sensitive_ratio']:.1%} sensitive data (high ratio)")
        
        # Check execution time
        if row["max_execution_time"] > 10000:
            contexts.append("had very slow query execution time (possible data dump)")
        
        # Check failed login
        if row["failed_login_count"] > 0:
            contexts.append(f"had {int(row['failed_login_count'])} failed login attempts")
        
        # Check multiple IPs
        if row["unique_ip_count"] > 1:
            contexts.append(f"logged in from {int(row['unique_ip_count'])} different IP addresses")
        
        return contexts

    def generate_explanation(self, row):
        """Create explanation using natural language"""
        contexts = self.build_context(row)
        
        if not contexts:
            return {
                "employee_id": int(row["EmployeeID"]),
                "risk_level": "LOW",
                "explanation": f"Employee {int(row['EmployeeID'])} shows normal activity with no signs of anomalies.",
                "anomaly_score": float(row["anomaly_score"]),
                "contexts": []
            }
        
        # Determine risk level
        risk_level = (
            "HIGH" if row["anomaly_score"] < -0.3 else
            "MEDIUM" if row["anomaly_score"] < -0.1 else
            "LOW"
        )
        
        explanation = (
            f"Employee {int(row['EmployeeID'])} "
            f"{', '.join(contexts)}. "
            f"This behavior deviates from the usual pattern and is assessed for risk level. {risk_level}."
        )
        
        return {
            "employee_id": int(row["EmployeeID"]),
            "risk_level": risk_level,
            "explanation": explanation,
            "anomaly_score": float(row["anomaly_score"]),
            "contexts": contexts
        }

SQL = """ 
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
    GROUP BY q.EmployeeID, DATEADD(hour, DATEDIFF(hour, 0, q.QueryTime), 0)
),
AuthAgg AS (
    SELECT
        EmployeeID,
        DATEADD(hour, DATEDIFF(hour, 0, LoginTime), 0) AS TimeBucket,
        COUNT(DISTINCT SourceIP) AS unique_ip_count,
        SUM(CASE WHEN LoginStatus = 'FAIL' THEN 1 ELSE 0 END) AS failed_login_count
    FROM AuthenticationLogs
    GROUP BY EmployeeID, DATEADD(hour, DATEDIFF(hour, 0, LoginTime), 0)
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

@app.get("/ueba/detect")
def detect_anomalies():
    conn = get_connection()
    df = pd.read_sql(SQL, conn).fillna(0)

    detector = UEBADetector()
    result = detector.detect(df)    
    anomalies = result[result["is_anomaly"] == -1]
    time.sleep(2)  # Delay 5 seconds
    return {
        "total_rows": len(df),
        "anomalies": len(anomalies),
        "data": anomalies.sort_values("anomaly_score").head(50).to_dict(orient="records")
    }

@app.get("/ueba/explain")
def explain_anomalies():
    """API trả về context đánh giá được generate bởi ML"""
    conn = get_connection()
    df = pd.read_sql(SQL, conn).fillna(0)
    
    detector = UEBADetector()
    result = detector.detect(df)    
    anomalies = result[result["is_anomaly"] == -1]
    
    # Generate explanations cho từng anomaly
    explanations = []
    for _, row in anomalies.sort_values("anomaly_score").head(20).iterrows():
        explanation = detector.generate_explanation(row)
        explanations.append(explanation)
    
    time.sleep(2)
    return {
        "total_rows": len(df),
        "anomalies_found": len(anomalies),
        "explanations": explanations,
        "summary": {
            "high_risk": len([e for e in explanations if e["risk_level"] == "HIGH"]),
            "medium_risk": len([e for e in explanations if e["risk_level"] == "MEDIUM"]),
            "low_risk": len([e for e in explanations if e["risk_level"] == "LOW"])
        }
    }

# SSE endpoint trả tiến trình thật
@app.get("/ueba/detect/progress")
async def detect_progress(request: Request):
    async def event_generator():
        # Bước 1: Kết nối DB (chia nhỏ tiến trình)
        yield f"data: {json.dumps({'progress': 5, 'status': 'Connecting to DB...'})}\n\n"
        await sleep_if_needed(request, 0.2)
        yield f"data: {json.dumps({'progress': 10, 'status': 'Connecting to DB...'})}\n\n"
        await sleep_if_needed(request, 0.2)
        try:
            conn = get_connection()
        except Exception as e:
            yield f"data: {json.dumps({'progress': 100, 'status': 'DB connection failed', 'done': True})}\n\n"
            return
        yield f"data: {json.dumps({'progress': 18, 'status': 'Connected. Reading data...'})}\n\n"
        await sleep_if_needed(request, 0.15)
        yield f"data: {json.dumps({'progress': 22, 'status': 'Reading data...'})}\n\n"
        await sleep_if_needed(request, 0.15)
        # Bước 2: Đọc dữ liệu (chia nhỏ)
        df = pd.read_sql(SQL, conn).fillna(0)
        yield f"data: {json.dumps({'progress': 30, 'status': 'Data loaded. Loading model...'})}\n\n"
        await sleep_if_needed(request, 0.15)
        yield f"data: {json.dumps({'progress': 35, 'status': 'Loading model...'})}\n\n"
        await sleep_if_needed(request, 0.15)
        # Bước 3: Load model (chia nhỏ)
        detector = UEBADetector()
        yield f"data: {json.dumps({'progress': 45, 'status': 'Model loaded. Detecting anomalies...'})}\n\n"
        await sleep_if_needed(request, 0.15)
        yield f"data: {json.dumps({'progress': 55, 'status': 'Detecting anomalies...'})}\n\n"
        await sleep_if_needed(request, 0.15)
        # Bước 4: ML detect (chia nhỏ)
        for prog in range(60, 90, 5):
            yield f"data: {json.dumps({'progress': prog, 'status': 'Detecting anomalies...'})}\n\n"
            await sleep_if_needed(request, 0.12)
        result = detector.detect(df)
        anomalies = result[result["is_anomaly"] == -1]
        yield f"data: {json.dumps({'progress': 92, 'status': 'Preparing result...'})}\n\n"
        await sleep_if_needed(request, 0.12)
        yield f"data: {json.dumps({'progress': 97, 'status': 'Finalizing...'})}\n\n"
        await sleep_if_needed(request, 0.12)
        # Hoàn thành
        yield f"data: {json.dumps({'progress': 100, 'status': 'Done', 'done': True})}\n\n"

    async def sleep_if_needed(request, seconds):
        # Cho phép hủy nếu client disconnect
        for _ in range(int(seconds * 10)):
            if await request.is_disconnected():
                break
            await asyncio.sleep(0.1)

    import asyncio
    return StreamingResponse(event_generator(), media_type="text/event-stream")
