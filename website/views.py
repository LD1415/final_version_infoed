from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for, session, g
from flask_login import current_user, login_required
from . import db
from .models import TimeSpent, Note
import json
import os
from datetime import datetime, date, timedelta, timezone
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


def get_adjusted_local_time(offset_minutes):
    utc_now = datetime.utcnow().replace(tzinfo=timezone.utc)
    adjusted = utc_now + timedelta(minutes=offset_minutes) + timedelta(hours=3)
    return adjusted


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
            flash(_('Note is too short!'), category='error')
        else:
            new_note = Note(data=note, user_id=current_user.id)
            db.session.add(new_note)  # note la db
            db.session.commit()
            flash(_('Note added!'), category='success')
    
    today = date.today()
    record = TimeSpent.query.filter_by(user_id=current_user.id, date=today).first()
    minutes_spent_today = record.time_spent_seconds // 60 if record else 0

    # tot notes 2 view
    user_notes = Note.query.filter_by(user_id=current_user.id).all()
    current_year = today.year
    all_months = get_all_days_in_year(current_year)
    times_by_month = get_times_by_month(current_user.id, current_year)

    return render_template(
        "home.html",
        user=current_user,
        notes=user_notes,
        minutes_spent_today=minutes_spent_today,
        all_months=all_months,
        times_by_month=times_by_month,
        current_year=current_year
    )

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


@views.route('/set_lang/<lang>')
def set_lang(lang):
    print(f"Changing language to {lang}")  #arata pt debug
    session['lang'] = lang
    print(f"Session after change: {session['lang']}")
    return redirect(request.referrer or url_for('views.home'))


@views.route('/update-time', methods=['POST'])
@login_required
def update_time():
    now = datetime.utcnow()
    last_ping = session.get('last_ping')

    if last_ping:
        try:
            delta = int((now - datetime.fromtimestamp(last_ping)).total_seconds())
        except Exception:
            delta = 0    
    else:
        delta = 0
    session['last_ping'] = now.timestamp()
    if delta <= 0 or delta > 600:
        return '', 204
    today = date.today()
    record = TimeSpent.query.filter_by(user_id=current_user.id, date=today).first()
    if not record:
        record = TimeSpent(user_id=current_user.id, date=today, time_spent_seconds=0)
        db.session.add(record)
    record.time_spent_seconds += delta
    db.session.commit()
    return '', 204


@views.route('/show-time-json')
@login_required
def show_time_json():
    today = date.today()
    record = TimeSpent.query.filter_by(user_id=current_user.id, date=today).first()
    minutes = record.time_spent_seconds //60 if record else 0
    return jsonify(minutes=minutes)

@views.route('/adjusted-save-time', methods=['POST'])
@login_required
def adjusted_save_time():
    data = json.loads(request.data)
    offset = data.get('timezoneOffset')

    if offset is None:
        return jsonify({'error': 'Missing timezoneOffset'}), 400

    # tz dif
    start_time = session.get('start_time')
    if start_time:
        time_spent = int(datetime.utcnow().timestamp() - start_time)
        local_time = get_adjusted_local_time(offset)
        today = local_time.date()

        record = TimeSpent.query.filter_by(user_id=current_user.id, date=today).first()
        if record:
            record.time_spent_seconds += time_spent
        else:
            record = TimeSpent(user_id=current_user.id, date=today, time_spent_seconds=time_spent)
            db.session.add(record)
        db.session.commit()
        session.pop('start_time', None)

    return '', 204