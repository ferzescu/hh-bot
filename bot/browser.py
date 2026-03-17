import logging

from playwright.sync_api import BrowserContext, Page

from bot.auth import RESUMES_URL, ensure_logged_in, save_cookies

log = logging.getLogger("hh_bot")


def update_resumes(
    context: BrowserContext, page: Page, username: str, password: str
) -> bool:
    """Обновляет (поднимает) все резюме пользователя на hh.ru."""
    if not ensure_logged_in(context, page, username, password):
        log.error("Не удалось авторизоваться — пропускаем обновление")
        return False

    # Переходим на страницу резюме
    page.goto(RESUMES_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    # Ищем кнопки «Поднять в поиске»
    raise_buttons = page.locator('[data-qa="resume-update-button"]')
    count = raise_buttons.count()

    if count == 0:
        log.info("Кнопок «Поднять в поиске» не найдено — возможно ещё рано")
        _log_next_update_time(page)
        return True

    updated = 0
    for i in range(count):
        btn = raise_buttons.nth(i)
        resume_title = _get_resume_title(page, i)

        try:
            btn.scroll_into_view_if_needed()
            btn.click()
            page.wait_for_timeout(2000)
            log.info('Резюме "%s" — обновлено', resume_title)
            updated += 1
        except Exception as e:
            log.warning('Резюме "%s" — ошибка при обновлении: %s', resume_title, e)

    save_cookies(context)
    log.info("Обновлено резюме: %d из %d", updated, count)
    return updated > 0


def _get_resume_title(page: Page, index: int) -> str:
    """Пытается получить название резюме по индексу."""
    try:
        titles = page.locator('[data-qa="resume-title"]')
        if titles.count() > index:
            return titles.nth(index).inner_text().strip()
    except Exception:
        pass
    return f"#{index + 1}"


def _log_next_update_time(page: Page) -> None:
    """Логирует время до следующего доступного обновления, если есть на странице."""
    try:
        timer = page.locator('[data-qa="resume-update-timer"]')
        if timer.count() > 0:
            text = timer.first.inner_text().strip()
            log.info("Следующее обновление доступно: %s", text)
    except Exception:
        pass
