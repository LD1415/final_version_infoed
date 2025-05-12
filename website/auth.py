 
from flask import Blueprint, render_template, request, flash, redirect, url_for
from .models import User
from werkzeug.security import generate_password_hash, check_password_hash
from . import db
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash
from argon2 import PasswordHasher
from website import db
from website.models import User
from flask_babel import _, Babel

 
auth = Blueprint('auth', __name__)
 
 
@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
 
        user = User.query.filter_by(email=email).first()
        if user:
            print(f"Stored hash: {user.password}")
            # Argon2 verif parola
            ph = PasswordHasher()
            try:
                # parola hash, no pb
                ph.verify(user.password, password)
                flash('Logged in successfully!', category='success')
                login_user(user, remember=True)
                return redirect(url_for('views.home'))
            except:
                flash('Incorrect password, try again.', category='error')
        else:
            flash('Email does not exist.', category='error')
 
    #return render_template("login.html", user=current_user)
    return render_template("login.html")

 
 
@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
 
from argon2 import PasswordHasher
 
@auth.route("/sign-up", methods=["GET", "POST"])
def sign_up():
    if request.method == "POST":
        email = request.form.get("email")
        first_name = request.form.get("first_name")
        password1 = request.form.get("password1")
        password2 = request.form.get("password2")
 
        if password1 != password2:
            flash("Passwords don't match!", category="error")
        else:
            # argon2 in hash parola
            ph = PasswordHasher()
            hashed_password = ph.hash(password1)
 
            new_user = User(email=email, first_name=first_name, password=hashed_password)
 
            db.session.add(new_user)
            db.session.commit()
            flash("Account created successfully!", category="success")
            return redirect(url_for("auth.login"))
 
    return render_template("sign_up.html")


    