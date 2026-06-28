# Adaptive Learning Platform Final Project

This project is a full-stack adaptive learning platform built with Flask, HTML/CSS, JavaScript, FER-2013 based emotion analysis, and Gemini-assisted live learning support.

The system supports:

- Student, teacher, and admin authentication
- Teacher course publishing and course deletion
- Student live lecture page with realtime emotion monitoring
- Gemini-generated simple explanation when the student looks confused
- Exam and result tracking
- FER-2013 training/test workflow for the emotion model
- MySQL support for platform data storage

## Project Domain

Adaptive learning and educational technology.

The core project goal is:

Detect the student emotion during a live lecture session and automatically generate a simpler explanation, better teaching action, and support message when the student becomes confused, stressed, or bored.

## Tech Stack

- Backend: Flask
- Frontend: Jinja templates, HTML, CSS, JavaScript
- Database: MySQL
- Emotion model: FER-2013 NumPy/OpenCV MLP model
- AI guidance: Gemini API

## Main Features

### Student

- Login and access adaptive dashboard
- Start mood-based learning
- Open live lecture session
- Enable camera for realtime emotion analysis
- Get generated explanation for the current lecture topic
- Take exams and review results

### Teacher

- Add courses with title, subject, category, order, PDF, and lecture URL
- Delete owned courses
- Review student support alerts
- Monitor learning analytics

### Admin

- View users, teachers, students, and courses
- Monitor exams and support feed
- Check database backend status
- View FER-2013 model metrics

## Project Structure

```text
app.py
auth_utils.py
platform_db.py
route_auth.py
route_course.py
route_dashboard.py
route_exam.py
route_learning.py
learning_logic.py
emotion_model.py
gemini_client.py
train_fer2013.py
mysql_setup.sql
templates/
static/
data/
```

## Database Integration

The final project uses MySQL as the application database.

Data stored in MySQL:

- users
- courses
- emotions
- exam_attempts
- session_insights
- training_runs

## MySQL Setup

1. Create the schema using `mysql_setup.sql`
2. Configure environment variables
3. Start the Flask app

Example PowerShell setup:

```powershell
$env:DB_BACKEND="mysql"
$env:MYSQL_HOST="localhost"
$env:MYSQL_PORT="3306"
$env:MYSQL_USER="root"
$env:MYSQL_PASSWORD="your_password"
$env:MYSQL_DATABASE="adaptive_learning_platform"
$env:GEMINI_API_KEY="your_gemini_api_key"
```

## Installation

Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run The Project

```powershell
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Demo Accounts

- Student: `student@example.com` / `student123`
- Teacher: `teacher@example.com` / `teacher123`
- Admin: `admin@example.com` / `admin123`

## FER-2013 Training And Testing

This project includes a train/test workflow in `train_fer2013.py`.

Expected dataset format inside the zip:

```text
train/
  angry/
  disgust/
  fear/
  happy/
  neutral/
  sad/
  surprise/
test/
  angry/
  disgust/
  fear/
  happy/
  neutral/
  sad/
  surprise/
```

Run training:

```powershell
python train_fer2013.py --zip-path "C:\path\to\fer2013.zip" --epochs 5 --batch-size 128 --learning-rate 0.05
```

Generated files:

- `data/models/fer2013_emotion_mlp.npz`
- `data/models/fer2013_training_history.json`
- `data/models/fer2013_confusion_matrix.csv`

The latest training metrics are shown on the admin dashboard.

## Gemini Integration

Gemini is used in the live lecture page to generate:

- teacher guidance
- student-friendly explanation
- intervention summary
- topic to re-explain
- reason for intervention

The code for this integration is in:

- `gemini_client.py`
- `learning_logic.py`
- `route_learning.py`
- `templates/learn_interactive.html`

## Important Notes

- If `GEMINI_API_KEY` is not set, the project falls back to rule-based guidance.
- If a trained FER-2013 model is not available, the app falls back to alternative emotion analysis flow.
- Teacher delete-course actions also remove related exam attempts and session insights for that course.
- Teacher, student, and admin accounts are stored in the MySQL `users` table with role-based access.

## Final Project Deliverables Added

- MySQL-backed app database support
- Teacher add and delete course flow
- Improved live lecture student page
- FER-2013 training script
- MySQL schema file
- Clean project README

## Limitation In This Environment

The current machine session does not have a working Python interpreter available in the terminal, so I could not execute a real end-to-end run, retrain the model live, or verify the Flask server from this shell.

The source code and integration points have been prepared so you can run them on a Python-enabled environment immediately.
