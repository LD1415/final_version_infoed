from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for, session
from flask_login import current_user, login_required
from . import db
from .models import TimeSpent, Note
import json
import os
from datetime import datetime, date, timedelta
import random
from flask_babel import Babel, _
from collections import defaultdict
import subprocess

def get_all_days_in_year(year):
    months = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June", 
              7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"}
    
    all_months = {}
    
    for month in range(1, 13):
        days_in_month = []
        first_day_of_month = datetime(year, month, 1)
        # gaseste zi si luna
        if month == 12:
            last_day_of_month = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day_of_month = datetime(year, month + 1, 1) - timedelta(days=1)
        
        day = first_day_of_month
        while day <= last_day_of_month:
            days_in_month.append(day)
            day += timedelta(days=1)
        
        all_months[months[month]] = days_in_month
    
    return all_months

from flask import current_app

def get_times_by_month(user_id, year):
    # lista date 
    entries = TimeSpent.query.filter(
        TimeSpent.user_id == user_id,
        TimeSpent.date >= datetime(year, 1, 1),
        TimeSpent.date < datetime(year + 1, 1, 1)
    ).all()

    times_by_month = defaultdict(lambda: defaultdict(int))
    months = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June", 
              7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"}

    for entry in entries:
        month_name = months[entry.date.month]
        day = entry.date.day
        times_by_month[month_name][day] += entry.time_spent_seconds

    return times_by_month




views = Blueprint('views', __name__)
lang = Blueprint('lang', __name__)


def save_time_spent():
    start_time = session.get('start_time')
    if start_time:
        time_spent = int(datetime.utcnow().timestamp() - start_time)

        today = datetime.utcnow().date()
        record = TimeSpent.query.filter_by(user_id=current_user.id, date=today).first()

        if record:
            record.time_spent_seconds += time_spent
        else:
            record = TimeSpent(user_id=current_user.id, date=today, time_spent_seconds=time_spent)
            db.session.add(record)

        db.session.commit()
        session.pop('start_time', None)


@views.route('/', methods=['GET', 'POST'])
@login_required
def home():
    if request.method == 'POST':
        note = request.form.get('note')

        if len(note) < 1:
            flash('Note is too short!', category='error')
        else:
            new_note = Note(data=note, user_id=current_user.id)
            db.session.add(new_note)  # note la db
            db.session.commit()
            flash('Note added!', category='success')
    
    today = date.today()
    record = TimeSpent.query.filter_by(user_id=current_user.id, date=today).first()
    if record:
        minutes_spent_today = record.time_spent_seconds // 60
    else:
        minutes_spent_today = 0

    # tot notes 2 view
    user_notes = Note.query.filter_by(user_id=current_user.id).all()

    return render_template("home.html", user=current_user, notes=user_notes)


@views.route('/delete-note', methods=['POST'])
def delete_note():
    note = json.loads(request.data)
    noteId = note['noteId']
    note = Note.query.get(noteId)
    if note:
        if note.user_id == current_user.id:
            db.session.delete(note)
            db.session.commit()
            return jsonify({'success': True}) # good
    return jsonify({'success': False})  # nu merge


@views.route('/change_language/<lang>', methods=['GET'])
@login_required
def change_language(lang):
    if lang in ['en', 'ro', 'fr', 'es']:
        session['lang'] = lang
    else:
        session['lang'] = 'en'
    print(f"Language set to: {session.get('lang')}")
    return redirect(request.referrer)



@views.route('/test')
def test_translation():
    lang = request.args.get('lang')
    if lang in ['en', 'ro', 'fr', 'es']:
        session['lang'] = lang
        print(f"[Route] Lang in query set session to: {lang}")
    return render_template('test_translation.html')




@views.route('/translate')
def translation_page():
    return render_template('test_translation.html')


@views.route('/set_lang/<lang>')
def set_lang(lang):
    session['lang'] = lang
    return redirect(request.referrer or url_for('views.test_translation'))



@views.route('/compile-translations')
def compile_translations():
    try:
        subprocess.run(['pybabel', 'compile', '-d', 'translations'], check=True)
        return "Translations compiled successfully!"
    except subprocess.CalledProcessError as e:
        return f"Failed to compile translations: {str(e)}", 500





@views.route('/time-tracking')
@login_required
def time_tracking():
    times = TimeSpent.query.filter_by(user_id=current_user.id).all()
    # timp/iz
    times_by_day = defaultdict(int)  #{date:total_seconds}
    for record in times:
        times_by_day[record.date] += record.time_spent_seconds
    # org timp zi, luna
    times_by_month = defaultdict(lambda: defaultdict(int))  #{month:{day:total_seconds}}
    for day_date, total_seconds in times_by_day.items():
        times_by_month[day_date.month][day_date.day] = total_seconds
    # arata date
    current_year = date.today().year
    all_months = {month: [] for month in range(1, 13)}

    for month in all_months.keys():
        start_date = date(current_year, month, 1)
        while start_date.month == month:
            all_months[month].append(start_date)
            start_date += timedelta(days=1)

    return render_template('track_time.html',
                           current_year=current_year,
                           current_date=date.today(),
                           times_by_month=times_by_month,
                           all_months=all_months)



@views.route('/day/<date>')
@login_required
def view_day(date):
    record = TimeSpent.query.filter_by(user_id=current_user.id, date=date).first()
    if not record:
        flash('No data for this date.', 'danger')
        return redirect(url_for('views.time_tracking'))
    
    minutes = record.time_spent_seconds // 60
    seconds = record.time_spent_seconds % 60

    return render_template('day_detail.html', date=date, minutes=minutes, seconds=seconds)


@views.route('/update-time', methods=['POST'])
@login_required
def update_time():
    today = date.today()
    record = TimeSpent.query.filter_by(user_id=current_user.id, date=today).first()
    if not record:
        record = TimeSpent(user_id=current_user.id, date=today, time_spent_seconds=0)
        db.session.add(record)
    record.time_spent_seconds += 10 
    db.session.commit()
    return '', 204

@views.route('/show-time')
@login_required
def show_time():
    today = date.today()
    record = TimeSpent.query.filter_by(user_id=current_user.id, date=today).first()
    if record:
        minutes = record.time_spent_seconds//60
    else:
        minutes = 0
    return render_template('show_time.html', minutes=minutes)

@views.route('/show-time-json')
@login_required
def show_time_json():
    today = date.today()
    record = TimeSpent.query.filter_by(user_id=current_user.id, date=today).first()
    minutes = record.time_spent_seconds //60 if record else 0
    return jsonify(minutes=minutes)


@views.route('/time-tracking-table')
@login_required
def time_tracking_table():
    today = date.today()
    current_year = today.year
    all_months = get_all_days_in_year(current_year)
    times_by_month = get_times_by_month(current_user.id, current_year)
# timp tot
    total_time_sec = sum(
        time for month_times in times_by_month.values()
        for time in month_times.values()
    )
    total_minutes = total_time_sec // 60

    print(f"[{datetime.now()}] User {current_user.id} total time: {total_time_sec} sec ({total_minutes} min)")

    return render_template('track_time.html',
                           all_months=all_months,
                           times_by_month=times_by_month,
                           current_year=current_year)

