from flask import Flask
from routes.github_routes import github_bp
from routes.taiga_routes import taiga_bp
from routes.excel_routes import excel_bp
from config.logger_config import setup_logging
import logging

setup_logging()
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)

    # Register  blueprint routes
    app.register_blueprint(github_bp)
    app.register_blueprint(taiga_bp)
    app.register_blueprint(excel_bp)

    app.register_blueprint(github_bp, url_prefix="/webhooks", name="github_bp_prefixed")
    app.register_blueprint(taiga_bp, url_prefix="/webhooks", name="taiga_bp_prefixed")
    app.register_blueprint(excel_bp, url_prefix="/webhooks", name="excel_bp_prefixed")
    logger.info("Flask created and Blueprints registered successfully.")
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="127.0.0.1", port=5000)
