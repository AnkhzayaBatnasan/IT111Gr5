from flask import Blueprint
from .config import APP_NAME, APP_VERSION, APP_DESCRIPTION

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
def home():
    return f"{APP_NAME} v{APP_VERSION} - {APP_DESCRIPTION}"
