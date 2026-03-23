import json
import logging
import os
from datetime import datetime

HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "storage", "history.json"
)

log = logging.getLogger("hh_bot")


class ApplicationHistory:
    def __init__(self, path: str = HISTORY_PATH):
        self.path = path
        self.data: dict = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Не удалось загрузить историю: %s", e)
            return {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def is_applied(self, vacancy_id: str) -> bool:
        entry = self.data.get(str(vacancy_id))
        if not entry:
            return False
        status = entry.get("status", "")
        return status in ("applied", "already_applied")

    def record(
        self,
        vacancy_id: str,
        title: str,
        employer: str,
        url: str,
        status: str,
        cover_letter: str = "",
    ) -> None:
        self.data[str(vacancy_id)] = {
            "title": title,
            "employer": employer,
            "url": url,
            "applied_at": datetime.now().isoformat(),
            "status": status,
            "cover_letter_preview": cover_letter[:200] if cover_letter else "",
        }
        self._save()

    def get_stats(self) -> dict:
        total = len(self.data)
        applied = sum(1 for v in self.data.values() if v["status"] == "applied")
        errors = sum(1 for v in self.data.values() if v["status"].startswith("error"))
        skipped = total - applied - errors
        return {"total": total, "applied": applied, "skipped": skipped, "errors": errors}
