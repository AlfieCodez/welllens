"""Shared extension singletons, initialised in the app factory."""
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from authlib.integrations.flask_client import OAuth

db = SQLAlchemy()
csrf = CSRFProtect()
oauth = OAuth()
