import os
import pyodbc

def get_connection():
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={os.environ['DB_SERVER']};"
        f"DATABASE={os.environ['DB_NAME']};"
        f"UID={os.environ['DB_USER']};"
        f"PWD={os.environ['DB_PASSWORD']};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
    )
    # conn = pyodbc.connect(
    #     "DRIVER={ODBC Driver 18 for SQL Server};"
    #     "SERVER=tcp:ueba-database.database.windows.net,1433;"
    #     "DATABASE=free-sql-db-8454879;"
    #     "UID=tuan251209;"
    #     "PWD=Tuan1234@;"
    #     "Encrypt=yes;"
    #     "TrustServerCertificate=no;"
    # )
    return conn


try:
    conn = get_connection()
    print("✅ Kết nối SQL Server thành công")
    conn.close()
except Exception as e:
    print("❌ Lỗi kết nối:")
    print(e)
