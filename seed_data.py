from __future__ import annotations

from werkzeug.security import generate_password_hash


STUDENT_NAMES = [
    "Prashant Waje",
    "Pooja Shirsat",
    "Akash Jadhav",
    "Sneha Patil",
    "Rahul Pawar",
    "Priya More",
    "Sanket Kadam",
    "Neha Deshmukh",
    "Rohit Salunkhe",
    "Aarti Chavan",
    "Sagar Gaikwad",
    "Komal Shinde",
    "Nikhil Bhosale",
    "Vaishnavi Mane",
    "Vishal Lokhande",
    "Anjali Kulkarni",
    "Kiran Rathod",
    "Sayali Gawade",
    "Amol Kumbhar",
    "Rutuja Nikam",
    "Omkar Mahajan",
    "Mansi Borade",
    "Yogesh Mali",
    "Sonal Kale",
    "Ganesh Jagtap",
    "Kajal Suryawanshi",
    "Ajay Dhumal",
    "Megha Borse",
    "Harshal Joshi",
    "Tejaswini Ghorpade",
]

INDIAN_TEACHER_NAMES = [
    "Meera Deshpande",
    "Rajesh Patil",
    "Anita Joshi",
    "Vikram Shah",
    "Sunita Pawar",
    "Mahesh Shinde",
    "Kavita More",
    "Nitin Jadhav",
    "Deepa Chavan",
    "Prakash Bhosale",
]


def _student_email(name: str) -> str:
    return f"{name.lower().replace(' ', '.')}@demo.com"


def _gmail(name: str) -> str:
    return f"{name.lower().replace(' ', '.')}@gmail.com"


def _teacher_email(name: str, index: int) -> str:
    return f"{name.lower().replace(' ', '.')}{index:02d}@gmail.com"


def _fallback_email(email: str, user_id: int) -> str:
    local, domain = email.split("@", 1)
    return f"{local}.{user_id}@{domain}"


def _row_value(row, key_or_index):
    if isinstance(row, dict):
        return row[key_or_index]
    return row[key_or_index]


def seed_db(db) -> None:
    user_count_row = db.execute("SELECT COUNT(*) FROM users").fetchone()
    user_count = _row_value(user_count_row, 0)
    if user_count == 0:
        demo_users = [
            ("Rohan Patil", "rohan.patil@demo.com", "student123", "9000000001", "student"),
            ("Sanjay Kulkarni", "sanjay.kulkarni@gmail.com", "teacher123", "9000000002", "teacher"),
            ("Aniket Deshmukh", "aniket.deshmukh@gmail.com", "admin123", "9000000003", "admin"),
        ]
        db.executemany(
            """
            INSERT INTO users (username, email, password_hash, mobile, role)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (name, email, generate_password_hash(password), mobile, role)
                for name, email, password, mobile, role in demo_users
            ],
        )
    default_student = db.execute(
        "SELECT id FROM users WHERE email IN (?, ?) AND role = 'student' ORDER BY id LIMIT 1",
        ("student@example.com", "rohan.patil@demo.com"),
    ).fetchone()
    if default_student:
        db.execute(
            "UPDATE users SET username = ?, email = ?, mobile = ? WHERE id = ?",
            ("Rohan Patil", "rohan.patil@demo.com", "9000000001", _row_value(default_student, 0)),
        )
    default_teacher = db.execute(
        "SELECT id FROM users WHERE email IN (?, ?) AND role = 'teacher' ORDER BY id LIMIT 1",
        ("teacher@example.com", "sanjay.kulkarni@gmail.com"),
    ).fetchone()
    if default_teacher:
        db.execute(
            "UPDATE users SET username = ?, email = ?, mobile = ? WHERE id = ?",
            ("Sanjay Kulkarni", "sanjay.kulkarni@gmail.com", "9000000002", _row_value(default_teacher, 0)),
        )
    default_admin = db.execute(
        "SELECT id FROM users WHERE email IN (?, ?) AND role = 'admin' ORDER BY id LIMIT 1",
        ("admin@example.com", "aniket.deshmukh@gmail.com"),
    ).fetchone()
    if default_admin:
        db.execute(
            "UPDATE users SET username = ?, email = ?, mobile = ? WHERE id = ?",
            ("Aniket Deshmukh", "aniket.deshmukh@gmail.com", "9000000003", _row_value(default_admin, 0)),
        )

    bulk_demo_users = []
    for index, student_name in enumerate(INDIAN_STUDENT_NAMES, start=1):
        bulk_demo_users.append(
            (
                student_name,
                _student_email(student_name),
                f"student{index:02d}",
                f"90100000{index:02d}",
                "student",
                f"student{index:02d}@demo.com",
            )
        )
    for index, teacher_name in enumerate(INDIAN_TEACHER_NAMES, start=1):
        bulk_demo_users.append(
            (
                teacher_name,
                _teacher_email(teacher_name, index),
                f"teacher{index:02d}",
                f"90200000{index:02d}",
                "teacher",
                f"teacher{index:02d}@demo.com",
            )
        )
    for row in bulk_demo_users:
        name, email, password, mobile, role = row[:5]
        old_email = row[5] if len(row) > 5 else email
        old_user = db.execute("SELECT id FROM users WHERE email = ?", (old_email,)).fetchone()
        target_user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        existing_user = old_user or target_user
        if not existing_user:
            db.execute(
                """
                INSERT INTO users (username, email, password_hash, mobile, role)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, email, generate_password_hash(password), mobile, role),
            )
        else:
            target_email = email
            if old_user and target_user and _row_value(old_user, 0) != _row_value(target_user, 0):
                target_email = _fallback_email(email, _row_value(old_user, 0))
            db.execute(
                "UPDATE users SET username = ?, email = ?, mobile = ? WHERE id = ?",
                (name, target_email, mobile, _row_value(existing_user, 0)),
            )

    course_count_row = db.execute("SELECT COUNT(*) FROM courses").fetchone()
    course_count = _row_value(course_count_row, 0)
    if course_count == 0:
        teacher_row = db.execute(
            "SELECT id FROM users WHERE role = 'teacher' ORDER BY id LIMIT 1"
        ).fetchone()
        teacher_id = _row_value(teacher_row, 0)
        demo_courses = [
            (
                "IT Fundamentals",
                "it",
                "Information Technology",
                1,
                "Learn operating systems, networking basics, hardware-software flow, and IT support practices.",
                None,
                "https://www.youtube.com/watch?v=qwN8wyU-DZY",
                teacher_id,
            ),
            (
                "Digital Literacy Essentials",
                "non-it",
                "Digital Literacy",
                1,
                "Understand email, online tools, internet safety, and digital productivity in daily work.",
                None,
                "https://www.youtube.com/watch?v=O5nskjZ_GoI",
                teacher_id,
            ),
            (
                "Data Science Foundations",
                "datascience",
                "Data Science",
                1,
                "Learn data lifecycle, analysis basics, visualization, and interpretation for decision-making.",
                None,
                "https://www.youtube.com/watch?v=ua-CiDNNj30",
                teacher_id,
            ),
            (
                "Professional Soft Skills",
                "softskills",
                "Soft Skills",
                1,
                "Strengthen teamwork, adaptability, ownership, and workplace etiquette.",
                None,
                "https://www.youtube.com/watch?v=KQw0h2s1R2I",
                teacher_id,
            ),
        ]
        db.executemany(
            """
            INSERT INTO courses
            (title, category, subject, course_index, description, pdf_file, youtube_url, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            demo_courses,
        )

    demo_students = db.execute(
        """
        SELECT id, email
        FROM users
        WHERE role = 'student'
          AND email IN ({})
        ORDER BY email
        """.format(",".join(["?"] * len(INDIAN_STUDENT_NAMES))),
        [_student_email(name) for name in INDIAN_STUDENT_NAMES],
    ).fetchall()
    demo_courses_for_activity = db.execute(
        """
        SELECT id, category
        FROM courses
        ORDER BY category, course_index, id
        """
    ).fetchall()
    if demo_students and demo_courses_for_activity:
        for student_index, student in enumerate(demo_students, start=1):
            student_id = _row_value(student, 0)
            course_span = 2 + (student_index % 3)
            for offset in range(course_span):
                course = demo_courses_for_activity[(student_index + offset) % len(demo_courses_for_activity)]
                course_id = _row_value(course, 0)
                category = _row_value(course, 1)
                db.execute(
                    """
                    INSERT INTO course_subscriptions (user_id, course_id, price)
                    VALUES (?, ?, 799)
                    ON DUPLICATE KEY UPDATE price = VALUES(price)
                    """,
                    (student_id, course_id),
                )
                attempt_exists = db.execute(
                    "SELECT id FROM exam_attempts WHERE user_id = ? AND course_id = ? LIMIT 1",
                    (student_id, course_id),
                ).fetchone()
                if not attempt_exists:
                    total_questions = 20
                    score = 9 + ((student_index + offset * 3) % 11)
                    db.execute(
                        """
                        INSERT INTO exam_attempts (user_id, course_id, category, score, total_questions)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (student_id, course_id, category, score, total_questions),
                    )

    db.commit()
