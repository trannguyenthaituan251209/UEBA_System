import sys, os
sys.path.append(os.path.dirname(__file__))
from db_connection import get_connection

from fastapi import FastAPI, Request, Body
import pandas as pd
import joblib
from fastapi.middleware.cors import CORSMiddleware
import time
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
import json
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from fpdf import FPDF
from typing import Any, Dict

app = FastAPI(title="UEBA Detection API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "https://hatvaqua.online/",
    "https://ueba-system.onrender.com",
    "https://ueba-system.onrender.com/",
    "https://ueba-system.onrender.com:10000",
    "https://ueba-system.onrender.com:10000/",
    "https://ueba-system.onrender.com:443",
    "https://ueba-system.onrender.com:443/",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://192.168.1.111:5500"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# UEBADetector chỉ nạp model/scaler từ file .pkl đã huấn luyện sẵn
class UEBADetector:
    def __init__(self):
        self.model = joblib.load("model/iforest.pkl")
        self.scaler = joblib.load("model/scaler.pkl")

    def detect(self, df):

        from fastapi import Body
        from typing import Dict, Any

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
    e.FullName,
    e.Role,
    e.avatar_url,
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
LEFT JOIN Employees e
    ON t.EmployeeID = e.EmployeeID
"""

@app.get("/ueba/detect")
def detect_anomalies():
    time.sleep(3)
    conn = get_connection()
    df = pd.read_csv("data/supervised_querylogs.csv").fillna(0)


    df["hour_of_day"] = pd.to_datetime(df["QueryTime"]).dt.hour
    df["is_after_hours"] = ((df["hour_of_day"] < 7) | (df["hour_of_day"] > 17)).astype(int)
    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder()
    df["query_type"] = le.fit_transform(df["QueryType"].astype(str))
    features = [
        "hour_of_day", "is_after_hours", "RowsExamined", "RowsReturned", "ExecutionTime", "QueryLength", "IsSensitive", "query_type"
    ]
    for col in features:
        if col not in df.columns:
            df[col] = 0
    X = df[features].fillna(0)

    # Load mô hình supervised
    import joblib
    clf = joblib.load("model/rf_supervised.pkl")
    y_pred = clf.predict(X)
    df["anomaly_score"] = clf.predict_proba(X)[:, 1] if hasattr(clf, "predict_proba") else y_pred
    df["is_anomaly"] = y_pred

    # Trả về top N anomaly (label=1)
    anomalies = df[df["is_anomaly"] == 1].sort_values("anomaly_score", ascending=False)
    top_anomalies = anomalies.head(50)

    # Sinh context tổng hợp
    total_rows = int(len(df))
    anomaly_count = int(len(anomalies))
    anomaly_rate = (anomaly_count / total_rows) if total_rows else 0
    # Thêm thông tin user bất thường nhất vào context
    if anomaly_count == 0:
        context = "System is safe. No significant anomalies detected."
    else:
        # Lấy top 1-2 user bất thường nhất
        top_users = []
        for i, row in enumerate(anomalies.head(2).itertuples()):
            emp = getattr(row, "EmployeeID", None)
            score = getattr(row, "anomaly_score", None)
            if emp is not None and score is not None:
                top_users.append(f"{emp} (score: {score:.2f})")
        top_users_str = ", ".join(top_users)
        if anomaly_rate < 0.05:
            context = f"System is safe. {anomaly_count} minor anomalies detected. Most abnormal user: {top_users_str}."
        elif anomaly_rate < 0.15:
            context = f"Warning: {anomaly_count} anomalies detected. Most abnormal user: {top_users_str}. Please review recent activities."
        else:
            context = f"Danger: High anomaly rate ({anomaly_rate:.1%})! Top outlier(s): {top_users_str}. Immediate investigation recommended."

    # Tìm đúng tên cột QueryLogID (phân biệt hoa thường)
    querylogid_col = None
    for col in df.columns:
        if col.lower() == "querylogid":
            querylogid_col = col
            break

    return {
        "total_rows": total_rows,
        "anomalies": anomaly_count,
        "anomaly_rate": anomaly_rate,
        "context": context,
        "data": [
            {
                "EmployeeID": int(row["EmployeeID"]) if "EmployeeID" in row else None,
                "QueryTime": str(row["QueryTime"]) if "QueryTime" in row else None,
                "QueryLogID": row[querylogid_col] if querylogid_col and querylogid_col in row else None,
                "anomaly_score": float(row["anomaly_score"]),
                "is_anomaly": int(row["is_anomaly"]),
                "RowsExamined": int(row["RowsExamined"]) if "RowsExamined" in row else None,
                "RowsReturned": int(row["RowsReturned"]) if "RowsReturned" in row else None,
                "ExecutionTime": float(row["ExecutionTime"]) if "ExecutionTime" in row else None,
                "QueryLength": int(row["QueryLength"]) if "QueryLength" in row else None,
                "IsSensitive": int(row["IsSensitive"]) if "IsSensitive" in row else None,
                "query_type": int(row["query_type"]) if "query_type" in row else None
            }
            for _, row in top_anomalies.iterrows()
        ]
    }

@app.get("/ueba/explain")
def explain_anomalies():
    """API trả về context đánh giá được generate bởi ML, luôn trả về top 10 anomaly_score thấp nhất"""
    conn = get_connection()
    df = pd.read_sql(SQL, conn).fillna(0)

    detector = UEBADetector()
    # Tính anomaly_score cho toàn bộ dữ liệu (không lọc theo predict)

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
    for col in features:
        if col not in df.columns:
            df[col] = 0
    X = df[features].fillna(0).copy()
    import numpy as np
    for col in ["query_count", "rows_returned_sum", "avg_execution_time", "max_execution_time", "sensitive_query_count", "unique_ip_count", "failed_login_count"]:
        if col in X.columns:
            X[col] = np.log1p(X[col])
    X_scaled = detector.scaler.transform(X)
    df["anomaly_score"] = detector.model.decision_function(X_scaled)


    # Ghi log toàn bộ anomaly_score và EmployeeID để kiểm tra
    print("==== DEBUG: anomaly_score by EmployeeID ====")
    for idx, row in df.iterrows():
        print(f"EmployeeID: {row['EmployeeID']}, anomaly_score: {row['anomaly_score']}")
    print("==== END DEBUG ====")

    # Lấy top 10 anomaly_score thấp nhất
    top_anomalies = df.sort_values("anomaly_score").head(10)

    explanations = []
    for _, row in top_anomalies.iterrows():
        row = row if isinstance(row, pd.Series) else pd.Series(row)
        full_name = str(row.get("FullName", ""))
        role = str(row.get("Role", ""))
        avatar_url = str(row.get("avatar_url", ""))
        anomaly_score = float(row["anomaly_score"])
        risk_level = (
            "HIGH" if anomaly_score < -0.19 else
            "MEDIUM" if anomaly_score < -0.1 else
            "LOW"
        )
        explanation_obj = detector.generate_explanation(row)
        explanation = explanation_obj["explanation"] if isinstance(explanation_obj, dict) else str(explanation_obj)
        explanations.append({
            "employee_id": int(row["EmployeeID"]),
            "full_name": full_name,
            "role": role,
            "avatar_url": avatar_url,
            "anomaly_score": anomaly_score,
            "risk_level": risk_level,
            "explanation": explanation
        })

    return {
        "explanations": explanations,
        "anomalies_found": len(explanations),
        "summary": {
            "high_risk": sum(1 for e in explanations if e["risk_level"] == "HIGH"),
            "medium_risk": sum(1 for e in explanations if e["risk_level"] == "MEDIUM"),
            "low_risk": sum(1 for e in explanations if e["risk_level"] == "LOW"),
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

@app.get("/ueba/evaluate")
def evaluate_ml():
    """Endpoint trả về self-evaluation của mô hình ML: accuracy, precision, recall, f1-score"""
    conn = get_connection()
    # Lấy features
    df = pd.read_sql(SQL, conn).fillna(0)
    # Lấy nhãn từ bảng AnomalyLabels (giả sử EmployeeID và TimeBucket mapping với QueryTime)
    label_sql = """
    SELECT EmployeesID, is_abnomaly AS label
    FROM AbnomalyLabels
    WHERE is_abnomaly IS NOT NULL
    """
    labels = pd.read_sql(label_sql, conn)
    # Gộp nhãn vào features chỉ theo EmployeeID
    df = df.merge(labels, left_on=["EmployeeID"], right_on=["EmployeesID"], how="left")
    df["label"] = df["label"].fillna(0).astype(int)

    # Dự đoán của mô hình
    detector = UEBADetector()
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
    X_scaled = detector.scaler.transform(X)
    y_pred = detector.model.predict(X_scaled)
    # Isolation Forest: -1 là bất thường, 1 là bình thường
    y_pred = (y_pred == -1).astype(int)
    y_true = df["label"].values

    accuracy = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "total_samples": int(len(y_true)),
        "anomaly_labeled": int(sum(y_true)),
        "anomaly_predicted": int(sum(y_pred))
    }
@app.get("/ueba/selfscore")
def selfscore():
    """Endpoint trả về các chỉ số nội tại của Isolation Forest không dùng nhãn."""
    conn = get_connection()
    df = pd.read_sql(SQL, conn).fillna(0)
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
    for col in features:
        if col not in df.columns:
            df[col] = 0
    X = df[features].fillna(0).copy()
    import numpy as np
    for col in ["query_count", "rows_returned_sum", "avg_execution_time", "max_execution_time", "sensitive_query_count", "unique_ip_count", "failed_login_count"]:
        if col in X.columns:
            X[col] = np.log1p(X[col])
    from joblib import load
    model = load("model/iforest.pkl")
    scaler = load("model/scaler.pkl")
    X_scaled = scaler.transform(X)
    anomaly_score = model.decision_function(X_scaled)
    is_anomaly = model.predict(X_scaled)
    anomaly_rate = float((is_anomaly == -1).sum()) / len(is_anomaly)
    score_stats = {
        "min": float(np.min(anomaly_score)),
        "max": float(np.max(anomaly_score)),
        "mean": float(np.mean(anomaly_score)),
        "std": float(np.std(anomaly_score)),
        "25%": float(np.percentile(anomaly_score, 25)),
        "50%": float(np.percentile(anomaly_score, 50)),
        "75%": float(np.percentile(anomaly_score, 75))
    }
    # Top 10 outlier
    top_idx = np.argsort(anomaly_score)[:10]
    top_outlier = df.iloc[top_idx][["EmployeeID", "hour_of_day", "query_count"]].copy()
    top_outlier["anomaly_score"] = anomaly_score[top_idx]
    return {
        "anomaly_rate": anomaly_rate,
        "score_stats": score_stats,
        "top_outlier": top_outlier.to_dict(orient="records")
    }
#Test mô hình giám sát
@app.get("/supervised/predict")
def supervised_predict():
    time.sleep(3)
    """API kiểm chứng mô hình supervised: dự đoán bất thường/bình thường trên dữ liệu hiện tại."""
    import joblib
    from sklearn.preprocessing import LabelEncoder
    # Đọc dữ liệu QueryLogs đã gán nhãn (hoặc lấy từ SQL nếu muốn)
    df = pd.read_csv("data/supervised_querylogs.csv")
    # Trích xuất đặc trưng số giống lúc train
    df["hour_of_day"] = pd.to_datetime(df["QueryTime"]).dt.hour
    df["is_after_hours"] = ((df["hour_of_day"] < 7) | (df["hour_of_day"] > 17)).astype(int)
    le = LabelEncoder()
    df["query_type"] = le.fit_transform(df["QueryType"].astype(str))
    features = [
        "hour_of_day", "is_after_hours", "RowsExamined", "RowsReturned", "ExecutionTime", "QueryLength", "IsSensitive", "query_type"
    ]
    X = df[features].fillna(0)
    # Load model
    clf = joblib.load("model/rf_supervised.pkl")
    y_pred = clf.predict(X)
    # Ép kiểu predicted_label về int Python
    df["predicted_label"] = [int(x) for x in y_pred]
    # Trả về kết quả dự đoán và so sánh với nhãn thật nếu có
    if "Labels" in df.columns:
        correct = int((df["Labels"].astype(int) == y_pred).sum())
        total = int(len(df))
        accuracy = float(correct / total) if total > 0 else None
    else:
        accuracy = None
    # Ép kiểu predicted_counts về int
    predicted_counts = {int(k): int(v) for k, v in pd.Series(y_pred).value_counts().items()}
    # Ép kiểu EmployeeID và predicted_label về int trong results
    # Nếu có nhãn gốc, trả về cả Labels để đối chiếu
    if "Labels" in df.columns:
        results = [
            {
                "EmployeeID": int(row["EmployeeID"]),
                "QueryTime": str(row["QueryTime"]),
                "predicted_label": int(row["predicted_label"]),
                "label": int(row["Labels"]) if not pd.isnull(row["Labels"]) else None
            }
            for _, row in df[["EmployeeID", "QueryTime", "predicted_label", "Labels"]].iterrows()
        ]
    else:
        results = [
            {
                "EmployeeID": int(row["EmployeeID"]),
                "QueryTime": str(row["QueryTime"]),
                "predicted_label": int(row["predicted_label"])
            }
            for _, row in df[["EmployeeID", "QueryTime", "predicted_label"]].iterrows()
        ]
    return {
        "accuracy": accuracy,
        "total_samples": int(len(df)),
        "predicted_counts": predicted_counts,
        "results": results
    }

@app.get("/ueba/scorechart")
def get_anomaly_scores():
    time.sleep(3)
    """API trả về danh sách anomaly_score cho toàn bộ dữ liệu để vẽ chart"""
    import joblib
    import numpy as np
    from sklearn.preprocessing import LabelEncoder
    df = pd.read_csv("data/supervised_querylogs.csv")
    df["hour_of_day"] = pd.to_datetime(df["QueryTime"]).dt.hour
    df["is_after_hours"] = ((df["hour_of_day"] < 7) | (df["hour_of_day"] > 17)).astype(int)
    le = LabelEncoder()
    df["query_type"] = le.fit_transform(df["QueryType"].astype(str))
    features = [
        "hour_of_day", "is_after_hours", "RowsExamined", "RowsReturned", "ExecutionTime", "QueryLength", "IsSensitive", "query_type"
    ]
    X = df[features].fillna(0)
    clf = joblib.load("model/rf_supervised.pkl")
    # Lấy xác suất anomaly nếu có, nếu không thì lấy nhãn dự đoán
    if hasattr(clf, "predict_proba"):
        scores = clf.predict_proba(X)[:, 1]
    else:
        scores = clf.predict(X)
    # Đánh dấu outlier: score > 0.5 là bất thường (tuỳ mô hình, có thể chỉnh)
    threshold = 0.5
    is_anomaly = (scores > threshold).astype(int) if hasattr(clf, "predict_proba") else (scores == 1).astype(int)
    # Risk level: score càng gần 1 càng nguy hiểm
    def risk_level_fn(score):
        if score > 0.8:
            return "HIGH"
        elif score > 0.5:
            return "MEDIUM"
        else:
            return "LOW"
    # Context: score > 0.8 là nghi ngờ cao, >0.5 là tiềm ẩn, còn lại là bình thường
    def context_fn(score):
        if score > 0.8:
            return "Highly suspicious activity"
        elif score > 0.5:
            return "Potential anomaly"
        else:
            return "Normal activity"
    result = []
    for idx, row in df.iterrows():
        score = float(scores[idx])
        result.append({
            "employee_id": int(row["EmployeeID"]) if "EmployeeID" in row else None,
            "query_time": str(row["QueryTime"]) if "QueryTime" in row else None,
            "QueryLogID": row["QueryLogID"] if "QueryLogID" in row else None,
            "anomaly_score": score,
            "is_anomaly": int(is_anomaly[idx]),
            "risk_level": risk_level_fn(score),
            "context": context_fn(score)
        })
    return {
        "threshold": threshold,
        "data": result
    }
# import sys, os
# sys.path.append(os.path.dirname(__file__))
# from train_supervised import train_supervised_model
# # --- API train supervised model trực tiếp từ web ---
# @app.post("/supervised/train")
# def train_supervised_api():
#     """API để train lại mô hình supervised, trả về kết quả cross-validation."""
#     try:
#         result = train_supervised_model()
#         return {
#             "success": True,
#             "mean_scores": result["mean_scores"],
#             "fold_scores": result["fold_scores"]
#         }
#     except Exception as e:
#         return {"success": False, "error": str(e)}

from fastapi import Request
import requests

@app.post("/ueba/export-pdf")
async def export_pdf_from_data(request: Request, data: Dict[str, Any] = Body(...)):
    """API để xuất báo cáo PDF từ dữ liệu anomaly đã detect (frontend gửi lên), kèm IP và vị trí client."""
    try:
        # Lấy IP client
        client_ip = request.client.host if request.client else None
        # Ưu tiên lấy từ header X-Forwarded-For nếu có (nếu chạy sau proxy)
        xff = request.headers.get("x-forwarded-for")
        if xff:
            client_ip = xff.split(",")[0].strip()
        # Log IP ra server để debug
        print(f"[EXPORT PDF] Client IP: {client_ip}")
        # Lấy vị trí địa lý từ ip-api.com
        geo_info = {}
        is_local = client_ip in ("127.0.0.1", "::1", None)
        if not is_local:
            try:
                resp = requests.get(f"http://ip-api.com/json/{client_ip}?fields=status,country,regionName,city,query,lat,lon,isp")
                if resp.ok:
                    geo_info = resp.json()
            except Exception as ex:
                print(f"[EXPORT PDF] Geo lookup error: {ex}")
                geo_info = {}
        # anomalies: lấy từ data['data'] nếu có, nếu không thì từ data['anomalies'] nếu là list
        anomalies = data.get("data")
        if anomalies is None:
            anomalies = data.get("anomalies") if isinstance(data.get("anomalies"), list) else []
        context = data.get("context", "")
        total_rows = data.get("total_rows", None)
        # anomaly_count: lấy số lượng anomaly, không phải list
        anomaly_count = data.get("anomalies") if isinstance(data.get("anomalies"), int) else len(anomalies)
        anomaly_rate = data.get("anomaly_rate", None)

        from datetime import datetime
        import os
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        # Add custom font (assume font file is in assets/fonts/YourFont.ttf)
        font_path = os.path.join(os.path.dirname(__file__), '../../assets/fonts/SourceCodePro-VariableFont_wght.ttf')
        font_name = "CustomFont"
        if os.path.exists(font_path):
            pdf.add_font(font_name, '', font_path, uni=True)
            pdf.set_font(font_name, size=18)
        else:
            pdf.set_font("Arial", style="B", size=18)
        # Logo (bên trái)
        logo_path = os.path.join(os.path.dirname(__file__), '../../assets/UEBA SYSTEM.png')
        if os.path.exists(logo_path):
            pdf.image(logo_path, x=10, y=10, w=22, h=22)
        # Tiêu đề chính
        pdf.set_xy(35, 10)
        pdf.cell(0, 12, "UEBA-MLVer1 (BETA) REPORT", ln=2, align="L")
        # Tiêu đề phụ
        if os.path.exists(font_path):
            pdf.set_font(font_name, size=11)
        else:
            pdf.set_font("Arial", size=11)
        pdf.set_text_color(120,120,120)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report_id = f"ReportID: {datetime.now().strftime('%Y%m%d%H%M%S')}"
        pdf.cell(0, 7, f"Datetime: {now}   {report_id}", ln=2, align="L")

        # Đường line ngang
        pdf.set_draw_color(180,180,180)
        pdf.set_line_width(0.7)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(6)
        # Thông tin tổng quan
        if os.path.exists(font_path):
            pdf.set_font(font_name, size=8)
        else:
            pdf.set_font("Arial", size=8)
        # Thông tin IP và vị trí
        ip_str = f"Client IP: {client_ip or '--'}"
        if is_local:
            loc_str = "Location: Localhost (no geolocation)"
        elif geo_info.get("status") == "success":
            loc_str = f"Location: {geo_info.get('city','')}, {geo_info.get('regionName','')}, {geo_info.get('country','')} (ISP: {geo_info.get('isp','')})"
        else:
            loc_str = f"Location: Not found for IP: {client_ip}"
        pdf.cell(0, 7, ip_str, ln=2, align="L")
        pdf.cell(0, 7, loc_str, ln=2, align="L")
        pdf.set_text_color(0,0,0)
        pdf.ln(2)
        if total_rows is not None:
            pdf.cell(0, 8, f"Total rows: {total_rows}", ln=1, align="L")
        if anomaly_count is not None:
            pdf.cell(0, 8, f"Anomalies: {anomaly_count}", ln=1, align="L")
        if anomaly_rate is not None:
            pdf.cell(0, 8, f"Anomaly rate: {anomaly_rate:.2%}", ln=1, align="L")
        if context:
            pdf.multi_cell(0, 8, f"Context by ML: {context}", align="L")
        pdf.ln(2)
        # Table header
        if os.path.exists(font_path):
            pdf.set_font(font_name, size=8)
        else:
            pdf.set_font("Arial", size=7)
        col_widths = [15, 48, 18, 13, 18, 18, 18, 15, 18]
        headers = ["EmpID", "QueryTime", "Score", "Anom", "RowsEx", "RowsRet", "ExecT", "QType", "LogID"]
        for i, h in enumerate(headers):
            pdf.cell(col_widths[i], 8, h, 1, 0, 'C')
        pdf.ln()
        if os.path.exists(font_path):
            pdf.set_font(font_name, size=9)
        else:
            pdf.set_font("Arial", size=9)
        for row in anomalies[:30]:
            vals = [
                str(row.get("EmployeeID", "")),
                str(row.get("QueryTime", ""))[:19],
                f"{row.get('anomaly_score', 0):.2f}",
                str(row.get("is_anomaly", "")),
                str(row.get("RowsExamined", "")),
                str(row.get("RowsReturned", "")),
                f"{row.get('ExecutionTime', ''):.2f}" if row.get('ExecutionTime') is not None else "",
                str(row.get("query_type", "")),
                str(row.get("QueryLogID", "")),
            ]
            y_before = pdf.get_y()
            x = pdf.get_x()
            for i, v in enumerate(vals):
                v = str(v)
                # Chỉ wrap cho LogID nếu quá dài, còn lại giữ 1 dòng
                if i == 8 and len(v) > 16:
                    pdf.multi_cell(col_widths[i], 8, v, 1, 'C', False)
                    x += col_widths[i]
                    pdf.set_xy(x, y_before)
                else:
                    pdf.cell(col_widths[i], 8, v, 1, 0, 'C')
                    x += col_widths[i]
            pdf.ln(8)
        pdf.ln(2)
        # Notice cuối
        if os.path.exists(font_path):
            pdf.set_font(font_name, size=8)
        else:
            pdf.set_font("Arial", style="B", size=8)
        pdf.set_text_color(220, 0, 0)
        pdf.cell(0, 8, "*NOTE: Anomaly scores are calculated by Machine Learning and may not be 100% accurate. Use as reference only.", ln=1, align="L")
        pdf.set_text_color(0,0,0)
        pdf.ln(2)
        # Mô tả hệ thống ML
        if os.path.exists(font_path):
            pdf.set_font(font_name, size=14)
        else:
            pdf.set_font("Arial", style="B", size=14)
        pdf.cell(0, 8, "About UEBA-MLVer1 (BETA)", ln=1, align="L")
        if os.path.exists(font_path):
            pdf.set_font(font_name, size=10)
        else:
            pdf.set_font("Arial", size=10)
        ml_desc = (
            "The UEBA (User and Entity Behavior Analytics) ML System is a security analytics platform designed to detect, analyze, and respond to anomalous activities within enterprise databases and IT environments. "
            "It leverages advanced machine learning algorithms to monitor user/entity behaviors, correlate events, and identify potential threats in real time. "
            "The system integrates both unsupervised and supervised models, including Isolation Forests and Random Forests, to provide robust anomaly detection. "
            "Key features: real-time anomaly detection, contextual risk assessment, interactive dashboard, API endpoints, scalable backend, and export/reporting tools. "
            "The dashboard visualizes key metrics, anomaly scores, and top suspicious events, empowering security teams to prioritize investigations. "
            "For more information, contact your system administrator or security team."
        )
        pdf.multi_cell(0, 7, ml_desc, align="L")
        pdf.ln(2)
        if os.path.exists(font_path):
            pdf.set_font(font_name, size=12)
        else:
            pdf.set_font("Arial", style="B", size=12)
        pdf.cell(0, 8, "--THE END--", ln=1, align="C")
        from io import BytesIO
        pdf_bytes = pdf.output(dest='S').encode('latin1')
        pdf_buffer = BytesIO(pdf_bytes)
        pdf_buffer.seek(0)
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=ueba_anomaly_report.pdf"}
        )
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(content={"success": False, "error": str(e)})