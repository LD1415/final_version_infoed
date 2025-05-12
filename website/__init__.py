from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from os import path
from flask_login import LoginManager, current_user
from flask_session import Session
from flask_babel import Babel, _

from flask import session, request, g
from flask_migrate import Migrate
from functools import lru_cache

import json

db = SQLAlchemy()
DB_NAME = "database.db"
migrate = Migrate()


#def get_locale():
 #   lang = session.get('lang', 'en')
   # print(f"[Babel] Selected language: {lang}")
  #  return lang

def load_translations():
    with open('translations.json', encoding='utf-8') as f:
        return json.load(f)

def get_lang():
    return session.get('lang', 'en')

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = '`123456dxct56 2435467ueysdfgt`'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_NAME}'

    app.config["SESSION_PERMANENT"] = True
    app.config["SESSION_TYPE"] = "filesystem"
    Session(app)

    db.init_app(app)
    migrate.init_app(app, db)

    @app.context_processor
    def inject_global_vars():
        return dict(_=_)

    from .views import views
    from .auth import auth
    from .models import User, Note, WrongAnswer, SkippedQuestion, Flashcard
    from .questions import questions_bp

    translations = load_translations()

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')
    app.register_blueprint(questions_bp, url_prefix='/')


    with app.app_context():
        db.create_all()

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(id):
        return User.query.get(int(id))

    @app.context_processor
    def inject_skipped_info():
        if current_user.is_authenticated:
            last_skipped = SkippedQuestion.query.filter_by(user_id=current_user.id).order_by(SkippedQuestion.timestamp.desc()).first()
            return dict(last_skipped=last_skipped)
        return dict(last_skipped=None)

    @app.before_request
    def set_translation():
        lang = get_lang()
        g.translations = translations.get(lang, {})

    @app.context_processor
    def inject_translation():
        translations = g.translations
        @lru_cache(maxsize=512)
        def t(text):
            return translations.get(text, text)
        return dict(t=t)

    return app



def create_database(app):
    if not path.exists('website/' + DB_NAME):
        with app.app_context():
            db.create_all()
        print('Created Database!')

