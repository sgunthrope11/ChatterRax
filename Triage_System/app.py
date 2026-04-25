import os

try:
    from .backend.app import app
except ImportError:
    from backend.app import app


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "False") == "True")
