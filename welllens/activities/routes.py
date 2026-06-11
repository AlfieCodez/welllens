"""Activity upload and listing."""
import uuid
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename

from ..auth.helpers import current_user, login_required
from .parsing import ActivityParseError, parse_file
from .service import save_parsed_activity

activities_bp = Blueprint("activities", __name__)


@activities_bp.route("/upload", methods=["GET"])
@login_required
def upload():
    user = current_user()
    free_info = None
    if not user.is_pro:
        limit = current_app.config["FREE_UPLOAD_LIMIT"]
        free_info = {"used": user.upload_count(), "limit": limit}
    return render_template("upload.html", user=user, free_info=free_info)


@activities_bp.route("/upload", methods=["POST"])
@login_required
def upload_post():
    user = current_user()
    files = request.files.getlist("activity")
    files = [f for f in files if f and f.filename]
    if not files:
        flash("Please choose at least one file to upload.", "error")
        return redirect(url_for("activities.upload"))

    # Free-tier upload cap. Pro / comped / admin are unlimited.
    remaining = None
    if not user.is_pro:
        limit = current_app.config["FREE_UPLOAD_LIMIT"]
        remaining = limit - user.upload_count()
        if remaining <= 0:
            flash(
                f"You've reached the free limit of {limit} uploads. "
                "Upgrade to Pro for unlimited uploads.",
                "error",
            )
            return redirect(url_for("billing.index"))

    allowed = current_app.config["ALLOWED_EXTENSIONS"]
    added, skipped, failed = 0, 0, []
    limit_hit = False

    for file in files:
        # Stop accepting new activities once a free user hits their cap.
        if remaining is not None and added >= remaining:
            limit_hit = True
            break

        filename = secure_filename(file.filename)
        ext = Path(filename).suffix.lower()
        if ext not in allowed:
            failed.append(f"{filename}: unsupported type (use .fit, .gpx or .tcx).")
            continue

        stored_name = f"{uuid.uuid4().hex}{ext}"
        dest = Path(current_app.config["UPLOAD_DIR"]) / stored_name
        file.save(dest)

        try:
            parsed = parse_file(dest)
        except ActivityParseError as exc:
            dest.unlink(missing_ok=True)
            failed.append(f"{filename}: {exc}")
            continue
        except Exception:  # noqa: BLE001
            dest.unlink(missing_ok=True)
            failed.append(f"{filename}: couldn't read this file.")
            continue

        _activity, created = save_parsed_activity(
            user.id, parsed, source="upload", raw_path=str(dest)
        )
        if created:
            added += 1
        else:
            dest.unlink(missing_ok=True)  # don't keep duplicate raw file
            skipped += 1

    _flash_summary(added, skipped, failed)
    if limit_hit:
        flash(
            "Some files weren't added — you've hit the free upload limit. "
            "Upgrade to Pro for unlimited uploads.",
            "info",
        )
    if added:
        return redirect(url_for("dashboard.index"))
    if limit_hit:
        return redirect(url_for("billing.index"))
    return redirect(url_for("activities.upload"))


def _flash_summary(added: int, skipped: int, failed: list[str]) -> None:
    if added:
        flash(f"Added {added} new {_plural(added, 'activity', 'activities')}.", "success")
    if skipped:
        flash(
            f"Skipped {skipped} {_plural(skipped, 'duplicate', 'duplicates')} "
            "already in your history.",
            "info",
        )
    for msg in failed:
        flash(msg, "error")


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many
