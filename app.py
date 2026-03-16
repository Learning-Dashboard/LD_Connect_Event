from flask import Flask
from routes.github_routes import github_bp
from routes.taiga_routes import taiga_bp
from routes.excel_routes import excel_bp
from config.logger_config import setup_logging
import logging
import os

setup_logging()
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)

    # Register  blueprint routes
    app.register_blueprint(github_bp)
    app.register_blueprint(taiga_bp)
    app.register_blueprint(excel_bp)
    logger.info("Flask created and Blueprints registered successfully.")
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
        host="127.0.0.1",
        port=5000,
    )
