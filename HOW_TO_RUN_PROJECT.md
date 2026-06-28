# How To Run This Project

## Project Type

This is a Flask-based adaptive learning platform with:

- Student, teacher, and admin login
- Course management
- Mood-based course suggestions
- Live session emotion support
- Exam and result pages

## Requirements

- Python 3.10 or newer
- Windows PowerShell or Command Prompt

## Install Steps

Open a terminal inside this folder and run:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Start The App

Set MySQL and Gemini environment variables first:

```powershell
$env:MYSQL_HOST="localhost"
$env:MYSQL_PORT="3306"
$env:MYSQL_USER="root"
$env:MYSQL_PASSWORD="your_password"
$env:MYSQL_DATABASE="adaptive_learning_platform"
$env:GEMINI_API_KEY="your_api_key_here"
```

Run:

```powershell
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

## Demo Login Accounts

- Student: `student@example.com` / `student123`
- Teacher: `teacher@example.com` / `teacher123`
- Admin: `admin@example.com` / `admin123`

## Notes

- The project uses MySQL for users, teacher data, student data, admin data, courses, exam attempts, moods, and live session insights.
- The app also includes a trained emotion model in `data/models/`, so it can run without retraining.
- If Gemini is not configured, the project still works using rule-based guidance.

## Included Important Folders

- `templates/` for HTML pages
- `static/` for CSS and uploaded PDFs
- `data/` for trained model files

## Troubleshooting

- If `cv2` fails to install, upgrade pip first:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

- If port 5000 is busy, stop the other Flask app using that port and run again.

- If the camera prompt appears during the live learning page, allow camera access in the browser.

- Make sure the MySQL server is running before starting the Flask app.
