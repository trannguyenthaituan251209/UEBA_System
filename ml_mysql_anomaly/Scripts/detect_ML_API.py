import sys, os
sys.path.append(os.path.dirname(__file__))
from db_connection import get_connection

# Đường dẫn tuyệt đối tới thư mục gốc project (ml_mysql_anomaly)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Thư mục gốc project (demo/)
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))
DATA_PATH = os.path.join(BASE_DIR, "data", "supervised_querylogs.csv")
MODEL_DIR = os.path.join(BASE_DIR, "model")
IFOREST_PATH = os.path.join(MODEL_DIR, "iforest.pkl")
SCALER_PATH = os.path.join(MODEL_DIR, "scaler.pkl")
RF_SUPERVISED_PATH = os.path.join(MODEL_DIR, "rf_supervised.pkl")

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

# Chuyển sang google.genai (Gemini API mới)
import google.genai as genai

# Đặt API key Gemini (thay bằng key của bạn)
GENAI_API_KEY = "AIzaSyCsKw4NQVL-SSj3UKhW_moJyA5KmQ49-f8"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def generate_context(anomaly_count, anomaly_rate, top_users, sample_data):
    prompt = (
        f"UEBA System Alert: {anomaly_count} anomalies detected (rate: {anomaly_rate:.2%}).\n"
        f"Top suspicious users ranked by anomaly score: {top_users}.\n\n"
        f"Please provide:\n"
        f"1. Overall risk assessment based on the anomaly rate and count.\n"
        f"2. For EACH user listed above, provide a brief individual risk analysis (what their score means, potential threat level).\n"
        f"3. Recommended actions for the administrator, prioritized by user risk level.\n"
        f"4. General security recommendations.\n"
        f"Keep the response concise and actionable."
    )
    print(f"[LLM] Prompt: {prompt}")
    try:
        client = genai.Client(api_key=GENAI_API_KEY)
        # Gemini expects 'history' not 'messages', and history is a list of dicts with 'role' and 'parts'
        history = [{"role": "user", "parts": [{"text": prompt}]}]
        chat = client.chats.create(model="models/gemini-2.5-flash", history=history)
        # The chat object may have a 'history' or 'last' property, but to get the model's response, send a message
        response = chat.send_message(prompt)
        # Extract content from response
        part = response.candidates[0].content.parts[0] if hasattr(response, 'candidates') and response.candidates and hasattr(response.candidates[0], 'content') and response.candidates[0].content.parts else None
        import re
        raw_context = part.text.strip() if part and hasattr(part, 'text') and isinstance(part.text, str) else str(response)
        # Return raw markdown text — let the frontend handle formatting
        print(f"[LLM] Output: {raw_context}")
        return raw_context
    except Exception as e:
        print(f"[LLM] Error: {e}")
        return None
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

from typing import Optional

@app.get("/ueba/detect")
def detect_anomalies(skip_context: Optional[str] = None):
    conn = get_connection()
    # Đọc trực tiếp từ database QueryLogs
    df = pd.read_sql("SELECT * FROM QueryLogs", conn).fillna(0)

    # Feature engineering như cũ
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
    clf = joblib.load(RF_SUPERVISED_PATH)
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

    # Nếu skip_context, không gọi AI
    context = None
    if not skip_context:
        # Lấy top 5 user bất thường nhất
        top_users = []
        for i, row in enumerate(anomalies.head(5).itertuples()):
            emp = getattr(row, "EmployeeID", None)
            score = getattr(row, "anomaly_score", None)
            if emp is not None and score is not None:
                top_users.append(f"#{i+1} User {emp} (score: {score:.2f})")
        top_users_str = ", ".join(top_users)
        sample_data = anomalies.head(5).to_dict(orient='records') if anomaly_count > 0 else []
        context = generate_context(anomaly_count, anomaly_rate, top_users_str, sample_data)
        print(f"[LLM] Final context: {context}")
        if context is None:
            if anomaly_count == 0:
                context = "System is safe. No significant anomalies detected."
            elif anomaly_rate < 0.05:
                context = f"System is safe. {anomaly_count} minor anomalies detected."
            elif anomaly_rate < 0.15:
                context = f"Warning: {anomaly_count} anomalies detected. Please review recent activities."
            else:
                context = f"Danger: High anomaly rate ({anomaly_rate:.1%})! Immediate investigation recommended."
        print(f"[LLM] Used context: {context}")

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

@app.post("/ueba/generate-context")
def generate_context_api(body: Dict[str, Any] = Body(...)):
    """Endpoint riêng để sinh AI context, gọi sau khi đã có dữ liệu detect."""
    anomaly_count = body.get("anomaly_count", 0)
    anomaly_rate = body.get("anomaly_rate", 0)
    top_users = body.get("top_users", "")
    sample_data = body.get("sample_data", [])
    context = generate_context(anomaly_count, anomaly_rate, top_users, sample_data)
    if context is None:
        if anomaly_count == 0:
            context = "System is safe. No significant anomalies detected."
        elif anomaly_rate < 0.05:
            context = f"System is safe. {anomaly_count} minor anomalies detected."
        elif anomaly_rate < 0.15:
            context = f"Warning: {anomaly_count} anomalies detected. Please review recent activities."
        else:
            context = f"Danger: High anomaly rate ({anomaly_rate:.1%})! Immediate investigation recommended."
    return {"context": context}



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

@app.get("/supervised/predict")
def supervised_predict():
    """API kiểm chứng mô hình supervised: dự đoán bất thường/bình thường trên dữ liệu hiện tại."""
    import joblib
    from sklearn.preprocessing import LabelEncoder
    # Đọc dữ liệu QueryLogs đã gán nhãn (hoặc lấy từ SQL nếu muốn)
    df = pd.read_csv(DATA_PATH)
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
    clf = joblib.load(RF_SUPERVISED_PATH)
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
    """API trả về danh sách anomaly_score cho toàn bộ dữ liệu để vẽ chart"""
    import joblib
    import numpy as np
    from sklearn.preprocessing import LabelEncoder
    conn = get_connection()
    # Đọc trực tiếp từ database QueryLogs
    df = pd.read_sql("SELECT * FROM QueryLogs", conn).fillna(0)
    df["hour_of_day"] = pd.to_datetime(df["QueryTime"]).dt.hour
    df["is_after_hours"] = ((df["hour_of_day"] < 7) | (df["hour_of_day"] > 17)).astype(int)
    le = LabelEncoder()
    df["query_type"] = le.fit_transform(df["QueryType"].astype(str))
    features = [
        "hour_of_day", "is_after_hours", "RowsExamined", "RowsReturned", "ExecutionTime", "QueryLength", "IsSensitive", "query_type"
    ]
    X = df[features].fillna(0)
    clf = joblib.load(RF_SUPERVISED_PATH)
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
    print("[EXPORT PDF] Input data:", data)
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
            except Exception as e:
                print(f"[LLM] Error: {e}")
                return None

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
        # Sửa đường dẫn font: lấy từ thư mục gốc project (không phụ thuộc BASE_DIR local)
        font_path = os.path.join(PROJECT_ROOT, 'assets', 'fonts', 'SourceCodePro-VariableFont_wght.ttf')
        print("[EXPORT PDF] Font path:", font_path, "Exists:", os.path.exists(font_path))
        font_name = "CustomFont"
        if os.path.exists(font_path):
            try:
                pdf.add_font(font_name, '', font_path, uni=True)
                pdf.set_font(font_name, size=18)
            except Exception as font_err:
                print(f"[EXPORT PDF] Font load error: {font_err}. Fallback to Arial.")
                pdf.set_font("Arial", style="B", size=18)
        else:
            print(f"[EXPORT PDF] Font file not found: {font_path}. Fallback to Arial.")
            pdf.set_font("Arial", style="B", size=18)
        # Logo (bên trái)
        logo_path = os.path.join(PROJECT_ROOT, 'assets', 'UEBA SYSTEM.png')
        if os.path.exists(logo_path):
            pdf.image(logo_path, x=10, y=10, w=22, h=22)
        # Tiêu đề chính
        pdf.set_xy(35, 10)
        pdf.cell(0, 12, "UEBA-MLVer1 (BETA) REPORT", ln=2, align="L")
        # Tiêu đề phụ
        if os.path.exists(font_path):
            try:
                pdf.set_font(font_name, size=11)
            except Exception:
                pdf.set_font("Arial", size=11)
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
            try:
                pdf.set_font(font_name, size=8)
            except Exception:
                pdf.set_font("Arial", size=8)
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
        pdf.ln(4)

        # --- AI-Context Section ---
        if context:
            # Section header
            if os.path.exists(font_path):
                try:
                    pdf.set_font(font_name, size=14)
                except Exception:
                    pdf.set_font("Arial", style="B", size=14)
            else:
                pdf.set_font("Arial", style="B", size=14)
            pdf.set_text_color(30, 80, 160)
            pdf.cell(0, 10, "AI-Context Analysis (Gemini)", ln=1, align="L")
            # Divider line
            pdf.set_draw_color(30, 80, 160)
            pdf.set_line_width(0.5)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(3)
            # Context body
            if os.path.exists(font_path):
                try:
                    pdf.set_font(font_name, size=9)
                except Exception:
                    pdf.set_font("Arial", size=9)
            else:
                pdf.set_font("Arial", size=9)
            pdf.set_text_color(0, 0, 0)
            # Strip markdown bold/italic markers for clean PDF text
            import re as _re
            clean_context = _re.sub(r'\*\*(.+?)\*\*', r'\1', context)
            clean_context = _re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', clean_context)
            pdf.multi_cell(0, 6, clean_context, align="L")
            pdf.ln(4)
            pdf.set_text_color(0, 0, 0)

        # Table header
        if os.path.exists(font_path):
            try:
                pdf.set_font(font_name, size=8)
            except Exception:
                pdf.set_font("Arial", size=7)
        else:
            pdf.set_font("Arial", size=7)
        col_widths = [15, 48, 18, 13, 18, 18, 18, 15, 18]
        headers = ["EmpID", "QueryTime", "Score", "Anom", "RowsEx", "RowsRet", "ExecT", "QType", "LogID"]
        # Print table header row
        for i, h in enumerate(headers):
            pdf.cell(col_widths[i], 8, h, 1, 0, 'C')
        pdf.ln()
        if os.path.exists(font_path):
            try:
                pdf.set_font(font_name, size=9)
            except Exception:
                pdf.set_font("Arial", size=9)
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
            try:
                pdf.set_font(font_name, size=8)
            except Exception:
                pdf.set_font("Arial", style="B", size=8)
        else:
            pdf.set_font("Arial", style="B", size=8)
        pdf.set_text_color(220, 0, 0)
        pdf.cell(0, 8, "*NOTE: Anomaly scores are calculated by Machine Learning and may not be 100% accurate. Use as reference only.", ln=1, align="L")
        pdf.set_text_color(0,0,0)
        pdf.ln(2)
        # Mô tả hệ thống ML
        if os.path.exists(font_path):
            try:
                pdf.set_font(font_name, size=14)
            except Exception:
                pdf.set_font("Arial", style="B", size=14)
        else:
            pdf.set_font("Arial", style="B", size=14)
        pdf.cell(0, 8, "About UEBA-MLVer1 (BETA)", ln=1, align="L")
        if os.path.exists(font_path):
            try:
                pdf.set_font(font_name, size=10)
            except Exception:
                pdf.set_font("Arial", size=10)
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
            try:
                pdf.set_font(font_name, size=12)
            except Exception:
                pdf.set_font("Arial", style="B", size=12)
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
    # Dashboard summary endpoint

# Dashboard summary endpoint (tổng hợp toàn bộ lịch sử)
@app.get("/dashboard/summary")
def dashboard_summary():
    conn = get_connection()
    cursor = conn.cursor()

    # Tổng số truy vấn toàn bộ lịch sử
    cursor.execute("SELECT COUNT(*) FROM QueryLogs")
    total_query_all = cursor.fetchone()[0]

    # Tổng số RowsExamined toàn bộ lịch sử
    cursor.execute("SELECT SUM(RowsExamined) FROM QueryLogs")
    total_rows_examined = cursor.fetchone()[0] or 0

    # Tổng số truy vấn ngoài giờ toàn bộ lịch sử (giả sử ngoài 7h-17h)
    cursor.execute("SELECT COUNT(*) FROM QueryLogs WHERE (DATEPART(HOUR, QueryTime) < 7 OR DATEPART(HOUR, QueryTime) > 17)")
    after_hours_all = cursor.fetchone()[0]

    # Tổng số lần đăng nhập thất bại toàn bộ lịch sử
    cursor.execute("SELECT COUNT(*) FROM AuthenticationLogs WHERE LoginStatus='FAIL'")
    failed_auth_all = cursor.fetchone()[0]

    # Tổng số sự kiện (QueryLogs + AuthenticationLogs)
    cursor.execute("SELECT COUNT(*) FROM AuthenticationLogs")
    total_auth = cursor.fetchone()[0]
    total_events = total_query_all + total_auth

    # Top 1 nhân viên có nhiều truy vấn nhất
    cursor.execute("SELECT TOP 1 EmployeeID, COUNT(*) AS cnt FROM QueryLogs GROUP BY EmployeeID ORDER BY cnt DESC")
    top_user = cursor.fetchone()
    top_user_id = top_user[0] if top_user else None
    top_user_count = top_user[1] if top_user else 0

    return {
        "total_query_all": total_query_all,
        "total_rows_examined": total_rows_examined,
        "after_hours_all": after_hours_all,
        "failed_auth_all": failed_auth_all,
        "total_events": total_events,
        "top_user_id": top_user_id,
        "top_user_count": top_user_count
    }

import asyncio
# SSE endpoint: Live log stream (monitor QueryLogs table for new entries)
from fastapi.responses import StreamingResponse

@app.get("/live-log-stream")
async def live_log_stream():
    async def event_generator():
        last_log_id = None
        while True:
            try:
                conn = get_connection()
                cursor = conn.cursor()
                # Lần đầu lấy log mới nhất để khởi tạo last_log_id
                if last_log_id is None:
                    cursor.execute("SELECT TOP 1 QueryLogID FROM QueryLogs ORDER BY QueryLogID DESC")
                    row = cursor.fetchone()
                    last_log_id = row[0] if row else 0
                else:
                    # Lấy tất cả log mới hơn last_log_id, theo thứ tự tăng dần
                    cursor.execute("SELECT QueryLogID, EmployeeID, QueryTime, QueryType FROM QueryLogs WHERE QueryLogID > %s ORDER BY QueryLogID ASC", (last_log_id,))
                    rows = cursor.fetchall()
                    for log in rows:
                        log_id, emp_id, q_time, q_type = log
                        data = {
                            "QueryLogID": log_id,
                            "EmployeeID": emp_id,
                            "QueryTime": str(q_time),
                            "QueryType": q_type
                        }
                        yield f"data: {json.dumps(data)}\n\n"
                        last_log_id = log_id
                await asyncio.sleep(1)
            except Exception as e:
                yield f"event: error\ndata: {str(e)}\n\n"
                await asyncio.sleep(2)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/employee/info/{employee_id}")
def get_employee_info(employee_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    # Lấy thông tin employee
    cursor.execute("SELECT EmployeeID, FullName, Role, avatar_url FROM Employees WHERE EmployeeID = %s", (employee_id,))
    emp_row = cursor.fetchone()
    if not emp_row:
        return {"error": "Employee not found"}
    employee = {
        "employee_id": emp_row[0],
        "full_name": emp_row[1],
        "role": emp_row[2],
        "avatar_url": emp_row[3]
    }
    # Lấy các authentication events
    cursor.execute("SELECT LoginTime, LogoutTime, SourceIP, DeviceInfo, LoginStatus, FailureReason FROM AuthenticationLogs WHERE EmployeeID = %s ORDER BY LoginTime DESC", (employee_id,))
    auth_events = [
        {
            "login_time": str(row[0]),
            "logout_time": str(row[1]),
            "source_ip": row[2],
            "device_info": row[3],
            "login_status": row[4],
            "failure_reason": row[5]
        }
        for row in cursor.fetchall()
    ]
    # Lấy các query events
    cursor.execute("SELECT QueryLogID, QueryTime, QueryType, RowsExamined, RowsReturned, ExecutionTime, QueryLength, IsSensitive, SourceIP, Affected_table, Labels FROM QueryLogs WHERE EmployeeID = %s ORDER BY QueryTime DESC", (employee_id,))
    query_events = [
        {
            "query_log_id": row[0],
            "query_time": str(row[1]),
            "query_type": row[2],
            "rows_examined": row[3],
            "rows_returned": row[4],
            "execution_time": row[5],
            "query_length": row[6],
            "is_sensitive": row[7],
            "source_ip": row[8],
            "affected_table": row[9],
            "labels": row[10]
        }
        for row in cursor.fetchall()
    ]
    return {
        **employee,
        "auth_events": auth_events,
        "query_events": query_events
    }
