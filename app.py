import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import wraps

from flask import (
    Flask, render_template, redirect, url_for, request, flash,
    send_file, abort, current_app
)
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user, login_required, current_user
)
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import UniqueConstraint
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, Regexp

ROOT = Path(__file__).resolve().parent
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-this-secret-before-sharing")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", f"sqlite:///{(ROOT / 'cloudbox.db').as_posix()}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB per upload
app.config["UPLOAD_ROOT"] = os.environ.get("UPLOAD_ROOT", str(ROOT / "storage"))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["REMEMBER_COOKIE_HTTPONLY"] = True

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to access CloudBox."
login_manager.login_message_category = "info"

ALLOWED_EXTENSIONS = {
    "pdf", "txt", "md", "csv", "png", "jpg", "jpeg", "gif", "webp",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx", "zip", "json"
}
MAX_SHARE_DAYS = 30


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("folder.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "parent_id", "name", name="uq_folder_sibling"),)


class StoredFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    folder_id = db.Column(db.Integer, db.ForeignKey("folder.id"), nullable=True, index=True)
    original_name = db.Column(db.String(255), nullable=False)
    storage_name = db.Column(db.String(80), nullable=False, unique=True)
    size = db.Column(db.Integer, nullable=False, default=0)
    uploaded_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class ShareLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey("stored_file.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    token = db.Column(db.String(96), unique=True, nullable=False, index=True)
    permission = db.Column(db.String(16), nullable=False, default="download")
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class RegisterForm(FlaskForm):
    username = StringField("Username", validators=[
        DataRequired(), Length(min=3, max=32),
        Regexp(r"^[A-Za-z0-9_.-]+$", message="Use letters, numbers, dots, underscores or hyphens.")
    ])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=10, max=128)])
    confirm = PasswordField("Confirm password", validators=[
        DataRequired(), EqualTo("password", message="Passwords must match.")
    ])
    submit = SubmitField("Create account")


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(max=32)])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Sign in")


class FolderForm(FlaskForm):
    name = StringField("Folder name", validators=[
        DataRequired(), Length(min=1, max=80),
        Regexp(r"^[^/\\\\<>:\"|?*\x00-\x1f]+$", message="Choose a folder name without path or reserved characters.")
    ])
    submit = SubmitField("Create folder")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def ensure_user_storage(user_id):
    Path(app.config["UPLOAD_ROOT"], str(user_id)).mkdir(parents=True, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def owned_file(file_id):
    item = db.session.get(StoredFile, file_id)
    if item is None or item.user_id != current_user.id:
        abort(404)
    return item


def owned_folder(folder_id):
    if folder_id is None:
        return None
    folder = db.session.get(Folder, folder_id)
    if folder is None or folder.user_id != current_user.id:
        abort(404)
    return folder


def readable_size(size):
    amount = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if amount < 1024 or unit == "GB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.1f} GB"


@app.context_processor
def inject_helpers():
    return {"readable_size": readable_size, "now": utcnow()}


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        if User.query.filter_by(username=username).first():
            flash("That username is already taken.", "error")
        else:
            user = User(username=username)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            ensure_user_storage(user.id)
            login_user(user)
            flash("Welcome to CloudBox. Your private space is ready.", "success")
            return redirect(url_for("dashboard"))
    return render_template("auth.html", form=form, mode="register")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash("Welcome back.", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("auth.html", form=form, mode="login")


@app.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have signed out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    folder_id = request.args.get("folder", type=int)
    folder = owned_folder(folder_id)
    files_query = StoredFile.query.filter_by(user_id=current_user.id, folder_id=folder_id)
    files = files_query.order_by(StoredFile.uploaded_at.desc()).all()
    folders_query = Folder.query.filter_by(user_id=current_user.id, parent_id=folder_id)
    folders = folders_query.order_by(Folder.name.asc()).all()
    total_files = StoredFile.query.filter_by(user_id=current_user.id).count()
    total_bytes = db.session.query(db.func.coalesce(db.func.sum(StoredFile.size), 0)).filter_by(
        user_id=current_user.id
    ).scalar()
    total_folders = Folder.query.filter_by(user_id=current_user.id).count()
    recent_files = StoredFile.query.filter_by(user_id=current_user.id).order_by(
        StoredFile.uploaded_at.desc()
    ).limit(5).all()
    folder_form = FolderForm()
    breadcrumbs = []
    cursor = folder
    while cursor:
        breadcrumbs.append(cursor)
        cursor = db.session.get(Folder, cursor.parent_id) if cursor.parent_id else None
    breadcrumbs.reverse()
    return render_template(
        "dashboard.html", files=files, folders=folders, folder=folder,
        folder_form=folder_form, total_files=total_files, total_bytes=total_bytes,
        total_folders=total_folders, recent_files=recent_files, breadcrumbs=breadcrumbs
    )


@app.post("/folders/create")
@login_required
def create_folder():
    form = FolderForm()
    folder_id = request.form.get("parent_id", type=int)
    parent = owned_folder(folder_id)
    if not form.validate_on_submit():
        flash("Please enter a valid folder name.", "error")
        return redirect(url_for("dashboard", folder=folder_id) if folder_id else url_for("dashboard"))
    name = form.name.data.strip()
    if Folder.query.filter_by(user_id=current_user.id, parent_id=folder_id, name=name).first():
        flash("A folder with that name already exists here.", "error")
    else:
        db.session.add(Folder(user_id=current_user.id, parent_id=folder_id, name=name))
        db.session.commit()
        flash(f"Folder “{name}” created.", "success")
    return redirect(url_for("dashboard", folder=folder_id) if folder_id else url_for("dashboard"))


@app.post("/folders/<int:folder_id>/delete")
@login_required
def delete_folder(folder_id):
    folder = owned_folder(folder_id)
    # Do not allow deleting non-empty folders; this avoids accidental recursive deletion.
    if StoredFile.query.filter_by(user_id=current_user.id, folder_id=folder.id).first() or Folder.query.filter_by(
        user_id=current_user.id, parent_id=folder.id
    ).first():
        flash("Move or delete the folder's contents first.", "error")
    else:
        db.session.delete(folder)
        db.session.commit()
        flash("Folder deleted.", "success")
    return redirect(url_for("dashboard", folder=folder.parent_id) if folder.parent_id else url_for("dashboard"))


@app.post("/upload")
@login_required
def upload():
    folder_id = request.form.get("folder_id", type=int)
    owned_folder(folder_id)
    upload_files = request.files.getlist("files")
    if not upload_files or all(not f.filename for f in upload_files):
        flash("Choose at least one file to upload.", "error")
        return redirect(url_for("dashboard", folder=folder_id) if folder_id else url_for("dashboard"))
    ensure_user_storage(current_user.id)
    saved = 0
    for incoming in upload_files:
        if not incoming or not incoming.filename:
            continue
        safe_name = secure_filename(incoming.filename)
        if not safe_name or not allowed_file(safe_name):
            flash(f"Skipped {incoming.filename!r}: file type is not allowed.", "error")
            continue
        storage_name = secrets.token_hex(24)
        destination = Path(app.config["UPLOAD_ROOT"], str(current_user.id), storage_name)
        incoming.save(destination)
        item = StoredFile(
            user_id=current_user.id, folder_id=folder_id,
            original_name=safe_name[:255], storage_name=storage_name,
            size=destination.stat().st_size
        )
        db.session.add(item)
        saved += 1
    db.session.commit()
    if saved:
        flash(f"Uploaded {saved} file(s).", "success")
    return redirect(url_for("dashboard", folder=folder_id) if folder_id else url_for("dashboard"))


@app.get("/files/<int:file_id>/download")
@login_required
def download(file_id):
    item = owned_file(file_id)
    path = Path(app.config["UPLOAD_ROOT"], str(current_user.id), item.storage_name)
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=item.original_name)


@app.post("/files/<int:file_id>/delete")
@login_required
def delete_file(file_id):
    item = owned_file(file_id)
    path = Path(app.config["UPLOAD_ROOT"], str(current_user.id), item.storage_name)
    if path.is_file():
        path.unlink()
    ShareLink.query.filter_by(file_id=item.id, user_id=current_user.id).delete()
    folder_id = item.folder_id
    db.session.delete(item)
    db.session.commit()
    flash("File deleted.", "success")
    return redirect(url_for("dashboard", folder=folder_id) if folder_id else url_for("dashboard"))


@app.post("/files/<int:file_id>/share")
@login_required
def create_share(file_id):
    item = owned_file(file_id)
    permission = request.form.get("permission", "download")
    if permission not in {"view", "download"}:
        permission = "download"
    days = request.form.get("days", type=int) or 7
    days = max(1, min(days, MAX_SHARE_DAYS))
    token = secrets.token_urlsafe(32)
    link = ShareLink(
        file_id=item.id, user_id=current_user.id, token=token,
        permission=permission, expires_at=utcnow() + timedelta(days=days)
    )
    db.session.add(link)
    db.session.commit()
    flash(f"Share link created: {url_for('shared_file', token=token, _external=True)}", "success")
    return redirect(url_for("dashboard", folder=item.folder_id) if item.folder_id else url_for("dashboard"))


@app.route("/shares")
@login_required
def shares():
    links = ShareLink.query.filter_by(user_id=current_user.id).order_by(ShareLink.created_at.desc()).all()
    return render_template("shares.html", links=links)


@app.post("/shares/<int:share_id>/revoke")
@login_required
def revoke_share(share_id):
    link = ShareLink.query.filter_by(id=share_id, user_id=current_user.id).first_or_404()
    link.revoked = True
    db.session.commit()
    flash("Share link revoked.", "success")
    return redirect(url_for("shares"))


@app.get("/s/<token>")
def shared_file(token):
    link = ShareLink.query.filter_by(token=token).first_or_404()
    if link.revoked or link.expires_at <= utcnow():
        return render_template("share_unavailable.html"), 410
    item = db.session.get(StoredFile, link.file_id)
    if item is None:
        abort(404)
    path = Path(app.config["UPLOAD_ROOT"], str(item.user_id), item.storage_name)
    if not path.is_file():
        abort(404)
    if request.args.get("download") == "1":
        if link.permission != "download":
            abort(403)
        return send_file(path, as_attachment=True, download_name=item.original_name)
    return render_template("shared_file.html", link=link, item=item)


@app.errorhandler(413)
def too_large(_error):
    flash("That upload exceeds the 25 MB per-request limit.", "error")
    return redirect(url_for("dashboard"))


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    return response


with app.app_context():
    db.create_all()
    Path(app.config["UPLOAD_ROOT"]).mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
