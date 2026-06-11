"""Database models: User and Activity."""
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    # Nullable until a Google-only user picks one.
    username = db.Column(db.String(80), unique=True, nullable=True, index=True)
    # Nullable for accounts created purely via Google.
    password_hash = db.Column(db.String(255), nullable=True)
    google_sub = db.Column(db.String(255), unique=True, nullable=True, index=True)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    # ---- Subscription / billing ----
    plan = db.Column(db.String(20), nullable=False, default="free")  # 'free' | 'pro'
    # Admin-granted free Pro access (a "comp").
    comped = db.Column(db.Boolean, nullable=False, default=False)
    stripe_customer_id = db.Column(db.String(120), nullable=True, index=True)
    stripe_subscription_id = db.Column(db.String(120), nullable=True, index=True)
    # Stripe subscription status: active, trialing, past_due, canceled, etc.
    subscription_status = db.Column(db.String(40), nullable=True)
    subscription_current_period_end = db.Column(db.DateTime, nullable=True)

    activities = db.relationship(
        "Activity", backref="user", cascade="all, delete-orphan", lazy="dynamic"
    )

    _ACTIVE_SUB_STATUSES = ("active", "trialing")

    @property
    def has_active_subscription(self) -> bool:
        return (self.subscription_status or "") in self._ACTIVE_SUB_STATUSES

    @property
    def is_pro(self) -> bool:
        """Effective Pro access: paid subscription, an admin comp, or admin."""
        return bool(self.has_active_subscription or self.comped or self.is_admin)

    def upload_count(self) -> int:
        """Number of manually-uploaded activities (Garmin sync doesn't count)."""
        return self.activities.filter_by(source="upload").count()

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email}>"


class Activity(db.Model):
    __tablename__ = "activities"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    # 'upload' | 'garmin'
    source = db.Column(db.String(20), nullable=False, default="upload")
    # External provider id, used for dedupe on synced activities.
    external_id = db.Column(db.String(120), nullable=True, index=True)

    type = db.Column(db.String(60), nullable=True)
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    duration_s = db.Column(db.Integer, nullable=False, default=0)
    distance_m = db.Column(db.Float, nullable=True)
    avg_hr = db.Column(db.Integer, nullable=True)
    max_hr = db.Column(db.Integer, nullable=True)
    # Canonical pace stored as seconds per kilometre.
    avg_pace = db.Column(db.Float, nullable=True)
    elevation_gain_m = db.Column(db.Float, nullable=True)
    raw_path = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    def __repr__(self) -> str:
        return f"<Activity {self.id} {self.type} {self.start_time}>"

    # ---- view helpers ----
    @property
    def distance_km(self) -> float | None:
        return round(self.distance_m / 1000, 2) if self.distance_m else None

    @property
    def duration_hms(self) -> str:
        s = int(self.duration_s or 0)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

    @property
    def pace_label(self) -> str | None:
        """Format seconds/km as 'm:ss /km'."""
        if not self.avg_pace:
            return None
        m, s = divmod(int(round(self.avg_pace)), 60)
        return f"{m}:{s:02d} /km"


class GarminToken(db.Model):
    """OAuth 2.0 tokens for a user's linked Garmin Connect account."""

    __tablename__ = "garmin_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False, index=True
    )
    # Garmin's stable user identifier — maps incoming webhooks to our user.
    garmin_user_id = db.Column(db.String(120), unique=True, nullable=True, index=True)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)
    token_type = db.Column(db.String(40), nullable=True, default="Bearer")
    scope = db.Column(db.String(255), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    refresh_expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    user = db.relationship("User", backref=db.backref("garmin", uselist=False))

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        now = now or _utcnow()
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return now >= exp

    def __repr__(self) -> str:
        return f"<GarminToken user={self.user_id} garmin={self.garmin_user_id}>"


class SupportTicket(db.Model):
    """A question the chatbot couldn't answer, escalated to the team's inbox."""

    __tablename__ = "support_tickets"

    id = db.Column(db.Integer, primary_key=True)
    # Nullable: anonymous visitors (e.g. on the login page) can ask too.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    email = db.Column(db.String(255), nullable=True)
    question = db.Column(db.Text, nullable=False)
    # The bot's best-effort reply (or note) at escalation time.
    bot_reply = db.Column(db.Text, nullable=True)
    resolved = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    user = db.relationship("User")

    def __repr__(self) -> str:
        return f"<SupportTicket {self.id} resolved={self.resolved}>"
