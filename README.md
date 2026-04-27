# School Management System (Flask + SQLite)

A simple School Management web application for primary/secondary schools.

## Features

- Login (Admin / Teacher) with hashed passwords
- Student CRUD + search by Roll Number
- Attendance (Present/Absent) with date and history per student
- Marks per subject with simple result view
- Role-based access (Admin can manage teachers; both roles can manage students/attendance/marks)
- Responsive sidebar dashboard (mobile + desktop)

## Tech

- Backend: Python Flask
- Database: SQLite (auto-created as `school.db`)
- ORM: Flask-SQLAlchemy
- Auth: Flask-Login + Werkzeug password hashing
- Frontend: HTML, CSS, JavaScript (Jinja templates)

## Default accounts

| Role    | Username  | Password    |
|---------|-----------|-------------|
| Admin   | admin     | admin123    |
| Teacher | teacher   | teacher123  |

## Run locally

```bash
# 1. Install Python 3.11+ then:
pip install flask flask-sqlalchemy flask-login werkzeug

# 2. Run
cd flask-app
python app.py

# 3. Open http://localhost:5000
```

The first run creates `school.db` automatically and seeds the two default users.

## Database tables

- `users` — id, username, full_name, password_hash, role, created_at
- `students` — id, name, class_name, roll_number, dob, parent_name, created_at
- `attendance` — id, student_id, date, status (unique per student/date)
- `marks` — id, student_id, subject, score, max_score, created_at

<!-- ## Project structure

```
flask-app/
├── app.py              # Flask app, models, routes
├── school.db           # SQLite (auto-created)
├── templates/          # Jinja2 HTML templates
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── students.html
│   ├── student_form.html
│   ├── student_detail.html
│   ├── attendance.html
│   ├── marks.html
│   ├── teachers.html
│   ├── teacher_form.html
│   └── error.html
└── static/
    ├── style.css
    └── app.js
``` -->
"# School_Management" 
