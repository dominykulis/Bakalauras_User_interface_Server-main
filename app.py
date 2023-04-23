from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///example.db'  # Replace with your preferred database URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)



app.secret_key = 'your_secret_key_here'
login_manager = LoginManager()
login_manager.init_app(app)

app.config['UPLOAD_FOLDER'] = 'static/uploads'
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif'}


USERS = {
    1: {'username': 'admin', 'password': 'admin'}
}

class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)

with app.app_context():
    db.create_all()


class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password, password)
    
    @staticmethod
    def get(user_id):
        user = USERS.get(user_id)
        if not user:
            return None
        return User(user_id, user['username'], user['password'])

@login_manager.user_loader
def load_user(user_id):
    return User.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = None

        for user_id, user_data in USERS.items():
            if user_data['username'] == username:
                user = User(user_id, user_data['username'], user_data['password'])
                break

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/profile')
def profile():
    return render_template('profile.html', user=current_user)
    
@app.route('/index')
@login_required
def index():
    username = current_user.username
    return render_template('index.html', username=username)

# @app.route('/create-user', methods=['GET', 'POST'])
# def create_user():
#     if request.method == 'POST':
#         # Get the form data
#         username = request.form['username']
#         password = request.form['password']
#         email = request.form['email']

#         # Process the form data (e.g. add new user to a database)
#         # ...

#         # Redirect to another page
#         return redirect(url_for('index'))

#     # Render the form template
#     return render_template('create_user.html')

@app.route('/users', methods=['GET', 'POST'])
@login_required
def add_user():
    if request.method == 'POST':
        name = request.form['username']
        email = request.form['email']

        new_user = Users(name=name, email=email)
        db.session.add(new_user)
        db.session.commit()

        return jsonify({'message': 'User added successfully.'})

    return render_template('create_user.html')


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_file():
    if request.method == 'POST':
        # Get the person's name from the form
        name = request.form.get('name')

        if 'files[]' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
        
        files = request.files.getlist('files[]')
        if not files:
            flash('No selected file', 'error')
            return redirect(request.url)
        
        filenames = []
        
        for file in files:

            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], name, filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                file.save(filepath)
                filenames.append(filename)

            elif file:
                return 'Invalid file type. Only JPG, JPEG, PNG, and GIF files are allowed. <a href="' + url_for('upload_file') + '">Try again</a>.'
        
        if filenames:
            flash(f'Files {", ".join(filenames)} uploaded successfully!', 'success')
            return redirect(request.url)
    
    return render_template('upload.html')

@app.route('/gallery')
@login_required
def gallery():
    subdirectories = next(os.walk(app.config['UPLOAD_FOLDER']))[1]
    image_names = {}
    for subdirectory in subdirectories:
        image_files = []
        for filename in os.listdir(os.path.join(app.config['UPLOAD_FOLDER'], subdirectory)):
            if filename.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                image_files.append(filename)

        if image_files:
            image_names[subdirectory] = image_files

    return render_template("gallery.html", image_names=image_names,os=os,app=app)

@app.route('/delete_image/<filename>', methods=['POST'])
@login_required
def delete_image(filename):

    try:
        os.remove(os.path.join('static/uploads', filename))
        return redirect(url_for('gallery'))
    
    except:
        return "Error deleting file"
    
if __name__ == '__main__':
    app.run(debug=True)