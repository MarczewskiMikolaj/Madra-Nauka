import os
from flask import Blueprint, send_from_directory, current_app, render_template, abort

pwa = Blueprint('pwa', __name__)

ALLOWED_ICONS = {
    'icon-16x16.png', 'icon-32x32.png', 'icon-72x72.png',
    'icon-96x96.png', 'icon-128x128.png', 'icon-144x144.png',
    'icon-152x152.png', 'icon-192x192.png', 'icon-384x384.png',
    'icon-512x512.png',
}


@pwa.route('/manifest.json', endpoint='manifest')
def manifest():
    return current_app.send_static_file('manifest.json')


@pwa.route('/service-worker.js', endpoint='service_worker')
def service_worker():
    return current_app.send_static_file('service-worker.js')


@pwa.route('/favicon.ico', endpoint='favicon')
def favicon():
    return current_app.send_static_file('favicon.ico')


@pwa.route('/icons/<path:filename>', endpoint='icons')
def icons(filename):
    if filename not in ALLOWED_ICONS:
        abort(404)
    icons_dir = os.path.join(current_app.root_path, 'static', 'icons')
    return send_from_directory(icons_dir, filename)


@pwa.route('/offline', endpoint='offline')
def offline():
    return render_template('offline.html')
