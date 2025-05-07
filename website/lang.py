from flask import Blueprint, request, redirect, url_for, session
from flask_babel import _
from flask_login import login_required

lang = Blueprint('lang', __name__)

@lang.route('/set_language/<language>')
@login_required
def set_language(language):
    session['lang'] = language
    return redirect(request.referrer or url_for('views.home'))
