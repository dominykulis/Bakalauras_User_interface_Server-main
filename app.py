from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, current_app, g
import config
from config import ADMIN_USERNAME, ADMIN_PASSWORD
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from scp import SCPClient
import os
import paramiko
import shutil
import sqlite3
import re



app = Flask(__name__)


app.secret_key = 'your_secret_key_here'
login_manager = LoginManager()
login_manager.init_app(app)

app.config['UPLOAD_FOLDER'] = 'static/uploads'
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif'}





DATABASE = 'instance/raspi.db'


conn = sqlite3.connect(DATABASE)
c = conn.cursor()

# Create table
c.execute('''CREATE TABLE IF NOT EXISTS raspi
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              hostname TEXT NOT NULL,
              username TEXT NOT NULL,
              password TEXT NOT NULL);''')

# Save (commit) the changes
conn.commit()

# Close the connection
conn.close()

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

class User(UserMixin):
    def __init__(self, username, password):
        self.id = username  # Set the ID of the user
        self.username = username
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    @staticmethod
    def get(user_id):
        # Implement the retrieval of a user based on the user ID if needed
        pass


@login_manager.user_loader
def load_user(user_id):
    if user_id == ADMIN_USERNAME:
        return User(user_id, ADMIN_PASSWORD)
    return None

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD:
            user = User(username, password)
            login_user(user)  # Log in the user
            return redirect(url_for('index'))
        else:
            # Invalid credentials, show error message
            flash('Invalid username or password', 'error')
            return redirect(url_for('login'))

    # Render the login form template
    return render_template("login.html")

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

@app.route('/users', methods=['GET', 'POST'])
@login_required
def add_user():
    if request.method == 'POST':
        name = request.form['username']

        # Create a new directory with the user's name in the UPLOADS folder
        upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], name)
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
            flash(f'User {name} created successfully!', 'success')

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
        file_count = 1
        
        for file in files:

            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                
                # Change filename to directory name and append a number if the filename already exists
                if not name:
                    flash('Please select a person\'s name', 'error')
                    return redirect(request.url)
                
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], name, filename)
                if not os.path.exists(filepath):
                    file_count = 1
                    filename = f"{name}#{file_count}.{filename.rsplit('.', 1)[1]}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], name, filename)
                    while os.path.exists(filepath):
                        file_count += 1
                        filename = f"{name}#{file_count}.{filename.rsplit('.', 1)[1]}"
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], name, filename)
                
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                file.save(filepath)
                filenames.append(filename)

            elif file:
                return 'Invalid file type. Only JPG, JPEG, PNG, and GIF files are allowed. <a href="' + url_for('upload_file') + '">Try again</a>.'
        
        if filenames:
            flash(f'Files {", ".join(filenames)} uploaded successfully!', 'success')
            return redirect(request.url)
    
    # Get a list of existing directories to populate the dropdown menu
    directories = [name for name in os.listdir(app.config['UPLOAD_FOLDER']) if os.path.isdir(os.path.join(app.config['UPLOAD_FOLDER'], name))]
    
    return render_template('upload.html', directories=directories)

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

@app.route('/delete_image/<name>/<filename>', methods=['POST'])
@login_required
def delete_image(name, filename):
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], name, filename))
        flash('Image deleted successfully.', 'success')

    except Exception as e:
        app.logger.error(f"Error deleting image {filename}: {str(e)}")
        flash('Error deleting image.', 'error')

    return redirect(url_for('gallery'))

@app.route('/create_pi', methods=['GET', 'POST'])
@login_required
def creation():
    if request.method == 'POST':
        hostname = request.form['hostname']
        username = request.form['username']
        password = request.form['password']
        
        # Your logic here
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        # insert sample data
        ip_regex = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
        if not re.match(ip_regex, hostname):
            flash('Invalid IP address format for hostname', 'error')
            return redirect(url_for('creation'))
        
        c.execute("INSERT INTO raspi (hostname, username, password) VALUES (?, ?, ?)", (hostname, username, password))
        conn.commit()
        conn.close()
        flash('Lock added Successfully', 'error')
    
    return render_template('create_pi.html')

@app.route('/delete_record/<int:id>', methods=['POST'])
@login_required
def delete_record(id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("DELETE FROM raspi WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash("Record deleted successfully.", "success")
    return redirect(url_for('database'))

@app.route('/delete', methods=['GET', 'POST'])
@login_required
def delete_directory():
    # Get a list of all existing directories in the UPLOADS folder
    existing_directories = [d for d in os.listdir(app.config['UPLOAD_FOLDER']) if os.path.isdir(os.path.join(app.config['UPLOAD_FOLDER'], d))]

    if request.method == 'POST':
        # Get the name of the directory to delete from the form
        directory_name = request.form['directory_name']
        
        if directory_name in existing_directories:
            # Remove the directory and all its contents
            shutil.rmtree(os.path.join(app.config['UPLOAD_FOLDER'], directory_name))
            flash(f"Directory '{directory_name}' and all its contents have been deleted.", 'success')
        else:
            flash(f"Directory '{directory_name}' does not exist.", 'error')
        return redirect(url_for('delete_directory'))

    return render_template('delete.html', directories=existing_directories)

@app.route('/run-command', methods=['GET', 'POST'])
@login_required
def run_command():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    if request.method == 'POST':
        # Get the selected directory from the form
        selected_host = request.form['host']

        # Get the selected directory from the form
        selected_dir = request.form['directory']

        # Build the source and destination paths
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], selected_dir)
        destination_path = '/home/pi/software/Face-Recognition/Users'

        try:
            # Connect to the selected host from the dropdown menu
            conn = sqlite3.connect(DATABASE)
            c = conn.cursor()
            c.execute("SELECT hostname, username, password FROM raspi WHERE hostname=?", (selected_host,))
            host_data = c.fetchone()
            if host_data is None:
                flash(f'Invalid host selected!', 'error')
                return redirect(url_for('run_command'))
            else:
                hostname, username, password = host_data
                ssh.connect(hostname, username=username, password=password)
        
            # Copy the directory to the Raspberry Pi using SCP
            with SCPClient(ssh.get_transport()) as scp:
                scp.put(source_path, destination_path, recursive=True)

            # Run the startup script on the Raspberry Pi for every file in the directory
            for file_name in os.listdir(source_path):
                if file_name.endswith('.jpg'):
                    command = f'Users/{selected_dir}/{file_name}'
                    stdin, stdout, stderr = ssh.exec_command("cd /home/pi/software/Face-Recognition && ./FaceRecognition " + str(command))
                    output = stdout.read().decode('utf-8')
                    error = stderr.read().decode('utf-8')
                    
                    if error:
                        flash(f'Error running script to initialize file named:{file_name} The error is: {error}', 'error')
                    else:
                        flash(f'Script {file_name} executed successfully: {output}', 'success')

        except Exception as e:
            flash(f'Error: {str(e)}', 'error')

        finally:
            # Close the database connection and SSH connection
            conn.close()
            ssh.close()

    # Get a list of existing hosts in the raspi table
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT hostname, username FROM raspi")
    hostnames = c.fetchall()
    conn.close()
    directories = [d for d in os.listdir(app.config['UPLOAD_FOLDER']) if os.path.isdir(os.path.join(app.config['UPLOAD_FOLDER'], d))]
    return render_template('run_command.html', hostnames=hostnames, directories=directories)

@app.route('/database')
def database():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # select all credentials
    c.execute("SELECT * FROM raspi")
    credentials = c.fetchall()

    # close connection
    conn.close()

    return render_template('database.html', credentials=credentials)

if __name__ == '__main__':
    app.run(debug=True)