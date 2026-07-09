import csv
from pathlib import Path

from line_revenue_bot.config import get_settings
from line_revenue_bot.db import Repository


def main() -> None:
    settings = get_settings()
    repo = Repository(settings)
    rows = repo.list_leads(limit=1000)
    out_dir = Path("artifacts")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "leads.csv"
    fields = ["id", "tenant_id", "line_user_id", "last_message", "category", "score", "status", "followup_due_at", "second_followup_due_at", "created_at", "updated_at"]
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    print(f"exported {len(rows)} leads to {out_path}")


if __name__ == "__main__":
    main()
