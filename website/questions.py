from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g, current_app
from flask_login import login_required, current_user
from .models import SkippedQuestion, WrongAnswer
from . import db
import csv
import os
import random, ast
from collections import defaultdict
from sympy import sympify, SympifyError, Eq
from math import isclose
from datetime import datetime
from pytz import timezone as pytz_timezone, UnknownTimeZoneError
from flask_babel import Babel, _, get_locale
import json
import io

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import nltk
from nltk.corpus import wordnet as wn
from nltk.tokenize import sent_tokenize
import nltk.data

import unicodedata
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application, convert_xor
from sympy.core.relational import Relational


#nltk.download('wordnet')
#nltk.download('omw-1.4')
#nltk.download('punkt')

from nltk.tokenize.punkt import PunktLanguageVars, PunktSentenceTokenizer
from nltk.stem import WordNetLemmatizer
import re
from difflib import SequenceMatcher
import types

try:
    correct_expr = sympify(correct_answer)
    print("Parsed correct:", correct_expr, type(correct_expr))

    if isinstance(correct_expr, types.FunctionType) or callable(correct_expr):
        raise TypeError("correct is a func, not equiv exp.")

    correct_value = correct_expr.evalf()
except Exception as e:
    print("Error parsing or eval correct:", e)
    correct_value = None
WORD_TO_MATH = {
    "plus": "+", "minus": "-", "times": "*", "multiplied by": "*", "divided by": "/", "over": "/", "equals": "=", "equal to": "=", "is equal to": "=", "greater than": ">", "less than": "<", "power of": "^", "squared": "^2", "cubed": "^3"
}

NUM_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"
}

math_transformations = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)

def is_math_expression(text):
    return bool(re.search(r'[\d\+\-\*/\^\=\(\)xXaAbBcC]', text))

def clean_math_expr(expr):
    return re.sub(r'\s+', '', expr)

def text_to_math_expression(text):
    text = text.lower()
    for word, num in NUM_WORDS.items():
        text = re.sub(rf'\b{word}\b', num, text)

    for phrase, symbol in sorted(WORD_TO_MATH.items(), key=lambda x: -len(x[0])):
        text = re.sub(rf'\b{phrase}\b', f' {symbol} ', text)

    text = ' '.join(text.split())
    return clean_math_expr(text)

def get_synonyms(word):
    synonyms = set()
    for syn in wn.synsets(word):
        for lemma in syn.lemmas():
            synonyms.add(lemma.name().replace('_', ' '))
    return list(synonyms)

def semantic_search_in_csv(search_term, file_path='data.csv', column='question', top_n=5):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"{file_path} not found.")

    df = pd.read_csv(file_path)
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in {file_path}.")

    texts = df[column].fillna('').astype(str).tolist()
    synonyms = get_synonyms(search_term)
    extended_query = [search_term] + synonyms

    vectorizer = TfidfVectorizer()
    corpus = texts + [' '.join(extended_query)]
    tfidf_matrix = vectorizer.fit_transform(corpus)

    query_vec = tfidf_matrix[-1]
    text_vecs = tfidf_matrix[:-1]

    similarities = cosine_similarity(query_vec, text_vecs).flatten()
    top_indices = similarities.argsort()[-top_n:][::-1]

    return df.iloc[top_indices].to_dict(orient='records')


def remove_spaces(text):
    return re.sub(r'\s+', '', text.lower().strip())

def remove_diacritics(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def clean_expression(expr):
    expr = remove_diacritics(expr)
    expr = expr.replace(" ", "")
    return expr

lemmatizer = WordNetLemmatizer()

def normalize_text(text):
    # ascii
    text = unicodedata.normalize('NFD', text)
    text = text.encode('ascii', 'ignore').decode('utf-8')  # fara diacritice
    text = re.sub(r'[^\w\s]', '', text.lower().strip())
    return [lemmatizer.lemmatize(word) for word in text.split() if word]

def semantic_match(user_input, correct_answer):
    tokens_user = set(normalize_text(user_input))
    tokens_correct = set(normalize_text(correct_answer))
    overlap = tokens_user.intersection(tokens_correct)
    score = len(overlap) / max(len(tokens_correct), 1)
    return score

def word_tokenize(text):
    return text.lower().split()

def synonym_expand(text):
    if not text.strip():
        return ["empty input"]
    tokens = word_tokenize(text.lower())
    lemmatized = [lemmatizer.lemmatize(token) for token in tokens]
    expanded = set(lemmatized)

    for word in lemmatized:
        for syn in wn.synsets(word):
            for lemma in syn.lemmas():
                expanded.add(lemmatizer.lemmatize(lemma.name().lower().replace("_", " ")))
    return list(expanded)

def semantic_token_overlap_score(user_text, correct_text):
    user_tokens = set(normalize_text(user_text))
    correct_tokens = set(normalize_text(correct_text))
    
    if not user_tokens or not correct_tokens:
        return 0.0

    overlap = user_tokens.intersection(correct_tokens)
    return len(overlap) / len(correct_tokens)
    
def unordered_word_match(user, correct):
# correct orice ord
    user_words = set(normalize_text(user))
    correct_words = set(normalize_text(correct))
    if not correct_words:
        return 0.0
    return len(user_words & correct_words) / len(correct_words)

def semantic_similarity_score(user_answer, correct_answer):
    if user_answer.strip().lower() == correct_answer.strip().lower():
        return 1.0

    user_expanded = " ".join(synonym_expand(user_answer))
    correct_expanded = " ".join(synonym_expand(correct_answer))

    print("u input:", user_answer)
    print("u exp:", user_expanded)
    print("ok input:", correct_answer)
    print("ok exp:", correct_expanded)

    if not user_expanded.strip() or not correct_expanded.strip():
        return 0.0

    try:
        vectorizer = TfidfVectorizer(stop_words=None).fit([user_expanded, correct_expanded])
        tfidf_matrix = vectorizer.transform([user_expanded, correct_expanded])
        score = cosine_similarity(tfidf_matrix[0], tfidf_matrix[1])[0][0]
        return score
    except ValueError:
        return 0.0

def evaluate_user_answer(user_answer, correct_answer):
    user_answer = user_answer.strip()
    correct_answer = correct_answer.strip()

    try:
        # cuv la mate
        if is_math_expression(user_answer) or any(w in user_answer.lower() for w in WORD_TO_MATH):
            user_answer = text_to_math_expression(user_answer)
        if is_math_expression(correct_answer) or any(w in correct_answer.lower() for w in WORD_TO_MATH):
            correct_answer = text_to_math_expression(correct_answer)

        # verif spatii
        if user_answer.lower() == correct_answer.lower():
            return 1.0
        if remove_spaces(user_answer) == remove_spaces(correct_answer):
            return 1.0

        correct_expr = parse_expr(correct_answer, transformations=math_transformations)
        user_expr = parse_expr(user_answer, transformations=math_transformations)

        if isinstance(correct_expr, Relational) and isinstance(user_expr, Relational):
            return 1.0 if correct_expr.equals(user_expr) else 0.0
        if abs(correct_expr.evalf() - user_expr.evalf()) < 1e-6:
            return 1.0

    except Exception as e:
        print("Math evaluation failed:", e)

    if unordered_word_match(user_answer, correct_answer) >= 0.8:
        return 1.0
    if semantic_token_overlap_score(user_answer, correct_answer) >= 0.8:
        return 1.0
    return semantic_similarity_score(user_answer, correct_answer)

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
            def normalize_for_match(text):
                return ' '.join(normalize_text(text))
            norm_user = normalize_for_match(user_input)
            norm_correct = normalize_for_match(translated_correct_answer)
            ratio = SequenceMatcher(None, norm_user, norm_correct).ratio()

            if ratio >= 0.75:
                is_correct = True
            else:
                score = evaluate_user_answer(user_input, translated_correct_answer)
                is_correct = score >= 0.75

#            # bey bey space
 #               user_expr = sympify(user_input.replace(" ", ""))
  #              correct_expr = sympify(translated_correct_answer.replace(" ", ""))
   #             user_value = user_expr.evalf()
    #            correct_value = correct_expr.evalf()
     #           is_correct = isclose(float(user_value), float(correct_value), rel_tol=1e-9)
               
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
            user_input = request.form.get('user_answer', '').strip()
            correct_answer = current_question.answer.strip()
            translated_correct_answer = g.question_translations.get(correct_answer, correct_answer)

            def normalize_for_match(text):
                return ' '.join(normalize_text(text))
            norm_user = normalize_for_match(user_input)
            norm_correct = normalize_for_match(translated_correct_answer)
            ratio = SequenceMatcher(None, norm_user, norm_correct).ratio()

            if ratio >= 0.70:
                is_correct = True
            else:
                score = evaluate_user_answer(user_input, translated_correct_answer)
                is_correct = score >= 0.70

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
            def normalize_for_match(text):
                return ' '.join(normalize_text(text))
            norm_user = normalize_for_match(user_input)
            norm_correct = normalize_for_match(translated_correct_answer)
            ratio = SequenceMatcher(None, norm_user, norm_correct).ratio()

            if ratio >= 0.75:
                is_correct = True
            else:
                score = evaluate_user_answer(user_input, translated_correct_answer)
                is_correct = score >= 0.75


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



@questions_bp.route('/search_questions', methods=['GET', 'POST'])
@login_required
def search_questions():
    results = None
    query = ""

    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        if not query:
            flash("Please enter a search term.")
            return redirect(url_for('questions.search_questions'))

        try:
            results = semantic_search_in_csv(query, file_path=QUESTIONS_CSV, column='question')
        except Exception as e:
            flash(f"Search failed: {str(e)}")
            results = []

    return render_template('search_combined.html', results=results, query=query)
