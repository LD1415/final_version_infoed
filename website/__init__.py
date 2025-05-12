from flask import Flask, session, request, g, make_response
from flask_sqlalchemy import SQLAlchemy
from os import path
from flask_login import LoginManager, current_user
from flask_session import Session
from flask_babel import Babel, _

from flask_migrate import Migrate
from functools import lru_cache
import json
import os


db = SQLAlchemy()
DB_NAME = "database.db"
babel = Babel()
migrate = Migrate()

TRANSLATIONS_FILE = 'translations.json'
translations = {}

#def get_locale():
 #   return session.get('lang', 'en')

#def get_locale():
 #   lang = session.get('lang', 'en')
   # print(f"[Babel] Selected language: {lang}")
  #  return lang

def load_translations():
    with open('translations.json', encoding='utf-8') as f:
        return json.load(f)


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = '`123456dxct56 2435467ueysdfgt`'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_NAME}'

    app.config["SESSION_PERMANENT"] = True
    app.config["SESSION_TYPE"] = "filesystem"
    Session(app)

    db.init_app(app)
    migrate.init_app(app, db)

    app.config['BABEL_DEFAULT_LOCALE'] = 'en'
    app.config['BABEL_SUPPORTED_LOCALES'] = ['en', 'ro']
    app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'

    global translations
    translations = load_translations()

    def get_lang():
        return session.get('lang', 'en')

    def get_locale():
        lang = request.args.get('lang')
        if lang:
            session['lang'] = lang
        return lang or session.get('lang', 'en')

    babel.init_app(app, locale_selector=get_locale)

    with open(TRANSLATIONS_FILE, encoding='utf-8') as f:
        translations_data = json.load(f)

    from .views import views
    from .auth import auth
    from .models import User, Note, WrongAnswer, SkippedQuestion, Flashcard
    from .questions import questions_bp

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')
    app.register_blueprint(questions_bp, url_prefix='/')

    with app.app_context():
        db.create_all()

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.after_request
    def disable_cache(response):
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.before_request
    def set_translation():
        lang = session.get('lang', 'en')
        g.translations = translations.get(lang, {})


    @app.context_processor
    def inject_translation():
        current_translations = g.get('translations', {})
        def t(text):
            return current_translations.get(text, text)
        return dict(t=t)

    @app.context_processor
    def inject_globals():
        context = {'_': _}
        if current_user.is_authenticated:
            last_skipped = SkippedQuestion.query.filter_by(user_id=current_user.id)\
                .order_by(SkippedQuestion.timestamp.desc()).first()
            context['last_skipped'] = last_skipped
        else:
            context['last_skipped'] = None
        return context


    return app


def create_database(app):
    if not os.path.exists(os.path.join('website', DB_NAME)):
        with app.app_context():
            db.create_all()
        print('Created Database!')
