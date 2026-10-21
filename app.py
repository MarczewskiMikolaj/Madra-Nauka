import os

from madra import create_app
from werkzeug.serving import WSGIRequestHandler


class PrivateRequestHandler(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        # Authorization codes must not appear in local HTTP logs.
        original_path = self.path
        try:
            if original_path.split("?", 1)[0] == "/auth/callback":
                self.path = "/auth/callback"
            super().log_request(code, size)
        finally:
            self.path = original_path


app = create_app()

if __name__ == "__main__":
    # Local development must not keep stale templates after UI edits.
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True
    port = int(os.environ.get("PORT", 8080))
    app.run(
        host="127.0.0.1", port=port, debug=False, request_handler=PrivateRequestHandler
    )
