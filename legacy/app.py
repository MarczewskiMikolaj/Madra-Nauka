import os

from flask import Flask

from config import SECRET_KEY
from blueprints.auth import auth
from blueprints.dashboard import dashboard_bp
from blueprints.sets import sets
from blueprints.learn import learn
from blueprints.test import test
from blueprints.profile import profile_bp
from blueprints.pwa import pwa
from blueprints.notifications import notifications

app = Flask(__name__)
app.secret_key = SECRET_KEY

app.register_blueprint(auth)
app.register_blueprint(dashboard_bp)
app.register_blueprint(sets, url_prefix='/zestawy')
app.register_blueprint(learn, url_prefix='/zestawy')
app.register_blueprint(test, url_prefix='/zestawy')
app.register_blueprint(profile_bp)
app.register_blueprint(pwa)
app.register_blueprint(notifications)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
