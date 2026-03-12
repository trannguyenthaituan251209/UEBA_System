import os
import pymssql

def get_connection():
    # conn = pymssql.connect(
    #     server=os.environ['DB_SERVER'],
    #     user=os.environ['DB_USER'],
    #     password=os.environ['DB_PASSWORD'],
    #     database=os.environ['DB_NAME'],
    #     port=1433  # hoặc port bạn dùng cho Azure SQL
    # )
    # return conn
    conn = pymssql.connect(
        server=os.environ.get('DB_SERVER', 'ueba-database.database.windows.net'),
        user=os.environ.get('DB_USER', 'tuan2509'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'free-sql-db-8454879'),
        port=int(os.environ.get('DB_PORT', 1433))
    )
    return conn

try:
    conn = get_connection()
    print("✅ Kết nối SQL Server thành công")
    conn.close()
except Exception as e:
    print("❌ Lỗi kết nối:")
    print(e)
