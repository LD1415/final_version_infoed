from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g, current_app
from flask_login import login_required, current_user
from .models import SkippedQuestion, WrongAnswer
from . import db
import csv
import os
import random, ast
from collections import defaultdict
from sympy import sympify, SympifyError, simplify
from math import isclose
from datetime import datetime
from pytz import timezone as pytz_timezone, UnknownTimeZoneError
from flask_babel import Babel, _, get_locale
import json
import io


def safe_eval(expr):
    try:
        return ast.literal_eval(expr)
    except Exception:
        return None

questions_bp = Blueprint('questions', __name__)
QUESTIONS_CSV = os.path.join(os.path.dirname(__file__), 'data.csv')

def load_questions(grade_filter=None):
    with open(QUESTIONS_CSV, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        questions = list(reader)

        if grade_filter:
            questions = [q for q in questions if q.get('grade') == str(grade_filter)]
        random.shuffle(questions)
        for q in questions:
            if 'question' in q:
                q['question'] = g.question_translations.get(q['question'], q['question'])
            if 'answer' in q:
                q['answer'] = g.question_translations.get(q['answer'], q['answer'])
        return questions



@questions_bp.before_app_request
def load_translations():
    g.translations = {}
    try:
        json_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'quest_trans.json'))
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            lang = str(get_locale())
            g.translations = data.get(lang, {})
            print("Loaded translations for", lang, ":", list(g.translations.items())[:5])

    except (FileNotFoundError, json.JSONDecodeError) as e:
        current_app.logger.warning(f'Failed to load quest_trans.json: {e}')


@questions_bp.route('/questions', methods=['GET', 'POST'])
@login_required
def questionnaire():
#    if 'questions' not in session:
#        session['questions'] =load_questions()
 #       session['index'] = 0

 
#    if 'start_time' not in session:
 #       session['start_time'] = datetime.utcnow().timestamp()
    grade = request.form.get('grade') or session.get('grade')

    if 'questions' not in session or session.get('grade') != grade:
        session['grade'] = grade
        session['questions'] =load_questions(grade_filter=grade)
        session['index'] = 0
        session['start_time'] = datetime.utcnow().timestamp()


    questions = session['questions']
    index = session['index']
    feedback = None 
    show_answer = False
    if request.method == 'GET':
        if not grade:
            return render_template('select_grade.html')

#    grade = request.form.get('grade') or session.get('grade')

    q_data = questions[index]
    question_text = g.question_translations.get(q_data['question'], q_data['question'])
    answer_text = g.question_translations.get(q_data['answer'], q_data['answer'])

    if request.method == 'POST':
        user_input= request.form.get('user_answer', '').strip()
        correct_answer = request.form.get('correct_answer')
        action = request.form.get('action')
        card_id = request.form.get('card_id')

        translated_correct_answer = g.translations.get(correct_answer, correct_answer)

        if action =='view_skipped':
            skipped_qs = SkippedQuestion.query.filter_by(user_id=current_user.id).order_by(SkippedQuestion.timestamp.desc()).all()
            return render_template('flashcards.html', skipped_questions=skipped_qs, question=None)
        elif action== 'skip':
            # q_data = questions[index]
            exists = SkippedQuestion.query.filter_by(user_id=current_user.id, question=q_data['question']).first()
            if not exists:
                skipped = SkippedQuestion(
                    user_id=current_user.id,
                    question=q_data['question'],
                    answer=q_data['answer']
                )
                db.session.add(skipped)
                db.session.commit()

            if card_id:
                flashcard = Flashcard.query.get(int(card_id))
                if flashcard:
                    flashcard.priority += 1
                    db.session.commit()
            session['index'] +=1

            if session['index']< len(questions):
                next_q = questions[session['index']]
                question_text = g.question_translations.get(next_q['question'], next_q['question'])
                answer_text = g.question_translations.get(next_q['answer'], next_q['answer'])
                return render_template('flashcards.html', question=next_q, question_text=question_text, answer_text=answer_text, feedback=None, show_answer=False, skipped_questions=None)
            else:
                session.pop('questions', None)
                session.pop('index', None)
                return render_template('flashcards.html', question=None, feedback=None, show_answer=False, skipped_questions=None)

        elif action == 'show_answer':
            show_answer = True
            if not feedback:
                feedback = " "
            return render_template('flashcards.html', question=q_data, question_text=question_text, answer_text=answer_text, feedback= feedback,show_answer=show_answer,skipped_questions=None )

        elif action == 'next':
            session['index'] += 1
            if session['index'] < len(questions):
                next_q = questions[session['index']]
                question_text = g.question_translations.get(next_q['question'], next_q['question'])
                answer_text = g.question_translations.get(next_q['answer'], next_q['answer'])
                return render_template('flashcards.html', question=next_q, question_text=question_text, answer_text=answer_text, feedback=None, show_answer=False, skipped_questions=None)
            else:
                session.pop('questions', None)
                session.pop('index', None)
                return render_template('flashcards.html', question=None, feedback=None, show_answer=False, skipped_questions=None)
        elif action == 'submit':
            try:
            # bey bey space
                user_expr = sympify(user_input.replace(" ", ""))
                correct_expr = sympify(translated_correct_answer.replace(" ", ""))
                user_value = user_expr.evalf()
                correct_value = correct_expr.evalf()
                is_correct = isclose(float(user_value), float(correct_value), rel_tol=1e-9)
            except (SympifyError, ValueError, TypeError):
            # string cmp
                is_correct = (user_input.replace(" ", "").lower() == translated_correct_answer.replace(" ", "").lower())

            if is_correct:
                feedback ="Correct!"
                if card_id:
                    flashcard = Flashcard.query.get(int(card_id))
                    if flashcard:
                        flashcard.priority = max(0, flashcard.priority - 1)
                        db.session.commit()

                if session['index'] < len(questions):
                    next_q = questions[session['index']]
                    return render_template('flashcards.html', question=q_data, feedback=feedback, show_answer=False, skipped_questions=None)
                else:
                    session.pop('questions', None)
                    session.pop('index', None)
                    return render_template('flashcards.html', question=None, feedback=feedback, show_answer=False, skipped_questions=None)
            else:
                feedback ="Incorrect."
                # add incorrect try
                wrong = WrongAnswer(
                    user_id=current_user.id,
                    question=q_data['question'],
                    user_answer=user_input,
                    correct_answer=correct_answer
                )
                db.session.add(wrong)
                if card_id:
                    flashcard = Flashcard.query.get(int(card_id))
                    if flashcard:
                        flashcard.priority += 2
                        db.session.commit()
                else:
                    db.session.commit()
                # stay on quest
                return render_template('flashcards.html', question=q_data, question_text=question_text, answer_text=answer_text, feedback=feedback, show_answer=False, skipped_questions=None)


    if index < len(questions):
        q_data = questions[index]
        question_text = g.question_translations.get(q_data['question'], q_data['question'])
        answer_text = g.question_translations.get(q_data['answer'], q_data['answer'])
        return render_template('flashcards.html', question=q_data, question_text=question_text, answer_text=answer_text, skipped_questions=None)
    else:
        session.pop('questions', None)
        session.pop('index', None)
        return render_template('flashcards.html', question=None, feedback=None, show_answer=False, skipped_questions=None)

@questions_bp.route('/questions/show_answer/<int:question_index>', methods=['GET'])
@login_required
def show_answer(question_index):
    questions = session.get('questions')
    if not questions or question_index >= len(questions):
        return redirect(url_for('questions.questionnaire'))

    question = questions[question_index]
    question_text = g.question_translations.get(q_data['question'], q_data['question'])
    answer_text = g.question_translations.get(q_data['answer'], q_data['answer'])
    return render_template(
        'flashcards.html',
        question=question,
        question_text=question_text,
        answer_text=answer_text,
        feedback=" Incorrect.",
        show_answer=True,
        skipped_questions=None,
        session={'index': question_index}
    )


@questions_bp.route('/skipped' )
@login_required
def view_skipped_questions():
    skipped= SkippedQuestion.query.filter_by(user_id=current_user.id).order_by(SkippedQuestion.timestamp.desc()).all()
    grouped =  defaultdict(list)

    for q in skipped:
        q.translated_question = g.translations.get(q.question, q.question)
        q.translated_answer = g.translations.get(q.answer, q.answer)
        date_key =q.timestamp.strftime('%Y-%m-%d')
        grouped_skipped[q.timestamp.date()].append(q)

    return render_template('skipped_questions.html', grouped_skipped=grouped_skipped)

@questions_bp.route('/view_skipped')
@login_required
def view_skipped():
    try:
        json_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'quest_trans.json'))
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            lang = str(get_locale())
            translations = data.get(lang, {})
    except Exception:
        translations = {}

    skipped_qs = SkippedQuestion.query.filter_by(user_id=current_user.id).all()
    grouped_skipped = defaultdict(list)

    for q in skipped_qs:
        q.translated_question = translations.get(q.question, q.question)
        date_key = q.timestamp.date()
        grouped_skipped[date_key].append(q)

    grouped_skipped = dict(sorted(grouped_skipped.items(), reverse=True))

    return render_template(
        'view_skipped.html',
        grouped_skipped=grouped_skipped,
        translations=translations
    )

@questions_bp.route('/answer_skipped/<int:question_id>', methods=['GET', 'POST'])
@login_required
def answer_skipped(question_id):
    skipped_questions = SkippedQuestion.query.filter_by(user_id=current_user.id).order_by(SkippedQuestion.timestamp).all()
    current_question =next((q for q in skipped_questions  if q.id == question_id),None)
    if not current_question:
        flash('Question not found.', 'danger')
        return redirect(url_for('questions.view_skipped'))

    next_question = None
    current_index = skipped_questions.index(current_question)
    if current_index + 1 < len(skipped_questions):
        next_question = skipped_questions[current_index + 1]

    question_text = g.question_translations.get(current_question.question, current_question.question)
    answer_text = g.question_translations.get(current_question.answer, current_question.answer)

    feedback = None 
    show_answer = False

    if request.method == 'POST':
        if 'show_answer' in request.form:
            show_answer= True
        elif 'user_answer' in request.form:
            user_answer = request.form.get('user_answer', '').strip()
            correct_answer = current_question.answer.strip()
            try:
            # bye bye space
                user_expr = sympify(user_answer.replace(" ", ""))
                correct_expr = sympify(correct_answer.replace(" ", ""))
                user_value = user_expr.evalf()
                correct_value = correct_expr.evalf()
                is_correct = isclose(float(user_value), float(correct_value), rel_tol=1e-9)
            except (SympifyError, ValueError, TypeError):
            # string cmp
                is_correct = (user_answer.replace(" ", "").lower() == correct_answer.replace(" ", "").lower())

            if is_correct:
                feedback = 'correct'
                # rm skip
                db.session.delete(current_question)
                db.session.commit()
            else:
                feedback = 'incorrect'

    return render_template(
        'answer_skipped.html',
        question=current_question,
        question_text=question_text,
        answer_text=answer_text,
        next_question=next_question,
        feedback=feedback,
        show_answer=show_answer
    )

@questions_bp.route('/skipped',methods=['GET', 'POST'])
@login_required
def answer_skipped_flow():
    if 'skipped_queue' not in session:
        skipped = SkippedQuestion.query.filter_by(user_id=current_user.id).order_by(SkippedQuestion.timestamp.asc()).all()
        session['skipped_queue'] =[s.id for s in skipped]
        session['skipped_index'] = 0

    skipped_ids = session.get('skipped_queue', [])
    index = session.get('skipped_index', 0)
    if request.method =='POST':
        action = request.form.get('action')
        user_answer = request.form.get('user_answer', '').strip()
        correct_answer = request.form.get('correct_answer', '').strip()
        question_id = request.form.get('question_id')

        if action =='quit':
            session.pop('skipped_queue', None)
            session.pop('skipped_index', None)
            return redirect(url_for('views.home'))

        if user_answer.strip().lower() == correct_answer.strip().lower():
            to_remove = SkippedQuestion.query.get(int(question_id))
            db.session.delete(to_remove)
            db.session.commit()
        else:
            # store wrong
            skipped =SkippedQuestion.query.get(int(question_id))
            wrong =WrongAnswer(
                user_id=current_user.id,
                question=skipped.question,
                user_answer=user_answer,
                correct_answer=skipped.answer
            )
            db.session.add(wrong)
            db.session.commit()
        session['skipped_index']+= 1

    if session['skipped_index'] <len(skipped_ids):
        current_id = skipped_ids[session['skipped_index']]
        skipped_q = SkippedQuestion.query.get(current_id)
        question_text = g.question_translations.get(skipped_q.question, skipped_q.question)
        answer_text = g.question_translations.get(skipped_q.answer, skipped_q.answer)
        return render_template('answer_skipped.html', skipped=skipped_q, question_text=question_text, answer_text=answer_text)
    else:
        session.pop('skipped_queue', None)
        session.pop('skipped_index', None)
        return render_template('answer_skipped.html', skipped=None)

import pytz
from datetime import datetime

def adapt_timestamp_to_timezone(utc_dt, timezone_str):
    # tz convert
    if utc_dt.tzinfo is None:
        utc_dt = pytz.utc.localize(utc_dt)

    try:
        user_tz = pytz.timezone(timezone_str)
        local_dt = utc_dt.astimezone(user_tz)
        return local_dt.strftime('%Y-%m-%d %H:%M')
    except pytz.UnknownTimeZoneError:
        return utc_dt.strftime('%Y-%m-%d %H:%M (UTC)')


@questions_bp.route('/wrong-answers', methods=['GET'])
@login_required
def wrong_answers():
    sort_by = request.args.get('sort_by', 'newest')
    search_query = request.args.get('search', '').strip().lower()
    user_timezone = request.args.get('timezone', 'UTC')

    base_query = WrongAnswer.query.filter(
        WrongAnswer.user_id == current_user.id,
        WrongAnswer.user_answer.isnot(None),
        WrongAnswer.user_answer != ''
    )

    if sort_by == 'oldest':
        all_wrong_answers = base_query.order_by(WrongAnswer.timestamp.asc()).all()
    else:
        all_wrong_answers = base_query.order_by(WrongAnswer.timestamp.desc()).all()

    if search_query:
        all_wrong_answers = [
            wa for wa in all_wrong_answers if search_query in wa.question.lower()
        ]

    #timestamps to tz
    for wa in all_wrong_answers:
        wa.local_timestamp = adapt_timestamp_to_timezone(wa.timestamp, user_timezone)
        wa.translated_question = g.question_translations.get(wa.question, wa.question)
        wa.translated_correct = g.question_translations.get(wa.correct_answer, wa.correct_answer)
        wa.translated_user = g.translations.get(wa.user_answer, wa.user_answer)


    grouped_answers = {}
    for wa in all_wrong_answers:
        key = wa.translated_question  
        if key not in grouped_answers:
            grouped_answers[key] = []
        grouped_answers[key].append(wa)

    return render_template('wrong_answers.html',
                           grouped_answers=grouped_answers,
                           sort_by=sort_by,
                           user_timezone=user_timezone)



@questions_bp.route('/rev-question', methods=['GET', 'POST'])
@login_required
def rev_question():
    if 'questions' not in session:
        session['questions'] = load_questions()
        session['index'] = 0
        session['start_time'] = datetime.utcnow().timestamp()

    questions = session['questions']
    index = session['index']
    feedback = None
    show_answer = False

    if request.method == 'POST':
        user_input = request.form.get('user_answer', '').strip()
        correct_answer = request.form.get('correct_answer')
        action = request.form.get('action')
        card_id = request.form.get('card_id')

        q_data = questions[index]
        question_text = g.question_translations.get(q_data['question'], q_data['question'])
        answer_text = g.question_translations.get(q_data['answer'], q_data['answer'])
        translated_correct_answer = g.question_translations.get(correct_answer, correct_answer)

        if action == 'view_skipped':
            skipped_qs = SkippedQuestion.query.filter_by(user_id=current_user.id).order_by(SkippedQuestion.timestamp.desc()).all()
            return render_template('full_rev.html', skipped_questions=skipped_qs, question=None)
        elif action == 'skip':
            exists = SkippedQuestion.query.filter_by(user_id=current_user.id, question=q_data['question']).first()
            if not exists:
                skipped = SkippedQuestion(
                    user_id=current_user.id,
                    question=q_data['question'],
                    answer=q_data['answer']
                )
                db.session.add(skipped)
                db.session.commit()

            if card_id:
                flashcard = Flashcard.query.get(int(card_id))
                if flashcard:
                    flashcard.priority += 1
                    db.session.commit()
            session['index'] += 1
            if session['index'] < len(questions):
                q_data = questions[session['index']]
                question_text = g.question_translations.get(q_data['question'], q_data['question'])
                answer_text = g.question_translations.get(q_data['answer'], q_data['answer'])
                return render_template('full_rev.html', question=q_data, question_text=question_text, answer_text=answer_text, feedback=None, show_answer=False, skipped_questions=None)
            else:
                session.pop('questions', None)
                session.pop('index', None)
                return render_template('full_rev.html', question=None, feedback=None, show_answer=False, skipped_questions=None)

        elif action == 'show_answer':
            show_answer = True
            question_text = g.question_translations.get(q_data['question'], q_data['question'])
            answer_text = g.question_translations.get(q_data['answer'], q_data['answer'])

            if not feedback:
                feedback = " "
            return render_template('full_rev.html', question=q_data, question_text=question_text, answer_text=answer_text, feedback= feedback,show_answer=show_answer,skipped_questions=None )
        elif action == 'next':
            session['index'] += 1
            if session['index'] < len(questions):
                q_data = questions[session['index']]
                question_text = g.question_translations.get(q_data['question'], q_data['question'])
                answer_text = g.question_translations.get(q_data['answer'], q_data['answer'])
                return render_template('full_rev.html', question=q_data, question_text=question_text, answer_text=answer_text, feedback=None, show_answer=False, skipped_questions=None)
            else:
                session.pop('questions', None)
                session.pop('index', None)
                return render_template('full_rev.html', question=None, feedback=None, show_answer=False, skipped_questions=None)
        elif action == 'submit':
            question_text = g.question_translations.get(q_data['question'], q_data['question'])
            answer_text = g.question_translations.get(q_data['answer'], q_data['answer'])
            try:
            # bey bey space
                user_expr = sympify(user_input.replace(" ", ""))
                correct_expr = sympify(correct_answer.replace(" ", ""))
                user_value = user_expr.evalf()
                correct_value = correct_expr.evalf()
                is_correct = isclose(float(user_value), float(correct_value), rel_tol=1e-9)
            except (SympifyError, ValueError, TypeError):
            # string cmp
                is_correct = (user_input.replace(" ", "").lower() == correct_answer.replace(" ", "").lower())

            if is_correct:
                feedback = "Correct!"
                if card_id:
                    flashcard = Flashcard.query.get(int(card_id))
                    if flashcard:
                        flashcard.priority = max(0, flashcard.priority - 1)
                        db.session.commit()

                if session['index'] < len(questions):
                    return render_template('full_rev.html', question=q_data, question_text=question_text, answer_text=answer_text, feedback=feedback, show_answer=False, skipped_questions=None)
                else:
                    session.pop('questions', None)
                    session.pop('index', None)
                    return render_template('full_rev.html', question=None, feedback=feedback, show_answer=False, skipped_questions=None)

            else:
                feedback = "Incorrect."
                question_text = g.question_translations.get(q_data['question'], q_data['question'])
                answer_text = g.question_translations.get(q_data['answer'], q_data['answer'])

                # add incorrect try
                wrong = WrongAnswer(
                    user_id=current_user.id,
                    question=q_data['question'],
                    user_answer=user_input,
                    correct_answer=correct_answer
                )
                db.session.add(wrong)
                if card_id:
                    flashcard = Flashcard.query.get(int(card_id))
                    if flashcard:
                        flashcard.priority += 2
                        db.session.commit()
                else:
                    db.session.commit()
                # stay on quest
                return render_template('full_rev.html', question=q_data, question_text=question_text, feedback=feedback, show_answer=False, skipped_questions=None)
    
    q_data = questions[index]
    question_text = g.question_translations.get(q_data['question'], q_data['question'])
    answer_text = g.question_translations.get(q_data['answer'], q_data['answer'])

    if index < len(questions):
        return render_template('full_rev.html', question=q_data, question_text=question_text, answer_text=answer_text, skipped_questions=None)
    else:
        session.pop('questions', None)
        session.pop('index', None)
        return render_template('full_rev.html', question=None, skipped_questions=None)