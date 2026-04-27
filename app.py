import os
from datetime import datetime, date
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, abort, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text

basedir = os.path.abspath(os.path.dirname(__file__))

CLASS_OPTIONS = [
    "1st Class", "2nd Class", "3rd Class", "4th Class", "5th Class",
    "6th Class", "7th Class", "8th Class", "9th Class", "10th Class",
]
SECTION_OPTIONS = ["A", "B", "C", "D"]

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SESSION_SECRET", "dev-secret-key-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "school.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."


# ---------------- Models ----------------
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' or 'teacher'
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(250), nullable=True)
    subject_assignment = db.Column(db.String(250), nullable=True)  # free-text e.g. "Maths, Science"
    last_login = db.Column(db.DateTime, nullable=True)
    assigned_class = db.Column(db.String(40), nullable=True)
    assigned_section = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    class_name = db.Column(db.String(40), nullable=False)
    section = db.Column(db.String(20), nullable=True)
    roll_number = db.Column(db.String(40), unique=True, nullable=False)
    dob = db.Column(db.Date, nullable=False)
    parent_name = db.Column(db.String(120), nullable=False)
    parent_phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(250), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    attendance = db.relationship("Attendance", backref="student", cascade="all, delete-orphan")
    marks = db.relationship("Mark", backref="student", cascade="all, delete-orphan")
    fees = db.relationship("Fee", backref="student", cascade="all, delete-orphan")


class Attendance(db.Model):
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(10), nullable=False)
    __table_args__ = (db.UniqueConstraint("student_id", "date", name="uq_student_date"),)


class Mark(db.Model):
    __tablename__ = "marks"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    exam = db.Column(db.String(20), nullable=False)  # e.g. FA1, FA2, SA1, SA2
    subject = db.Column(db.String(80), nullable=False)
    score = db.Column(db.Float, nullable=False)
    max_score = db.Column(db.Float, nullable=False, default=100.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Fee(db.Model):
    __tablename__ = "fees"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)  # e.g. "Term 1 Tuition"
    amount = db.Column(db.Float, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    mode = db.Column(db.String(30), nullable=True)  # Cash, UPI, Card, Bank Transfer, Cheque
    status = db.Column(db.String(10), nullable=False, default="Unpaid")  # 'Paid' or 'Unpaid'
    paid_on = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Subject(db.Model):
    __tablename__ = "subjects"
    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.String(40), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    __table_args__ = (db.UniqueConstraint("class_name", "name", name="uq_class_subject"),)


class Holiday(db.Model):
    __tablename__ = "holidays"
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    reason = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# AttendanceRequest: raised when teacher wants to mark past date OR re-edit
class AttendanceRequest(db.Model):
    __tablename__ = "attendance_requests"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    request_date = db.Column(db.Date, nullable=False)      # which attendance date
    reason = db.Column(db.String(250), nullable=False)
    request_type = db.Column(db.String(20), nullable=False)  # 'past_date' or 'edit'
    status = db.Column(db.String(20), nullable=False, default="Pending")  # Pending/Approved/Rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    teacher = db.relationship("User", foreign_keys=[teacher_id])


# AttendanceAudit: every save of attendance records who/when
class AttendanceAudit(db.Model):
    __tablename__ = "attendance_audit"
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    attendance_date = db.Column(db.Date, nullable=False)
    action = db.Column(db.String(20), nullable=False)   # 'mark' or 'edit'
    edit_count = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_by_request = db.Column(db.Integer, db.ForeignKey("attendance_requests.id"), nullable=True)
    teacher = db.relationship("User", foreign_keys=[teacher_id])



# MarksRequest: raised when user wants to edit already-entered marks
class MarksRequest(db.Model):
    __tablename__ = "marks_requests"
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    class_name = db.Column(db.String(40), nullable=False)
    exam = db.Column(db.String(20), nullable=False)
    subject = db.Column(db.String(80), nullable=False)
    reason = db.Column(db.String(250), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="Pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    requester = db.relationship("User", foreign_keys=[requester_id])


# MarksAudit: every bulk-save of marks records who/when
class MarksAudit(db.Model):
    __tablename__ = "marks_audit"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    class_name = db.Column(db.String(40), nullable=False)
    exam = db.Column(db.String(20), nullable=False)
    subject = db.Column(db.String(80), nullable=False)
    action = db.Column(db.String(20), nullable=False)  # 'enter' or 'edit'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_by_request = db.Column(db.Integer, db.ForeignKey("marks_requests.id"), nullable=True)
    user = db.relationship("User", foreign_keys=[user_id])


PAYMENT_MODES = ["Cash", "UPI", "Card", "Bank Transfer", "Cheque"]
SCHOOL_CUTOFF_HOUR = 18  # 6 PM — attendance cannot be marked after this hour
EXAM_TYPES = ["FA1", "FA2", "FA3", "FA4", "SA1", "SA2", "Unit Test", "Half Yearly", "Annual"]


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------- Helpers ----------------
def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


@app.context_processor
def inject_globals():
    att_pending = 0
    marks_pending = 0
    try:
        from flask_login import current_user as cu
        if cu.is_authenticated and cu.role == "admin":
            att_pending = AttendanceRequest.query.filter_by(status="Pending").count()
            marks_pending = MarksRequest.query.filter_by(status="Pending").count()
    except Exception:
        pass
    return {
        "class_options": CLASS_OPTIONS,
        "section_options": SECTION_OPTIONS,
        "payment_modes": PAYMENT_MODES,
        "nav_pending_requests": att_pending,
        "nav_marks_pending": marks_pending,
    }


@app.before_request
def force_password_change():
    """Block all actions until first-login password change is done."""
    if not current_user.is_authenticated:
        return
    if not getattr(current_user, "must_change_password", False):
        return
    # Allow GET dashboard so the modal can render, plus the change-password POST and logout.
    allowed_get = {"dashboard", "change_password", "static"}
    if request.method == "GET" and request.endpoint in allowed_get:
        return
    if request.endpoint in {"change_password", "logout"}:
        return
    return redirect(url_for("dashboard"))


# ---------------- Auth ----------------
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            if user.must_change_password:
                flash("Please set a new password to continue.", "info")
                return redirect(url_for("change_password"))
            flash(f"Welcome, {user.full_name}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/profile")
@login_required
def my_profile():
    return render_template("my_profile.html")


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    forced = current_user.must_change_password
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        if not forced and not current_user.check_password(current_pw):
            flash("Current password is incorrect.", "danger")
        elif len(new_pw) < 6:
            flash("New password must be at least 6 characters.", "danger")
        elif new_pw != confirm:
            flash("New passwords do not match.", "danger")
        else:
            current_user.set_password(new_pw)
            current_user.must_change_password = False
            db.session.commit()
            flash("Password updated successfully.", "success")
            return redirect(url_for("dashboard"))
    return render_template("change_password.html", forced=forced)


# ---------------- Dashboard ----------------
@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "teacher" and current_user.assigned_class:
        # Get only assigned class student IDs
        sq = Student.query.filter_by(class_name=current_user.assigned_class)
        if current_user.assigned_section:
            sq = sq.filter_by(section=current_user.assigned_section)
        class_student_ids = [s.id for s in sq.all()]
        stats = {
            "students": len(class_student_ids),
            "teachers": User.query.filter_by(role="teacher").count(),
            "today_present": Attendance.query.filter(
                Attendance.date == date.today(),
                Attendance.status == "Present",
                Attendance.student_id.in_(class_student_ids)
            ).count(),
            "today_absent": Attendance.query.filter(
                Attendance.date == date.today(),
                Attendance.status == "Absent",
                Attendance.student_id.in_(class_student_ids)
            ).count(),
        }
    else:
        stats = {
            "students": Student.query.count(),
            "teachers": User.query.filter_by(role="teacher").count(),
            "today_present": Attendance.query.filter_by(date=date.today(), status="Present").count(),
            "today_absent": Attendance.query.filter_by(date=date.today(), status="Absent").count(),
        }
    fee_stats = None
    if current_user.role == "admin":
        total = db.session.query(db.func.coalesce(db.func.sum(Fee.amount), 0)).scalar() or 0
        paid = db.session.query(db.func.coalesce(db.func.sum(Fee.amount), 0)).filter(Fee.status == "Paid").scalar() or 0
        unpaid = db.session.query(db.func.coalesce(db.func.sum(Fee.amount), 0)).filter(Fee.status == "Unpaid").scalar() or 0
        fee_stats = {"total": total, "paid": paid, "unpaid": unpaid}
    # Recent activity — last 5 events across students, teachers, fees
    recent_activity = []
    recent_students = Student.query.order_by(Student.created_at.desc()).limit(3).all()
    for s in recent_students:
        recent_activity.append({
            "icon": "👨‍🎓",
            "text": f"Student <strong>{s.name}</strong> was added",
            "time": s.created_at.strftime("%d %b %Y, %I:%M %p"),
            "_ts": s.created_at,
        })
    recent_teachers = User.query.filter_by(role="teacher").order_by(User.created_at.desc()).limit(2).all()
    for t in recent_teachers:
        recent_activity.append({
            "icon": "👨‍🏫",
            "text": f"Teacher <strong>{t.full_name}</strong> was added",
            "time": t.created_at.strftime("%d %b %Y, %I:%M %p"),
            "_ts": t.created_at,
        })
    recent_fees = Fee.query.order_by(Fee.created_at.desc()).limit(2).all()
    for f in recent_fees:
        student = db.session.get(Student, f.student_id)
        recent_activity.append({
            "icon": "💰",
            "text": f"Fee of <strong>₹{f.amount:.2f}</strong> added for <strong>{student.name if student else 'Unknown'}</strong>",
            "time": f.created_at.strftime("%d %b %Y, %I:%M %p"),
            "_ts": f.created_at,
        })
    # Sort all by most recent using raw datetime
    recent_activity = sorted(recent_activity, key=lambda x: x["_ts"], reverse=True)[:5]

    today_date = date.today().strftime("%A, %d %B %Y")

    # Today holiday/sunday status
    is_sunday = date.today().weekday() == 6
    holiday = Holiday.query.filter_by(date=date.today()).first()

    # Teacher specific stats
    teacher_stats = None
    if current_user.role == "teacher":
        if current_user.assigned_class:
            q = Student.query.filter_by(class_name=current_user.assigned_class)
            if current_user.assigned_section:
                q = q.filter_by(section=current_user.assigned_section)
            total_students = q.count()
            student_ids = [s.id for s in q.all()]
            today_marked = Attendance.query.filter(
                Attendance.date == date.today(),
                Attendance.student_id.in_(student_ids)
            ).count()
            not_marked_today = total_students - today_marked
            from datetime import timedelta
            week_start = date.today() - timedelta(days=date.today().weekday())
            marks_this_week = Mark.query.filter(
                Mark.created_at >= week_start,
                Mark.student_id.in_(student_ids)
            ).count()
            teacher_stats = {
                "total_students": total_students,
                "today_marked": today_marked,
                "not_marked_today": not_marked_today,
                "marks_this_week": marks_this_week,
                "assigned_class": current_user.assigned_class,
                "assigned_section": current_user.assigned_section or "",
            }
        else:
            teacher_stats = {"not_assigned": True}

    return render_template("dashboard.html", stats=stats, fee_stats=fee_stats,
                           today_date=today_date, recent_activity=recent_activity,
                           is_sunday=is_sunday, holiday=holiday,
                           teacher_stats=teacher_stats,
                           pending_requests_count=AttendanceRequest.query.filter_by(status="Pending").count() if current_user.role == "admin" else 0)


# ---------------- Students ----------------
@app.route("/students")
@login_required
def students():
    q = request.args.get("q", "").strip()

    # Teacher sees only their assigned class students
    if current_user.role == "teacher":
        if not current_user.assigned_class:
            flash("You have not been assigned a class yet. Please contact the admin.", "warning")
            return redirect(url_for("dashboard"))
        class_filter = current_user.assigned_class
        section_filter = current_user.assigned_section or ""
    else:
        class_filter = request.args.get("class_name", "").strip()
        section_filter = request.args.get("section", "").strip()

    query = Student.query
    if q:
        query = query.filter(
            db.or_(
                Student.roll_number.ilike(f"%{q}%"),
                Student.name.ilike(f"%{q}%")
            )
        )
    if class_filter:
        query = query.filter(Student.class_name == class_filter)
    if section_filter:
        query = query.filter(Student.section == section_filter)

    items = query.order_by(Student.class_name, Student.section, Student.name).all()

    # Class strength chart (admin only)
    class_chart = None
    if current_user.role == "admin":
        rows = (
            db.session.query(Student.class_name, db.func.count(Student.id))
            .group_by(Student.class_name)
            .all()
        )
        counts = {name: cnt for name, cnt in rows if name}
        class_chart = {
            "labels": CLASS_OPTIONS,
            "data": [counts.get(c, 0) for c in CLASS_OPTIONS],
        }

    return render_template(
        "students.html",
        students=items, q=q,
        class_filter=class_filter, section_filter=section_filter,
        class_chart=class_chart,
    )


@app.route("/students/new", methods=["GET", "POST"])
@role_required("admin", "teacher")
def student_new():
    if request.method == "POST":
        try:
            s = Student(
                name=request.form["name"].strip(),
                class_name=request.form["class_name"].strip(),
                section=(request.form.get("section") or "").strip() or None,
                roll_number=request.form["roll_number"].strip(),
                dob=parse_date(request.form["dob"]),
                parent_name=request.form["parent_name"].strip(),
                parent_phone=request.form.get("parent_phone", "").strip() or None,
                address=request.form.get("address", "").strip() or None,
            )
            db.session.add(s)
            db.session.commit()
            flash("Student added successfully.", "success")
            return redirect(url_for("students"))
        except Exception as e:
            db.session.rollback()
            flash(f"Could not add student: {e}", "danger")
    return render_template("student_form.html", student=None)


@app.route("/students/<int:sid>/edit", methods=["GET", "POST"])
@role_required("admin", "teacher")
def student_edit(sid):
    s = db.session.get(Student, sid) or abort(404)
    if request.method == "POST":
        try:
            s.name = request.form["name"].strip()
            s.class_name = request.form["class_name"].strip()
            s.section = (request.form.get("section") or "").strip() or None
            s.roll_number = request.form["roll_number"].strip()
            s.dob = parse_date(request.form["dob"])
            s.parent_name = request.form["parent_name"].strip()
            s.parent_phone = request.form.get("parent_phone", "").strip() or None
            s.address = request.form.get("address", "").strip() or None
            db.session.commit()
            flash("Student updated.", "success")
            return redirect(url_for("students"))
        except Exception as e:
            db.session.rollback()
            flash(f"Could not update student: {e}", "danger")
    return render_template("student_form.html", student=s)


@app.route("/students/<int:sid>/delete", methods=["POST"])
@role_required("admin")
def student_delete(sid):
    s = db.session.get(Student, sid) or abort(404)
    db.session.delete(s)
    db.session.commit()
    flash("Student deleted.", "info")
    return redirect(url_for("students"))


@app.route("/students/<int:sid>")
@login_required
def student_detail(sid):
    s = db.session.get(Student, sid) or abort(404)
    history = Attendance.query.filter_by(student_id=sid).order_by(Attendance.date.desc()).all()
    marks = Mark.query.filter_by(student_id=sid).order_by(Mark.subject, Mark.exam).all()

    # Build pivot: subjects × exams
    all_exams = sorted(set(m.exam for m in marks), key=lambda e: EXAM_TYPES.index(e) if e in EXAM_TYPES else 999)
    all_subjects = sorted(set(m.subject for m in marks))
    mark_lookup = {(m.subject, m.exam): m for m in marks}
    max_per_exam = {}
    for m in marks:
        max_per_exam[m.exam] = m.max_score

    pivot_rows = []
    for subj in all_subjects:
        row_scores = {}
        for e in all_exams:
            mk = mark_lookup.get((subj, e))
            row_scores[e] = mk.score if mk is not None else None
        entered = {e: v for e, v in row_scores.items() if v is not None}
        subj_total     = sum(entered.values()) if entered else None
        subj_max       = sum(max_per_exam[e] for e in entered) if entered else None
        subj_total_str = f"{subj_total:.1f} / {subj_max:.0f}" if subj_total is not None else "—"
        subj_pct_val   = (subj_total / subj_max * 100) if subj_max else None
        subj_pct_str   = f"{subj_pct_val:.1f}%" if subj_pct_val is not None else "—"
        pivot_rows.append({
            "subject": subj,
            "scores": row_scores,
            "total": subj_total_str,
            "pct_val": subj_pct_val,
            "pct": subj_pct_str,
        })

    # Grand total across all entered marks
    all_entered = [m for m in marks]
    grand_total   = sum(m.score for m in all_entered)
    grand_max     = sum(m.max_score for m in all_entered)
    grand_pct     = (grand_total / grand_max * 100) if grand_max else 0

    # Overall attendance
    att_total   = len(history)
    att_present = sum(1 for a in history if a.status == "Present")
    att_pct     = (att_present / att_total * 100) if att_total else 0

    # Fee summary
    fees = Fee.query.filter_by(student_id=sid).all()
    fee_total  = sum(f.amount for f in fees)
    fee_paid   = sum(f.amount for f in fees if f.status == "Paid")
    fee_unpaid = fee_total - fee_paid

    return render_template(
        "student_detail.html",
        student=s, history=history, marks=marks,
        pivot_rows=pivot_rows, all_exams=all_exams, max_per_exam=max_per_exam,
        grand_total=grand_total, grand_max=grand_max, grand_pct=grand_pct,
        att_total=att_total, att_present=att_present, att_pct=att_pct,
        fee_total=fee_total, fee_paid=fee_paid, fee_unpaid=fee_unpaid, fees=fees,
    )


# ---------------- Attendance ----------------
def _get_ist_today():
    from datetime import timedelta
    return (datetime.utcnow() + timedelta(hours=5, minutes=30)).date()

def _teacher_daily_request_used(teacher_id):
    """Returns True if the teacher has already submitted any approval request today (IST)."""
    ist_today = _get_ist_today()
    return AttendanceRequest.query.filter(
        AttendanceRequest.teacher_id == teacher_id,
        db.func.date(AttendanceRequest.created_at) == ist_today.isoformat()
    ).first() is not None

def _get_teacher_attendance_state(teacher_id, attendance_date):
    """
    Rules:
      - Teacher can mark today's attendance ONCE freely (before cutoff hour).
      - Teacher gets ONE request per calendar day (IST). This request can be used for:
          (a) editing today's attendance (after the free mark), OR
          (b) marking/editing a past date's attendance.
        Whichever is used first consumes the daily request quota.
      - After an approved request is used once, it is spent — no further saves allowed.
    """
    from datetime import timedelta
    ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    after_cutoff = ist_now.hour >= SCHOOL_CUTOFF_HOUR
    ist_today = ist_now.date()

    is_past = attendance_date < date.today()
    is_today = attendance_date == date.today()

    # How many times has this teacher saved attendance for this specific date?
    audit_rows = AttendanceAudit.query.filter_by(
        teacher_id=teacher_id,
        attendance_date=attendance_date
    ).all()
    edit_count = len(audit_rows)  # each row = one save action
    already_marked = edit_count > 0

    # Has the teacher already used their daily request today?
    daily_request_used = _teacher_daily_request_used(teacher_id)

    # Is there an approved request for this specific date that hasn't been consumed yet?
    approved_req = AttendanceRequest.query.filter_by(
        teacher_id=teacher_id,
        request_date=attendance_date,
        status="Approved"
    ).first()
    approval_used = False
    if approved_req:
        spent = AttendanceAudit.query.filter_by(
            approved_by_request=approved_req.id
        ).first()
        if spent:
            approval_used = True
            approved_req = None  # consumed — cannot use again

    # ── can_mark: first-time mark for this date ──
    if already_marked:
        can_mark = False
    elif is_today and not after_cutoff:
        can_mark = True          # free first mark today within hours
    else:
        # past date OR after cutoff → needs an unused approved request
        can_mark = approved_req is not None

    # ── can_edit: update already-marked attendance ──
    if not already_marked:
        can_edit = False
    elif approved_req is not None:
        can_edit = True          # approved request exists and not yet used
    else:
        can_edit = False         # no approved request → must request one

    # ── needs_request: should we show the request form? ──
    # Show it when the teacher is blocked AND hasn't used today's quota yet
    # AND the approval hasn't already been consumed
    if is_today and not after_cutoff and not already_marked:
        needs_request = False    # free first mark — no request needed
    elif approved_req is not None:
        needs_request = False    # already has a live approval
    elif approval_used:
        needs_request = False    # approval spent, nothing more allowed
    else:
        needs_request = True     # blocked — show request form if quota available

    return {
        "can_mark": can_mark,
        "can_edit": can_edit,
        "edit_count": edit_count,
        "after_cutoff": after_cutoff,
        "approved_req": approved_req,
        "approval_used": approval_used,
        "daily_request_used": daily_request_used,
        "needs_request": needs_request,
        "is_past": is_past,
        "is_today": is_today,
        "already_marked": already_marked,
    }


@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    today_str = request.values.get("date") or date.today().isoformat()
    selected_date = parse_date(today_str)

    # If teacher, force their assigned class/section
    if current_user.role == "teacher":
        if not current_user.assigned_class:
            flash("You have not been assigned a class yet. Please contact the admin.", "warning")
            return redirect(url_for("dashboard"))
        class_filter = current_user.assigned_class
        section_filter = current_user.assigned_section or ""
    else:
        class_filter = request.values.get("class_name", "").strip()
        section_filter = request.values.get("section", "").strip()

    query = Student.query
    if class_filter:
        query = query.filter(Student.class_name == class_filter)
    if section_filter:
        query = query.filter(Student.section == section_filter)
    students_list = query.order_by(Student.class_name, Student.section, Student.name).all()

    is_sunday = selected_date.weekday() == 6
    holiday = Holiday.query.filter_by(date=selected_date).first()
    is_holiday = holiday is not None

    # Teacher attendance state
    att_state = None
    if current_user.role == "teacher":
        att_state = _get_teacher_attendance_state(current_user.id, selected_date)

    if request.method == "POST":
        if current_user.role != "teacher":
            abort(403)
        if is_sunday:
            flash("Cannot mark attendance on Sundays.", "danger")
            return redirect(url_for("attendance", date=today_str))
        if is_holiday:
            flash(f"Cannot mark attendance — {holiday.reason} is a holiday.", "danger")
            return redirect(url_for("attendance", date=today_str))

        action = request.form.get("action", "save")

        # --- Submit approval request ---
        if action == "request_approval":
            reason = request.form.get("reason", "").strip()
            req_type = request.form.get("request_type", "past_date")
            if not reason:
                flash("Please provide a reason for the approval request.", "danger")
                return redirect(url_for("attendance", date=today_str))

            # Re-fetch state to enforce limits server-side
            state = _get_teacher_attendance_state(current_user.id, selected_date)

            # Block if daily quota already used
            if state["daily_request_used"]:
                flash("You have already used your one approval request for today. Try again tomorrow.", "warning")
                return redirect(url_for("attendance", date=today_str))

            # Block if there is already a pending request for this date
            existing_pending = AttendanceRequest.query.filter_by(
                teacher_id=current_user.id,
                request_date=selected_date,
                status="Pending"
            ).first()
            if existing_pending:
                flash("You already have a pending request for this date.", "warning")
                return redirect(url_for("attendance", date=today_str))

            # Block if approval already consumed for this date
            if state["approval_used"]:
                flash("Your approval for this date has already been used. No further changes allowed.", "danger")
                return redirect(url_for("attendance", date=today_str))

            db.session.add(AttendanceRequest(
                teacher_id=current_user.id,
                request_date=selected_date,
                reason=reason,
                request_type=req_type,
            ))
            db.session.commit()
            flash("Approval request sent to admin. You have used your one request for today.", "success")
            return redirect(url_for("attendance", date=today_str))

        # --- Save attendance ---
        if not (att_state["can_mark"] or att_state["can_edit"]):
            flash("Seek approval from admin to mark or update attendance for this date.", "danger")
            return redirect(url_for("attendance", date=today_str))

        for s in students_list:
            status = request.form.get(f"status_{s.id}")
            if status not in ("Present", "Absent"):
                continue
            existing = Attendance.query.filter_by(student_id=s.id, date=selected_date).first()
            if existing:
                existing.status = status
            else:
                db.session.add(Attendance(student_id=s.id, date=selected_date, status=status))

        # Record audit
        audit = AttendanceAudit(
            teacher_id=current_user.id,
            attendance_date=selected_date,
            action="edit" if att_state["already_marked"] else "mark",
            edit_count=1,
            approved_by_request=att_state["approved_req"].id if att_state["approved_req"] else None
        )
        db.session.add(audit)
        db.session.commit()
        flash(f"Attendance saved for {selected_date.strftime('%d %b %Y')}.", "success")
        return redirect(url_for("attendance", date=today_str))

    existing_map = {
        a.student_id: a.status
        for a in Attendance.query.filter_by(date=selected_date).all()
    }

    # Pending request for this specific date (teacher)
    pending_request = None
    if current_user.role == "teacher":
        pending_request = AttendanceRequest.query.filter_by(
            teacher_id=current_user.id,
            request_date=selected_date,
            status="Pending"
        ).first()

    # Today's attendance pie chart (admin only)
    today_chart = None
    if current_user.role == "admin":
        today = date.today()
        today_records = Attendance.query.filter_by(date=today).all()
        present = sum(1 for a in today_records if a.status == "Present")
        absent = sum(1 for a in today_records if a.status == "Absent")
        total_marked = present + absent
        today_chart = {
            "present": present,
            "absent": absent,
            "total": total_marked,
            "present_pct": (present / total_marked * 100) if total_marked else 0,
            "absent_pct": (absent / total_marked * 100) if total_marked else 0,
        }

    # Audit log for admin view
    audit_log = []
    if current_user.role == "admin":
        audit_log = (
            AttendanceAudit.query
            .order_by(AttendanceAudit.created_at.desc())
            .limit(20).all()
        )

    return render_template(
        "attendance.html",
        students=students_list, selected_date=selected_date,
        existing_map=existing_map,
        class_filter=class_filter, section_filter=section_filter,
        today_chart=today_chart,
        is_sunday=is_sunday,
        is_holiday=is_holiday,
        holiday=holiday,
        att_state=att_state,
        pending_request=pending_request,
        audit_log=audit_log,
        school_cutoff_hour=SCHOOL_CUTOFF_HOUR,
    )


# ---------------- Unified Approval Requests (Admin) ----------------
@app.route("/approval-requests")
@role_required("admin")
def approval_requests():
    status_filter = request.args.get("status", "Pending")
    valid = ("Pending", "Approved", "Rejected")
    att_q = AttendanceRequest.query
    mrk_q = MarksRequest.query
    if status_filter in valid:
        att_q = att_q.filter_by(status=status_filter)
        mrk_q = mrk_q.filter_by(status=status_filter)
    att_requests = att_q.order_by(AttendanceRequest.created_at.desc()).all()
    mrk_requests = mrk_q.order_by(MarksRequest.created_at.desc()).all()
    att_pending = AttendanceRequest.query.filter_by(status="Pending").count()
    mrk_pending = MarksRequest.query.filter_by(status="Pending").count()
    return render_template(
        "approval_requests.html",
        att_requests=att_requests,
        mrk_requests=mrk_requests,
        status_filter=status_filter,
        att_pending=att_pending,
        mrk_pending=mrk_pending,
    )


# ── Old URLs redirect to unified page ──
@app.route("/attendance-requests")
@role_required("admin")
def attendance_requests():
    return redirect(url_for("approval_requests", status=request.args.get("status", "Pending")))


@app.route("/attendance-requests/<int:rid>/resolve", methods=["POST"])
@role_required("admin")
def resolve_attendance_request(rid):
    r = db.session.get(AttendanceRequest, rid) or abort(404)
    action = request.form.get("action")
    if action in ("approve", "reject"):
        r.status = "Approved" if action == "approve" else "Rejected"
        r.resolved_at = datetime.utcnow()
        db.session.commit()
        flash(f"Request {r.status.lower()} for {r.teacher.full_name} — {r.request_date.strftime('%d %b %Y')}.", "success")
    # Bulk
    return redirect(url_for("attendance_requests"))


@app.route("/attendance-requests/bulk", methods=["POST"])
@role_required("admin")
def bulk_resolve_attendance_requests():
    ids = request.form.getlist("req_ids")
    action = request.form.get("action")
    if action not in ("approve", "reject") or not ids:
        flash("Invalid bulk action.", "danger")
        return redirect(url_for("attendance_requests"))
    new_status = "Approved" if action == "approve" else "Rejected"
    for rid in ids:
        r = db.session.get(AttendanceRequest, int(rid))
        if r and r.status == "Pending":
            r.status = new_status
            r.resolved_at = datetime.utcnow()
    db.session.commit()
    flash(f"{len(ids)} request(s) {new_status.lower()}.", "success")
    return redirect(url_for("attendance_requests"))


# ---------------- Holidays (Admin only) ----------------
@app.route("/holidays", methods=["GET", "POST"])
@role_required("admin")
def holidays():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            date_str = request.form.get("date", "").strip()
            reason = request.form.get("reason", "").strip()
            if date_str and reason:
                try:
                    h_date = date.fromisoformat(date_str)
                    if h_date.weekday() == 6:
                        flash("Sundays are already blocked automatically.", "warning")
                    else:
                        db.session.add(Holiday(date=h_date, reason=reason))
                        db.session.commit()
                        flash(f"Holiday added: {reason} on {h_date.strftime('%d %b %Y')}.", "success")
                except Exception as e:
                    db.session.rollback()
                    flash(f"Could not add holiday: {e}", "danger")
        elif action == "delete":
            hid = int(request.form.get("holiday_id"))
            h = db.session.get(Holiday, hid)
            if h:
                db.session.delete(h)
                db.session.commit()
                flash("Holiday removed.", "success")
        return redirect(url_for("holidays"))

    all_holidays = Holiday.query.order_by(Holiday.date).all()
    return render_template("holidays.html", holidays=all_holidays, today=date.today().isoformat())


# ---------------- Subjects ----------------
@app.route("/subjects", methods=["GET", "POST"])
@role_required("admin")
def subjects():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            class_name = request.form.get("class_name", "").strip()
            name = request.form.get("name", "").strip()
            if class_name and name:
                try:
                    db.session.add(Subject(class_name=class_name, name=name))
                    db.session.commit()
                    flash(f"Subject '{name}' added for {class_name}.", "success")
                except Exception as e:
                    db.session.rollback()
                    flash(f"Subject already exists or could not be added: {e}", "danger")
        elif action == "delete":
            sid = int(request.form.get("subject_id"))
            s = db.session.get(Subject, sid)
            if s:
                db.session.delete(s)
                db.session.commit()
                flash("Subject deleted.", "success")
        return redirect(url_for("subjects"))

    all_subjects = Subject.query.order_by(Subject.class_name, Subject.name).all()
    # Group by class
    subjects_by_class = {}
    for s in all_subjects:
        subjects_by_class.setdefault(s.class_name, []).append(s)

    return render_template("subjects.html", subjects_by_class=subjects_by_class)


# ---------------- Marks Helpers ----------------
def _marks_daily_request_used(teacher_id):
    """Returns True if teacher already submitted a marks approval request today (IST)."""
    ist_today = _get_ist_today()
    return MarksRequest.query.filter(
        MarksRequest.requester_id == teacher_id,
        db.func.date(MarksRequest.created_at) == ist_today.isoformat()
    ).first() is not None


def _get_marks_state(teacher_id, class_name, exam, subject):
    """
    Rules for marks entry per (class, exam, subject):
      - Teacher can enter marks ONCE freely (first time, within school hours).
      - After that, every edit needs admin approval (1 request per day, separate quota from attendance).
      - Once an approved request is used (saved), it is spent — no further edits.
    """
    from datetime import timedelta
    ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    after_cutoff = ist_now.hour >= SCHOOL_CUTOFF_HOUR

    # Has any mark been entered for this class+exam+subject combo by this teacher?
    entered = MarksAudit.query.filter_by(
        user_id=teacher_id,
        class_name=class_name,
        exam=exam,
        subject=subject,
    ).first()
    already_entered = entered is not None

    # Check for unused approved request for this combo
    approved_req = MarksRequest.query.filter_by(
        requester_id=teacher_id,
        class_name=class_name,
        exam=exam,
        subject=subject,
        status="Approved"
    ).first()
    approval_used = False
    if approved_req:
        spent = MarksAudit.query.filter_by(
            approved_by_request=approved_req.id
        ).first()
        if spent:
            approval_used = True
            approved_req = None

    daily_request_used = _marks_daily_request_used(teacher_id)

    # can_enter: first-time entry, within school hours
    if already_entered:
        can_enter = False
    elif after_cutoff:
        can_enter = approved_req is not None
    else:
        can_enter = True

    # can_edit: already entered, needs approval
    if not already_entered:
        can_edit = False
    elif approved_req is not None:
        can_edit = True
    else:
        can_edit = False

    # needs_request: show the approval request form?
    if not already_entered and not after_cutoff:
        needs_request = False
    elif approved_req is not None:
        needs_request = False
    elif approval_used:
        needs_request = False
    else:
        needs_request = True

    return {
        "can_enter": can_enter,
        "can_edit": can_edit,
        "already_entered": already_entered,
        "after_cutoff": after_cutoff,
        "approved_req": approved_req,
        "approval_used": approval_used,
        "daily_request_used": daily_request_used,
        "needs_request": needs_request,
    }


# ---------------- Marks ----------------
@app.route("/marks", methods=["GET", "POST"])
@role_required("admin", "teacher")
def marks():
    # Admin: pick class/section via query params; teacher: use assigned class
    if current_user.role == "admin":
        class_name = request.values.get("class_name", "").strip()
        section    = request.values.get("section", "").strip()
        if not class_name:
            return render_template(
                "marks.html",
                students=[], subject_list=[], exam_types=EXAM_TYPES,
                class_name="", section="",
                sel_exam="", sel_subject="",
                existing_marks={}, existing_max=100.0,
                new_student_ids=set(),
                marks_state=None, pending_marks_request=None,
                summary=[], pivot_tables=[],
                school_cutoff_hour=SCHOOL_CUTOFF_HOUR,
                is_admin_view=True,
            )
    else:
        if not current_user.assigned_class:
            flash("You have not been assigned a class yet. Please contact the admin.", "warning")
            return redirect(url_for("dashboard"))
        class_name = current_user.assigned_class
        section    = current_user.assigned_section or ""

    # All subjects for this class
    subject_rows = Subject.query.filter_by(class_name=class_name).order_by(Subject.name).all()
    subject_list = [s.name for s in subject_rows]

    # Students for this class/section
    q = Student.query.filter_by(class_name=class_name)
    if section:
        q = q.filter_by(section=section)
    students_list = q.order_by(Student.name).all()

    # Selected exam & subject from query/form
    sel_exam    = request.values.get("exam", "").strip()
    sel_subject = request.values.get("subject", "").strip()

    # ── POST actions are teacher-only (admin has read-only view) ──
    if request.method == "POST" and current_user.role == "admin":
        abort(403)

    # ── POST: request approval ──
    if request.method == "POST" and request.form.get("action") == "request_approval":
        reason      = request.form.get("reason", "").strip()
        req_exam    = request.form.get("req_exam", "").strip()
        req_subject = request.form.get("req_subject", "").strip()
        if not reason:
            flash("Please provide a reason for the approval request.", "danger")
            return redirect(url_for("marks", exam=sel_exam, subject=sel_subject))
        if _marks_daily_request_used(current_user.id):
            flash("You have already used your one marks-approval request for today. Try again tomorrow.", "warning")
            return redirect(url_for("marks", exam=sel_exam, subject=sel_subject))
        # Block duplicate pending for same combo
        existing_pending = MarksRequest.query.filter_by(
            requester_id=current_user.id,
            class_name=class_name,
            exam=req_exam,
            subject=req_subject,
            status="Pending"
        ).first()
        if existing_pending:
            flash("You already have a pending request for this exam/subject.", "warning")
            return redirect(url_for("marks", exam=sel_exam, subject=sel_subject))
        db.session.add(MarksRequest(
            requester_id=current_user.id,
            class_name=class_name,
            exam=req_exam,
            subject=req_subject,
            reason=reason,
        ))
        db.session.commit()
        flash("Approval request sent to admin. You have used your marks request for today.", "success")
        return redirect(url_for("marks", exam=sel_exam, subject=sel_subject))

    # ── POST: bulk save marks ──
    if request.method == "POST" and request.form.get("action") == "save_marks":
        req_exam    = request.form.get("bulk_exam", "").strip()
        req_subject = request.form.get("bulk_subject", "").strip()
        max_score   = float(request.form.get("max_score") or 100)

        if not req_exam or not req_subject:
            flash("Please select an exam and subject.", "danger")
            return redirect(url_for("marks", exam=req_exam, subject=req_subject))

        state = _get_marks_state(current_user.id, class_name, req_exam, req_subject)

        # Build set of student IDs that have no existing mark — new enrolments always allowed.
        already_marked_ids = set()
        if state["already_entered"]:
            for m in Mark.query.join(Student).filter(
                Student.class_name == class_name,
                Mark.exam == req_exam,
                Mark.subject == req_subject,
            ).all():
                already_marked_ids.add(m.student_id)

        can_act = state["can_enter"] or state["can_edit"]

        # Determine which students are being submitted and whether any need approval
        submitted_students = []
        for s in students_list:
            score_str = request.form.get(f"score_{s.id}", "").strip()
            if score_str == "":
                continue
            try:
                score_val = float(score_str)
            except ValueError:
                continue
            is_new = s.id not in already_marked_ids
            submitted_students.append((s, score_val, is_new))

        # If there are no new students in this submission and we cannot act, block it
        touches_existing = any(not is_new for _, _, is_new in submitted_students)
        if touches_existing and not can_act:
            flash("Seek approval from admin to enter or update marks for this exam/subject.", "danger")
            return redirect(url_for("marks", exam=req_exam, subject=req_subject))
        if not submitted_students:
            flash("No scores to save.", "warning")
            return redirect(url_for("marks", exam=req_exam, subject=req_subject))

        saved = 0
        for s, score, is_new in submitted_students:
            if not is_new and not can_act:
                continue  # safety guard — skip existing-student rows if not permitted
            score = max(0.0, min(score, max_score))
            existing = Mark.query.filter_by(student_id=s.id, subject=req_subject, exam=req_exam).first()
            if existing:
                existing.score = score
                existing.max_score = max_score
            else:
                db.session.add(Mark(
                    student_id=s.id, subject=req_subject,
                    exam=req_exam, score=score, max_score=max_score
                ))
            saved += 1

        # Audit log entry
        audit = MarksAudit(
            user_id=current_user.id,
            class_name=class_name,
            exam=req_exam,
            subject=req_subject,
            action="edit" if state["already_entered"] else "enter",
            approved_by_request=state["approved_req"].id if state["approved_req"] else None,
        )
        db.session.add(audit)
        db.session.commit()
        flash(f"Marks saved for {saved} student(s) — {req_exam} · {req_subject}.", "success")
        return redirect(url_for("marks", exam=req_exam, subject=req_subject))

    # ── GET: build state for selected combo (teacher only) ──
    marks_state = None
    pending_marks_request = None
    if sel_exam and sel_subject and current_user.role == "teacher":
        marks_state = _get_marks_state(current_user.id, class_name, sel_exam, sel_subject)
        pending_marks_request = MarksRequest.query.filter_by(
            requester_id=current_user.id,
            class_name=class_name,
            exam=sel_exam,
            subject=sel_subject,
            status="Pending"
        ).first()

    # Existing marks map: student_id -> score for selected combo (teacher view)
    existing_marks = {}
    existing_max = 100.0
    if sel_exam and sel_subject and current_user.role == "teacher":
        for m in Mark.query.join(Student).filter(
            Student.class_name == class_name,
            Mark.exam == sel_exam,
            Mark.subject == sel_subject
        ).all():
            existing_marks[m.student_id] = m.score
            existing_max = m.max_score

    # Students who have NO mark yet for this combo — they can always be saved freely
    # even when the rest of the class already has marks entered (new enrollments).
    new_student_ids = set()
    if sel_exam and sel_subject and current_user.role == "teacher" and marks_state and marks_state["already_entered"]:
        new_student_ids = {s.id for s in students_list if s.id not in existing_marks}

    # Summary: all marks for this class grouped by exam+subject (teacher view)
    summary = []
    if current_user.role == "teacher":
        summary_rows = (
            db.session.query(
                Mark.exam, Mark.subject,
                db.func.count(Mark.id).label("count"),
                db.func.avg(Mark.score).label("avg"),
                db.func.max(Mark.score).label("highest"),
                db.func.min(Mark.score).label("lowest"),
                db.func.avg(Mark.max_score).label("max_score"),
            )
            .join(Student, Mark.student_id == Student.id)
            .filter(Student.class_name == class_name)
            .group_by(Mark.exam, Mark.subject)
            .order_by(Mark.exam, Mark.subject)
            .all()
        )
        for row in summary_rows:
            pass_count = Mark.query.join(Student).filter(
                Student.class_name == class_name,
                Mark.exam == row.exam,
                Mark.subject == row.subject,
                Mark.score >= (Mark.max_score * 0.35)
            ).count()
            total = row.count
            summary.append({
                "exam": row.exam,
                "subject": row.subject,
                "count": total,
                "avg": round(row.avg, 1) if row.avg else 0,
                "highest": round(row.highest, 1) if row.highest else 0,
                "lowest": round(row.lowest, 1) if row.lowest else 0,
                "max_score": round(row.max_score, 0) if row.max_score else 100,
                "pass": pass_count,
                "fail": total - pass_count,
            })

    # ── Admin pivot: per subject → students × exams ──
    pivot_tables = []
    if current_user.role == "admin" and class_name:
        # Determine which subjects to show
        if sel_subject:
            subjects_to_show = [sel_subject]
        else:
            subjects_to_show = subject_list  # all subjects for class

        # Fetch all marks for this class (filtered by subject only — all exams always shown as columns)
        mq = Mark.query.join(Student).filter(Student.class_name == class_name)
        if section:
            mq = mq.filter(Student.section == section)
        if sel_subject:
            mq = mq.filter(Mark.subject == sel_subject)
        all_marks = mq.all()

        # Build lookup: (student_id, subject, exam) -> Mark
        mark_lookup = {}
        for m in all_marks:
            mark_lookup[(m.student_id, m.subject, m.exam)] = m

        for subj in subjects_to_show:
            # Only build table if there's any data for this subject
            subj_marks = [m for m in all_marks if m.subject == subj]
            if not subj_marks:
                continue

            # Exams that have data for this subject
            subj_exams = sorted(set(m.exam for m in subj_marks), key=lambda e: EXAM_TYPES.index(e) if e in EXAM_TYPES else 999)
            # max_score per exam for this subject
            max_per_exam = {}
            for m in subj_marks:
                max_per_exam[m.exam] = m.max_score

            rows = []
            col_scores = {e: [] for e in subj_exams}  # for class avg

            for s in students_list:
                row_scores = {}
                for e in subj_exams:
                    m = mark_lookup.get((s.id, subj, e))
                    if m is not None:
                        row_scores[e] = m.score
                        col_scores[e].append(m.score)
                    else:
                        row_scores[e] = None  # — not entered

                # Total & % — only exams where score is not None
                entered = {e: v for e, v in row_scores.items() if v is not None}
                if entered:
                    total_score = sum(entered.values())
                    total_max   = sum(max_per_exam[e] for e in entered)
                    total_str   = f"{total_score:.1f} / {total_max:.0f}"
                    pct_val     = (total_score / total_max * 100) if total_max else 0
                    pct_str     = f"{pct_val:.1f}%"
                else:
                    total_str = "—"
                    pct_str   = "—"
                    pct_val   = None

                rows.append({
                    "student": s,
                    "scores": row_scores,
                    "total": total_str,
                    "pct": pct_str,
                    "pct_val": pct_val,
                })

            # Class average row per exam (only students who have that exam entered)
            avg_row = {}
            for e in subj_exams:
                vals = col_scores[e]
                avg_row[e] = round(sum(vals) / len(vals), 1) if vals else None

            pivot_tables.append({
                "subject": subj,
                "exams": subj_exams,
                "max_per_exam": max_per_exam,
                "rows": rows,
                "avg_row": avg_row,
            })

    return render_template(
        "marks.html",
        students=students_list,
        subject_list=subject_list,
        exam_types=EXAM_TYPES,
        class_name=class_name,
        section=section,
        sel_exam=sel_exam,
        sel_subject=sel_subject,
        existing_marks=existing_marks,
        existing_max=existing_max,
        new_student_ids=new_student_ids,
        marks_state=marks_state,
        pending_marks_request=pending_marks_request,
        summary=summary,
        pivot_tables=pivot_tables,
        school_cutoff_hour=SCHOOL_CUTOFF_HOUR,
        is_admin_view=current_user.role == "admin",
    )


@app.route("/marks/<int:mid>/delete", methods=["POST"])
@role_required("admin")
def mark_delete(mid):
    m = db.session.get(Mark, mid) or abort(404)
    db.session.delete(m)
    db.session.commit()
    flash("Mark removed.", "info")
    return redirect(url_for("students"))


# ---------------- Marks Approval (Admin) ----------------
@app.route("/marks-requests")
@role_required("admin")
def marks_requests():
    return redirect(url_for("approval_requests", status=request.args.get("status", "Pending")))


@app.route("/marks-requests/<int:rid>/resolve", methods=["POST"])
@role_required("admin")
def resolve_marks_request(rid):
    r = db.session.get(MarksRequest, rid) or abort(404)
    action = request.form.get("action")
    if action in ("approve", "reject"):
        r.status = "Approved" if action == "approve" else "Rejected"
        r.resolved_at = datetime.utcnow()
        db.session.commit()
        flash(f"Marks request {r.status.lower()} for {r.requester.full_name}.", "success")
    return redirect(url_for("marks_requests"))


@app.route("/marks-requests/bulk", methods=["POST"])
@role_required("admin")
def bulk_resolve_marks_requests():
    ids = request.form.getlist("req_ids")
    action = request.form.get("action")
    if action not in ("approve", "reject") or not ids:
        flash("Invalid bulk action.", "danger")
        return redirect(url_for("marks_requests"))
    new_status = "Approved" if action == "approve" else "Rejected"
    for rid in ids:
        r = db.session.get(MarksRequest, int(rid))
        if r and r.status == "Pending":
            r.status = new_status
            r.resolved_at = datetime.utcnow()
    db.session.commit()
    flash(f"{len(ids)} marks request(s) {new_status.lower()}.", "success")
    return redirect(url_for("marks_requests"))


# ---------------- Teacher Management (Admin only) ----------------
@app.route("/teachers")
@role_required("admin")
def teachers():
    q = request.args.get("q", "").strip()
    query = User.query.filter_by(role="teacher")
    if q:
        query = query.filter(
            db.or_(
                User.full_name.ilike(f"%{q}%"),
                User.username.ilike(f"%{q}%"),
            )
        )
    items = query.order_by(User.full_name).all()
    return render_template("teachers.html", teachers=items, q=q)


@app.route("/teachers/new", methods=["GET", "POST"])
@role_required("admin")
def teacher_new():
    if request.method == "POST":
        try:
            u = User(
                username=request.form["username"].strip(),
                full_name=request.form["full_name"].strip(),
                role="teacher",
                must_change_password=True,
                phone=request.form.get("phone", "").strip() or None,
                address=request.form.get("address", "").strip() or None,
                subject_assignment=request.form.get("subject_assignment", "").strip() or None,
                assigned_class=request.form.get("assigned_class", "").strip() or None,
                assigned_section=request.form.get("assigned_section", "").strip() or None,
            )
            u.set_password(request.form["password"])
            db.session.add(u)
            db.session.commit()
            flash(
                f"Teacher account created. They must change their password on first login.",
                "success",
            )
            return redirect(url_for("teachers"))
        except Exception as e:
            db.session.rollback()
            flash(f"Could not add teacher: {e}", "danger")
    return render_template("teacher_form.html", teacher=None, class_options=CLASS_OPTIONS, section_options=SECTION_OPTIONS)


@app.route("/teachers/<int:uid>/edit", methods=["GET", "POST"])
@role_required("admin")
def teacher_edit(uid):
    u = db.session.get(User, uid) or abort(404)
    if u.role != "teacher":
        abort(400)
    if request.method == "POST":
        try:
            u.full_name = request.form["full_name"].strip()
            u.username = request.form["username"].strip()
            u.phone = request.form.get("phone", "").strip() or None
            u.address = request.form.get("address", "").strip() or None
            u.subject_assignment = request.form.get("subject_assignment", "").strip() or None
            u.assigned_class = request.form.get("assigned_class", "").strip() or None
            u.assigned_section = request.form.get("assigned_section", "").strip() or None
            db.session.commit()
            flash("Teacher updated.", "success")
            return redirect(url_for("teacher_detail", uid=uid))
        except Exception as e:
            db.session.rollback()
            flash(f"Could not update teacher: {e}", "danger")
    return render_template("teacher_form.html", teacher=u, class_options=CLASS_OPTIONS, section_options=SECTION_OPTIONS)


@app.route("/teachers/<int:uid>")
@role_required("admin")
def teacher_detail(uid):
    u = db.session.get(User, uid) or abort(404)
    if u.role != "teacher":
        abort(400)
    # Attendance marked by this teacher (we don't track who marked, so show school-wide stats)
    # Instead show: classes they are assigned to + recent attendance summary
    total_students = Student.query.count()
    total_attendance_days = db.session.query(Attendance.date).distinct().count()
    # Marks entered (no teacher FK on marks, show school-wide as context)
    total_marks = Mark.query.count()
    return render_template("teacher_detail.html", teacher=u,
                           total_students=total_students,
                           total_attendance_days=total_attendance_days,
                           total_marks=total_marks)


@app.route("/teachers/<int:uid>/delete", methods=["POST"])
@role_required("admin")
def teacher_delete(uid):
    u = db.session.get(User, uid) or abort(404)
    if u.role != "teacher":
        abort(400)
    db.session.delete(u)
    db.session.commit()
    flash("Teacher removed.", "info")
    return redirect(url_for("teachers"))


@app.route("/teachers/<int:uid>/reset", methods=["POST"])
@role_required("admin")
def teacher_reset(uid):
    u = db.session.get(User, uid) or abort(404)
    if u.role != "teacher":
        abort(400)
    new_pw = request.form.get("new_password", "").strip()
    if len(new_pw) < 6:
        flash("Password must be at least 6 characters.", "danger")
        return redirect(url_for("teachers"))
    u.set_password(new_pw)
    u.must_change_password = True
    db.session.commit()
    flash(f"Password reset for {u.full_name}. They must change it on next login.", "success")
    return redirect(url_for("teachers"))


# ---------------- Fees (Admin only) ----------------
@app.route("/fees")
@role_required("admin")
def fees():
    status_filter = request.args.get("status", "").strip()
    class_filter = request.args.get("class_name", "").strip()
    section_filter = request.args.get("section", "").strip()

    query = (
        db.session.query(Fee, Student)
        .join(Student, Fee.student_id == Student.id)
    )
    if status_filter in ("Paid", "Unpaid"):
        query = query.filter(Fee.status == status_filter)
    if class_filter:
        query = query.filter(Student.class_name == class_filter)
    if section_filter:
        query = query.filter(Student.section == section_filter)
    rows = query.order_by(Fee.created_at.desc()).all()

    # Totals respect class/section filter (so admin can see "this class' totals"),
    # but ignore status filter so the three cards stay meaningful.
    totals_query = db.session.query(db.func.coalesce(db.func.sum(Fee.amount), 0)).join(
        Student, Fee.student_id == Student.id
    )
    if class_filter:
        totals_query = totals_query.filter(Student.class_name == class_filter)
    if section_filter:
        totals_query = totals_query.filter(Student.section == section_filter)
    total = totals_query.scalar() or 0
    base_q = totals_query
    paid = base_q.filter(Fee.status == "Paid").scalar() or 0
    unpaid = base_q.filter(Fee.status == "Unpaid").scalar() or 0

    students_list = Student.query.order_by(Student.class_name, Student.section, Student.name).all()

    # Recent 10 paid transactions
    recent_txns = (
        db.session.query(Fee, Student)
        .join(Student, Fee.student_id == Student.id)
        .filter(Fee.status == "Paid")
        .order_by(Fee.paid_on.desc().nullslast(), Fee.created_at.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "fees.html",
        rows=rows, students=students_list,
        total=total, paid=paid, unpaid=unpaid,
        status_filter=status_filter,
        class_filter=class_filter, section_filter=section_filter,
        recent_txns=recent_txns,
    )


@app.route("/fees/new", methods=["POST"])
@role_required("admin")
def fee_new():
    try:
        sid = int(request.form["student_id"])
        title = request.form["title"].strip()
        amount = float(request.form["amount"])
        initial_status = request.form.get("initial_status", "Unpaid").strip()
        if initial_status not in ("Paid", "Unpaid"):
            initial_status = "Unpaid"
        mode = (request.form.get("mode") or "").strip() or None
        if mode and mode not in PAYMENT_MODES:
            mode = None
        paid_on = None
        if initial_status == "Paid":
            paid_on_str = (request.form.get("paid_on") or "").strip()
            if paid_on_str:
                try:
                    paid_on = datetime.strptime(paid_on_str, "%Y-%m-%d")
                except ValueError:
                    paid_on = datetime.utcnow()
            else:
                paid_on = datetime.utcnow()

        f = Fee(student_id=sid, title=title, amount=amount, mode=mode,
                status=initial_status, paid_on=paid_on)
        db.session.add(f)
        db.session.commit()
        flash("Bill added.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Could not add bill: {e}", "danger")
    return redirect(url_for("fees"))


@app.route("/fees/<int:fid>/toggle", methods=["POST"])
@role_required("admin")
def fee_toggle(fid):
    f = db.session.get(Fee, fid) or abort(404)
    if f.status == "Paid":
        f.status = "Unpaid"
        f.paid_on = None
        f.mode = None
        flash("Bill marked as unpaid.", "info")
    else:
        mode = (request.form.get("mode") or "").strip() or None
        if mode and mode not in PAYMENT_MODES:
            mode = None
        paid_on_str = (request.form.get("paid_on") or "").strip()
        if paid_on_str:
            try:
                paid_on = datetime.strptime(paid_on_str, "%Y-%m-%d")
            except ValueError:
                paid_on = datetime.utcnow()
        else:
            paid_on = datetime.utcnow()
        f.status = "Paid"
        f.paid_on = paid_on
        f.mode = mode
        flash("Bill marked as paid.", "success")
    db.session.commit()
    return redirect(url_for("fees", status=request.args.get("status", "")))


@app.route("/fees/<int:fid>/delete", methods=["POST"])
@role_required("admin")
def fee_delete(fid):
    f = db.session.get(Fee, fid) or abort(404)
    db.session.delete(f)
    db.session.commit()
    flash("Bill deleted.", "info")
    return redirect(url_for("fees"))


# ---------------- Errors ----------------
@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, msg="You don't have permission to access this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, msg="Page not found."), 404


# ---------------- Bootstrap ----------------
def migrate():
    """Lightweight schema migration for SQLite (adds missing columns)."""
    with db.engine.connect() as conn:
        # New tables for attendance requests and audit log
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS attendance_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES users(id),
                request_date DATE NOT NULL,
                reason VARCHAR(250) NOT NULL,
                request_type VARCHAR(20) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'Pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS attendance_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL REFERENCES users(id),
                attendance_date DATE NOT NULL,
                action VARCHAR(20) NOT NULL,
                edit_count INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                approved_by_request INTEGER REFERENCES attendance_requests(id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS marks_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                requester_id INTEGER NOT NULL REFERENCES users(id),
                class_name VARCHAR(40) NOT NULL,
                exam VARCHAR(20) NOT NULL,
                subject VARCHAR(80) NOT NULL,
                reason VARCHAR(250) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'Pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS marks_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                class_name VARCHAR(40) NOT NULL,
                exam VARCHAR(20) NOT NULL,
                subject VARCHAR(80) NOT NULL,
                action VARCHAR(20) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                approved_by_request INTEGER REFERENCES marks_requests(id)
            )
        """))
        conn.commit()
        ucols = [r[1] for r in conn.execute(text("PRAGMA table_info(users)")).fetchall()]
        if "must_change_password" not in ucols:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0"
            ))
        scols = [r[1] for r in conn.execute(text("PRAGMA table_info(students)")).fetchall()]
        if "section" not in scols:
            conn.execute(text("ALTER TABLE students ADD COLUMN section VARCHAR(20)"))
        fcols = [r[1] for r in conn.execute(text("PRAGMA table_info(fees)")).fetchall()]
        if "mode" not in fcols:
            conn.execute(text("ALTER TABLE fees ADD COLUMN mode VARCHAR(30)"))
        # New teacher profile columns
        if "phone" not in ucols:
            conn.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(20)"))
        if "address" not in ucols:
            conn.execute(text("ALTER TABLE users ADD COLUMN address VARCHAR(250)"))
        if "subject_assignment" not in ucols:
            conn.execute(text("ALTER TABLE users ADD COLUMN subject_assignment VARCHAR(250)"))
        if "last_login" not in ucols:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_login DATETIME"))
        if "assigned_class" not in ucols:
            conn.execute(text("ALTER TABLE users ADD COLUMN assigned_class VARCHAR(40)"))
        if "assigned_section" not in ucols:
            conn.execute(text("ALTER TABLE users ADD COLUMN assigned_section VARCHAR(20)"))
        conn.commit()


def seed():
    with app.app_context():
        db.create_all()
        migrate()
        if not User.query.filter_by(username="admin").first():
            admin = User(username="admin", full_name="Principal", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)
        if not User.query.filter_by(username="teacher").first():
            teacher = User(username="teacher", full_name="Default Teacher", role="teacher")
            teacher.set_password("teacher123")
            db.session.add(teacher)
        db.session.commit()


seed()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)