from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
from storage import store

auth = Blueprint('auth', __name__)


@auth.route('/login', methods=['GET', 'POST'], endpoint='login')
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Nazwa użytkownika i hasło są wymagane.', 'error')
            return render_template('login.html')

        # Przeładuj dane użytkowników z Cloud Storage
        store.reload_users()

        # Znajdź użytkownika po loginie w liście
        user = next((u for u in store.users if u.get('login') == username), None)
        if user and check_password_hash(user.get('haslo', ''), password):
            session['username'] = username
            flash('Logowanie pomyślne!', 'success')
            return redirect(url_for('dashboard.dashboard'))
        else:
            flash('Nieprawidłowa nazwa użytkownika lub hasło', 'error')

    return render_template('login.html')


@auth.route('/register', methods=['GET', 'POST'], endpoint='register')
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password')

        if not username:
            flash('Nazwa użytkownika nie może być pusta.', 'error')
            return redirect(url_for('auth.register'))

        if not password:
            flash('Hasło nie może być puste.', 'error')
            return redirect(url_for('auth.register'))

        # Przeładuj dane użytkowników z Cloud Storage
        store.reload_users()

        # Sprawdź, czy login już istnieje
        if any(u.get('login') == username for u in store.users):
            flash('Nazwa użytkownika już istnieje', 'error')
        elif password != confirm_password:
            flash('Hasła nie pasują do siebie', 'error')
        elif len(password) < 6:
            flash('Hasło musi mieć co najmniej 6 znaków', 'error')
        else:
            new_user = {
                'login': username,
                'haslo': generate_password_hash(password),
                'data_utworzenia': datetime.now(timezone.utc).isoformat()
            }
            store.users.append(new_user)
            store.save_and_reload_users()
            flash('Rejestracja zakończona sukcesem! Zaloguj się.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('register.html')


@auth.route('/logout', endpoint='logout')
def logout():
    session.pop('username', None)
    flash('Zostałeś wylogowany', 'success')
    return redirect(url_for('dashboard.index'))
