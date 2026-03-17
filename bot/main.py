import os
import signal
import sys
import time

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from bot.applier import run_auto_apply
from bot.browser import update_resumes
from bot.logger import setup_logger

load_dotenv()

log = setup_logger()

# Флаг для graceful shutdown
_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    log.info("Получен сигнал %s — завершаем работу", signal.Signals(signum).name)
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def main():
    username = os.getenv("HH_LOGIN", "")
    password = os.getenv("HH_PASSWORD", "")
    interval_hours = int(os.getenv("UPDATE_INTERVAL_HOURS", "4"))
    run_mode = os.getenv("RUN_MODE", "both").lower()

    # Параметры автоотклика
    search_url = os.getenv("HH_SEARCH_URL", "")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    max_applications = int(os.getenv("MAX_APPLICATIONS", "50"))
    claude_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    resume_summary = os.getenv("RESUME_SUMMARY", "")
    resume_id = os.getenv("HH_RESUME_ID", "")
    cover_letter = os.getenv("COVER_LETTER", "")

    if not username or not password:
        log.error("HH_LOGIN и HH_PASSWORD должны быть заданы в .env")
        sys.exit(1)

    if run_mode in ("apply", "both") and not search_url:
        log.error("HH_SEARCH_URL должен быть задан в .env для режима автоотклика")
        sys.exit(1)

    if run_mode in ("apply", "both") and not anthropic_api_key and not cover_letter:
        log.warning("Ни ANTHROPIC_API_KEY, ни COVER_LETTER не заданы — отклики будут без сопроводительного письма")

    interval_seconds = interval_hours * 3600
    log.info("Запуск бота. Режим: %s, интервал: %d ч.", run_mode, interval_hours)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="ru-RU",
        )
        page = context.new_page()

        while not _shutdown:
            try:
                # Режим поднятия резюме
                if run_mode in ("update", "both"):
                    update_resumes(context, page, username, password)

                # Режим автоотклика
                if run_mode in ("apply", "both"):
                    run_auto_apply(
                        context=context,
                        page=page,
                        username=username,
                        password=password,
                        search_url=search_url,
                        anthropic_api_key=anthropic_api_key,
                        resume_summary=resume_summary,
                        max_applications=max_applications,
                        claude_model=claude_model,
                        resume_id=resume_id,
                        static_cover_letter=cover_letter,
                    )
            except Exception:
                log.exception("Непредвиденная ошибка при выполнении")

            log.info("Следующий запуск через %d ч.", interval_hours)

            # Спим интервалами по 10 секунд для быстрого отклика на shutdown
            elapsed = 0
            while elapsed < interval_seconds and not _shutdown:
                time.sleep(10)
                elapsed += 10

        log.info("Бот остановлен")
        browser.close()


if __name__ == "__main__":
    main()
