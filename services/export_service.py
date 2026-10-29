"""
T.A.G.A.P. - Export Service

Handles CSV exports for research analytics.
"""

import csv
from pathlib import Path
from data.database import get_db
from models import Alert, SmsQueue, Analytics

EXPORT_DIR = Path("data/exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def export_analytics_csv() -> Path:
    """Exports all alerts and delivery timings to a CSV."""
    file_path = EXPORT_DIR / "tagap_analytics.csv"

    with get_db() as db, open(file_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Alert ID", "Card Type", "Triggered At", "Response Time (ms)", "Delivery Time (ms)"
        ])

        analytics_rows = db.query(Analytics).all()
        for row in analytics_rows:
            alert = db.query(Alert).get(row.alert_id)
            writer.writerow([
                row.alert_id,
                alert.card_type,
                row.scan_ts,
                row.response_time_ms,
                row.delivery_time_ms
            ])

    return file_path