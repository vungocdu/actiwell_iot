# /opt/actiwell/run.py

from actiwell_backend import create_app, app_state
from config import Config # Giữ config.py ở root

app = create_app(Config)

if __name__ == '__main__':
    # Logic shutdown vẫn có thể đặt ở đây hoặc trong __init__.py
    try:
        app.run(
            host=Config.WEB_HOST,
            port=Config.WEB_PORT,
            debug=Config.DEBUG,
            use_reloader=False
        )
    except KeyboardInterrupt:
        # shutdown_application()
        print("Shutting down...")
    finally:
        # shutdown_application()
        print("Shutdown complete.")