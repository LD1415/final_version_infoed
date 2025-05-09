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
        return render_template('select_grade.html')  # Grade selection page

#    grade = request.form.get('grade') or session.get('grade')


    if request.method == 'POST':
        user_input= request.form.get('user_answer', '').strip()
        correct_answer = request.form.get('correct_answer')
        action = request.form.get('action')
        card_id = request.form.get('card_id')

        q_data = questions[index]

        if action =='view_skipped':
            skipped_qs = SkippedQuestion.query.filter_by(user_id=current_user.id).order_by(SkippedQuestion.timestamp.desc()).all()
            return render_template('flashcards.html', skipped_questions=skipped_qs, question=None)
        elif action== 'skip':
            q_data = questions[index]
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
                return render_template('flashcards.html', question=questions[session['index']], feedback=None, show_answer=False, skipped_questions=None)
            else:
                session.pop('questions', None)
                session.pop('index', None)
                return render_template('flashcards.html', question=None, feedback=None, show_answer=False, skipped_questions=None)

        elif action == 'show_answer':
            show_answer = True
            if not feedback:
                feedback = " "
            return render_template(
                'flashcards.html',  question=q_data, feedback= feedback,show_answer=show_answer,skipped_questions=None )
        elif action == 'next':
            session['index'] += 1
            if session['index'] < len(questions):
                return render_template('flashcards.html', question=questions[session['index']], feedback=None, show_answer=False, skipped_questions=None)
            else:
                session.pop('questions', None)
                session.pop('index', None)
                return render_template('flashcards.html', question=None, feedback=None, show_answer=False, skipped_questions=None)
        elif action == 'submit':
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
                feedback ="Correct!"
                if card_id:
                    flashcard = Flashcard.query.get(int(card_id))
                    if flashcard:
                        flashcard.priority = max(0, flashcard.priority - 1)
                        db.session.commit()
                session['index']+= 1

                if session['index'] < len(questions):
                    return render_template('flashcards.html', question=questions[session['index']], feedback=feedback, show_answer= False, skipped_questions=None)
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
                return render_template('flashcards.html', question=q_data, feedback=feedback, show_answer=False, skipped_questions=None)

