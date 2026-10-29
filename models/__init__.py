"""T.A.G.A.P. models package — imports all models so Base.metadata is complete."""

from models.alert import Alert
from models.analytics import Analytics
from models.audit_log import AuditLog
from models.base import Base, TimestampMixin
from models.card import Card
from models.parent import Parent
from models.police_station import PoliceStation
from models.room import Room
from models.school import School
from models.sms_queue import SmsQueue
from models.sms_template import SmsTemplate
from models.student import Student
from models.student_parent import student_parents

__all__ = [
    "Alert",
    "Analytics",
    "AuditLog",
    "Base",
    "Card",
    "Parent",
    "PoliceStation",
    "Room",
    "School",
    "SmsQueue",
    "SmsTemplate",
    "Student",
    "TimestampMixin",
    "student_parents",
]