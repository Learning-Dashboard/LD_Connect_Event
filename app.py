from flask import Flask, jsonify
from routes.github_routes import github_bp
from routes.taiga_routes import taiga_bp
from routes.excel_routes import excel_bp
from routes.recovery_routes import recovery_bp
from config.credentials_loader import (
    CredentialsConfigError,
    ProjectCredentialsNotFoundError,
    validate_config_file,
)
from config.logger_config import setup_logging
import logging
import os

setup_logging()
logger = logging.getLogger(__name__)


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(CredentialsConfigError)
    def handle_credentials_config_error(exc):
        logger.error("Credentials configuration error: %s", exc)
        return (
            jsonify(
                {
                    "error": "Credentials configuration error",
                    "details": str(exc),
                }
            ),
            500,
        )

    @app.errorhandler(ProjectCredentialsNotFoundError)
    def handle_unknown_project(exc):
        logger.warning("Unknown project in credentials config: %s", exc)
        return (
            jsonify(
                {
                    "error": "Unknown project credentials",
                    "details": str(exc),
                }
            ),
            400,
        )


def _log_credentials_config_status() -> None:
    try:
        config_path = validate_config_file()
    except CredentialsConfigError as exc:
        logger.warning("%s", exc)
    else:
        logger.info("Using credentials config at %s", config_path)


def create_app():
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    # Register  blueprint routes
    app.register_blueprint(github_bp)
    app.register_blueprint(taiga_bp)
    app.register_blueprint(excel_bp)
    app.register_blueprint(recovery_bp)

    app.register_blueprint(github_bp, url_prefix="/webhooks", name="github_bp_prefixed")
    app.register_blueprint(taiga_bp, url_prefix="/webhooks", name="taiga_bp_prefixed")
    app.register_blueprint(excel_bp, url_prefix="/webhooks", name="excel_bp_prefixed")
    _register_error_handlers(app)
    _log_credentials_config_status()
    logger.info("Flask created and Blueprints registered successfully.")
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
        host="127.0.0.1",
        port=5000,
    )
