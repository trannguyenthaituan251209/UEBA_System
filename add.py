import pyodbc

# Kết nối tới SQL Server
conn = pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=localhost\\SQLEXPRESS01;"
        "DATABASE=AuthenticationManager;"
        "Trusted_Connection=yes;"
        "Encrypt=no;"
        "TrustServerCertificate=yes;"
)
cursor = conn.cursor()

# Thêm cột avatar_url nếu chưa có
try:
    cursor.execute("ALTER TABLE Employees ADD avatar_url NVARCHAR(255)")
    conn.commit()
except Exception as e:
    print("Có thể cột đã tồn tại:", e)

# Cập nhật avatar_url cho 17 user đầu tiên (giả sử có cột ID tăng dần từ 1)
# for i in range(1, 22):
#     url = fr'.\assets\user{i}.png'
#     cursor.execute(
#         "UPDATE Employees SET avatar_url = ? WHERE EmployeeID = ?",
#         url, i
#     )


conn.commit()
cursor.close()
conn.close()
print("Đã cập nhật avatar_url cho 17 user đầu tiên.")