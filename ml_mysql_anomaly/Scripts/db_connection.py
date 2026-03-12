import os
import pymssql

def get_connection():

    # conn = pymssql.connect(
    #     server=os.environ.get('DB_SERVER', 'ueba-database.database.windows.net'),
    #     user=os.environ.get('DB_USER', 'tuan2509'),
    #     password=os.environ.get('DB_PASSWORD', ''),
    #     database=os.environ.get('DB_NAME', 'free-sql-db-8454879'),
    #     port=int(os.environ.get('DB_PORT', 1433))
    # )
    # return conn
    conn = pymssql.connect(
        server='ueba-database.database.windows.net',
        user='tuan2509',
        password='Tuan1234@',
        database='free-sql-db-8454879',
        port=1433
    )
    return conn
try:
    conn = get_connection()
    print("✅ Kết nối SQL Server thành công")
    conn.close()
except Exception as e:
    print("❌ Lỗi kết nối:")
    print(e)
