ACTIWELL BACKEND - HƯỚNG DẪN CÀI ĐẶT VÀ TRIỂN KHAI

Tài liệu này hướng dẫn cách cài đặt và chạy hệ thống Actiwell Backend trên một máy chủ Linux (ví dụ: Raspberry Pi, Ubuntu Server). Hệ thống được thiết kế theo cấu trúc package và sử dụng Application Factory pattern để đảm bảo tính ổn định và khả năng mở rộng.

📋 BƯỚC 1: CHUẨN BỊ MÔI TRƯỜNG
1.1. Cập nhật hệ thống
Generated bash
sudo apt update && sudo apt full-upgrade -y

1.2. Cài đặt phần mềm cần thiết
Generated bash
# Cài đặt Python, môi trường ảo, MariaDB (tương thích MySQL) và công cụ USB
sudo apt install -y python3 python3-pip python3-venv mariadb-server usbutils

1.3. Tạo người dùng và cấu trúc thư mục
# Tạo thư mục project gốc
sudo mkdir -p /opt/actiwell
cd /opt/actiwell

# Tạo người dùng 'actiwell' riêng cho ứng dụng để tăng cường bảo mật
sudo useradd -r -s /bin/false -d /opt/actiwell actiwell

# Gán quyền sở hữu thư mục cho người dùng vừa tạo
sudo chown -R actiwell:actiwell /opt/actiwell

📁 BƯỚC 2: THIẾT LẬP MÃ NGUỒN ỨNG DỤNG
2.1. Cấu trúc thư mục ứng dụng

Ứng dụng được tổ chức dưới dạng một package Python (actiwell_backend).

Generated code
/opt/actiwell/
├── run.py                 # File thực thi chính để khởi động server
├── config.py              # File cấu hình trung tâm
├── requirements.txt       # Danh sách các thư viện Python
├── .env                   # Biến môi trường (cơ sở dữ liệu, API keys)
└── actiwell_backend/      # PACKAGE CHÍNH CỦA ỨNG DỤNG
    ├── __init__.py        # Application Factory (create_app)
    ├── models.py          # Models dữ liệu
    ├── database_manager.py# Logic cơ sở dữ liệu
    ├── device_manager.py  # Logic giao tiếp thiết bị
    ├── actiwell_api.py    # Logic tích hợp Actiwell API
    │
    ├── api/               # Chứa các API Blueprints
    │   ├── __init__.py
    │   ├── auth_routes.py
    │   └── device_routes.py
    │
    ├── services/          # Chứa các tiến trình chạy nền
    │   ├── __init__.py
    │   ├── measurement_processor.py
    │   └── sync_retry.py
    │
    ├── static/            # Tài nguyên tĩnh (CSS, JS)
    └── templates/         # Giao diện HTML (Jinja2)

2.2. Sao chép mã nguồn

Sao chép tất cả các file mã nguồn vào máy chủ, đảm bảo đúng cấu trúc thư mục như trên.

2.3. Tạo file requirements.txt

Flask==2.3.3
Flask-CORS==4.0.0
mysql-connector-python==8.1.0
pyserial==3.5
requests==2.31.0
PyJWT==2.8.0
python-dotenv==1.0.0
psutil==5.9.5

2.4. Tạo file cấu hình .env

File này chứa các thông tin nhạy cảm. Tuyệt đối không đưa file này lên Git.

sudo nano /opt/actiwell/.env

Generated env
# Database Configuration
DB_HOST=localhost
DB_USER=actiwell_user
DB_PASSWORD=your_secure_password_here # <--- THAY ĐỔI MẬT KHẨU NÀY
DB_NAME=actiwell_measurements
DB_POOL_SIZE=5

# Actiwell API Configuration (UPDATE THESE VALUES)
ACTIWELL_API_URL=https://api.actiwell.com # <--- Cập nhật URL API
ACTIWELL_API_KEY=your_api_key_here       # <--- Cập nhật API Key
ACTIWELL_LOCATION_ID=1                   # <--- Cập nhật Location ID

# Application Configuration
SECRET_KEY=a_very_long_and_random_secret_key_for_production # <--- THAY ĐỔI SECRET KEY NÀY
JWT_EXPIRE_HOURS=24
WEB_PORT=5000
WEB_HOST=0.0.0.0
FLASK_DEBUG=False

# Device Configuration
AUTO_DETECT_DEVICES=True
DEVICE_TIMEOUT=5

sudo chown actiwell:actiwell /opt/actiwell/.env
sudo chmod 600 /opt/actiwell/.env

🗄️ BƯỚC 3: CÀI ĐẶT CƠ SỞ DỮ LIỆU
3.1. Bảo mật MariaDB

Chạy script bảo mật và đặt mật khẩu root cho cơ sở dữ liệu.
sudo mysql_secure_installation

3.2. Tạo Database và User

Đăng nhập vào MariaDB và chạy các lệnh SQL sau:

sudo mysql -u root -p

CREATE DATABASE actiwell_measurements CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'actiwell_user'@'localhost' IDENTIFIED BY 'your_secure_password_here'; -- Sử dụng mật khẩu đã đặt trong file .env
GRANT ALL PRIVILEGES ON actiwell_measurements.* TO 'actiwell_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;


Lưu ý: Ứng dụng được thiết kế để tự động tạo các bảng cần thiết khi khởi động lần đầu, nhờ vào hàm _ensure_tables_exist() trong database_manager.py.

🐍 BƯỚC 4: THIẾT LẬP MÔI TRƯỜNG PYTHON
4.1. Tạo môi trường ảo (Virtual Environment)
Generated bash
cd /opt/actiwell

# Tạo môi trường ảo với quyền của user 'actiwell'
sudo -u actiwell python3 -m venv venv

# Kích hoạt môi trường ảo
source venv/bin/activate

# Nâng cấp pip và cài đặt các thư viện
pip install --upgrade pip
pip install -r requirements.txt

# Rời khỏi môi trường ảo
deactivate

🔌 BƯỚC 5: CẤU HÌNH QUYỀN TRUY CẬP THIẾT BỊ USB

Bước này rất quan trọng để ứng dụng có thể đọc dữ liệu từ thiết bị Tanita/InBody.

5.1. Cấp quyền truy cập cổng Serial
Generated bash
# Thêm user 'actiwell' vào nhóm 'dialout' để có quyền truy cập cổng serial
sudo usermod -a -G dialout actiwell

5.2. Tạo quy tắc udev

Quy tắc này sẽ tự động cấp quyền cho các thiết bị khi được cắm vào.

Generated bash
sudo bash -c 'cat > /etc/udev/rules.d/99-actiwell-devices.rules' << 'EOF'
# Grant members of the 'dialout' group access to USB-to-Serial devices
SUBSYSTEM=="tty", KERNEL=="ttyUSB[0-9]*", MODE="0666", GROUP="dialout"
SUBSYSTEM=="tty", KERNEL=="ttyACM[0-9]*", MODE="0666", GROUP="dialout"
EOF

# Tải lại và kích hoạt các quy tắc mới
sudo udevadm control --reload-rules
sudo udevadm trigger

🚀 BƯỚC 6: CHẠY VÀ QUẢN LÝ ỨNG DỤNG
6.1. Chạy thử nghiệm thủ công

Trước khi tạo service, hãy chạy thử để đảm bảo mọi thứ hoạt động.

cd /opt/actiwell

# Chạy ứng dụng với quyền của user 'actiwell'
sudo -u actiwell /opt/actiwell/venv/bin/python run.py


Bạn sẽ thấy log khởi động. Mở trình duyệt và truy cập http://<your-server-ip>:5000. Nếu thành công, nhấn Ctrl+C để dừng.

6.2. Tạo systemd Service để chạy nền (Production)
sudo nano /etc/systemd/system/actiwell-backend.service



Generated ini
[Unit]
Description=Actiwell Body Measurement Backend
After=network.target mariadb.service
Wants=mariadb.service

[Service]
Type=simple
User=actiwell
Group=actiwell
WorkingDirectory=/opt/actiwell
ExecStart=/opt/actiwell/venv/bin/python run.py
Restart=on-failure
RestartSec=5
# Đảm bảo PYTHONPATH bao gồm thư mục làm việc để import 'config'
Environment="PYTHONPATH=/opt/actiwell"

[Install]
WantedBy=multi-user.target


Lưu file và quản lý service bằng các lệnh sau:

Generated bash
# Tải lại cấu hình systemd
sudo systemctl daemon-reload

# Kích hoạt service để tự khởi động cùng hệ thống
sudo systemctl enable actiwell-backend.service

# Khởi động service ngay lập tức
sudo systemctl start actiwell-backend.service

# Kiểm tra trạng thái service
sudo systemctl status actiwell-backend.service

# Xem log của service
sudo journalctl -u actiwell-backend.service -f

🌐 BƯỚC 7: TRUY CẬP VÀ KIỂM TRA HỆ THỐNG

Dashboard: http://<your-server-ip>:5000

Health Check: curl http://localhost:5000/api/health

Đăng nhập (mặc định):

Username: admin

Password: actiwell123 (Nên thay đổi trong auth_routes.py cho môi trường production)

🚨 TROUBLESHOOTING

Lỗi "ImportError: No module named 'config'": Đảm bảo bạn đã thêm Environment="PYTHONPATH=/opt/actiwell" vào file service systemd hoặc chạy ứng dụng từ thư mục /opt/actiwell.

Không kết nối được thiết bị:

Kiểm tra thiết bị có được nhận không: ls -l /dev/ttyUSB*

Kiểm tra quyền của user: groups actiwell (phải có dialout).

Service không khởi động: Kiểm tra log chi tiết: sudo journalctl -u actiwell-backend.service --no-pager.

🎉 Chúc mừng! Hệ thống Actiwell Backend của bạn đã sẵn sàng hoạt động!