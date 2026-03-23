import logging
import random
import time

from playwright.sync_api import BrowserContext, Page

from bot.auth import ensure_logged_in, save_cookies
from bot.cover_letter import generate_cover_letter
from bot.history import ApplicationHistory
from bot.vacancy_search import get_vacancy_description, search_vacancies

log = logging.getLogger("hh_bot")


def run_auto_apply(
    context: BrowserContext,
    page: Page,
    username: str,
    password: str,
    search_url: str,
    anthropic_api_key: str,
    resume_summary: str,
    max_applications: int = 50,
    claude_model: str = "claude-sonnet-4-20250514",
    resume_id: str = "",
    static_cover_letter: str = "",
) -> None:
    """
    Основной пайплайн автоотклика:
    1. Авторизация
    2. Поиск вакансий по URL
    3. Для каждой: генерация cover letter + отклик
    """
    if not ensure_logged_in(context, page, username, password):
        log.error("Не удалось авторизоваться — автоотклик невозможен")
        return

    log.info("Начинаю поиск вакансий по URL: %s", search_url)
    vacancies = search_vacancies(page, search_url)

    if not vacancies:
        log.info("Вакансий не найдено")
        return

    history = ApplicationHistory()
    stats = history.get_stats()
    log.info("История: %d записей (%d откликов, %d пропущено)",
             stats["total"], stats["applied"], stats["skipped"])

    applied_count = 0
    skipped_count = 0
    error_count = 0

    for vacancy in vacancies:
        vacancy_id = vacancy["id"]
        title = vacancy["title"]
        employer = vacancy["employer"]
        url = vacancy["url"]

        # Дедупликация
        if history.is_applied(vacancy_id):
            log.debug("Пропуск (уже обработано): %s @ %s", title, employer)
            skipped_count += 1
            continue

        # Лимит откликов
        if applied_count >= max_applications:
            log.info("Достигнут лимит откликов (%d). Останавливаюсь.", max_applications)
            break

        log.info("Обработка: %s @ %s (ID: %s)", title, employer, vacancy_id)

        try:
            # Получаем описание вакансии для cover letter
            description = get_vacancy_description(page, url)

            # Сопроводительное письмо: статическое > Claude API > пустое
            cover_letter = ""
            if static_cover_letter:
                cover_letter = static_cover_letter
            elif anthropic_api_key:
                cover_letter = generate_cover_letter(
                    vacancy_title=title,
                    employer=employer,
                    description=description,
                    resume_summary=resume_summary,
                    api_key=anthropic_api_key,
                    model=claude_model,
                )

            # Откликаемся
            result = _apply_to_vacancy(page, cover_letter, resume_id)

            if result == "applied":
                log.info("  ОТКЛИК отправлен")
                history.record(vacancy_id, title, employer, url, "applied", cover_letter)
                applied_count += 1
                save_cookies(context)
            elif result == "already_applied":
                log.info("  Уже откликались ранее")
                history.record(vacancy_id, title, employer, url, "already_applied")
                skipped_count += 1
            else:
                log.warning("  Ошибка отклика: %s", result)
                history.record(vacancy_id, title, employer, url, f"error: {result}")
                error_count += 1

            # Задержка между откликами (2-6 секунд)
            delay = random.uniform(2, 6)
            time.sleep(delay)

        except Exception as e:
            log.exception("  Непредвиденная ошибка для вакансии %s: %s", vacancy_id, e)
            history.record(vacancy_id, title, employer, url, f"error: {e}")
            error_count += 1

    # Итоговая статистика
    log.info("=" * 50)
    log.info("Автоотклик завершён!")
    log.info("  Откликов: %d", applied_count)
    log.info("  Пропущено: %d", skipped_count)
    log.info("  Ошибок: %d", error_count)
    log.info("=" * 50)


def _apply_to_vacancy(page: Page, cover_letter: str, resume_id: str = "") -> str:
    """
    Откликается на вакансию, которая уже открыта в page.

    Возвращает: "applied", "already_applied", или строку с описанием ошибки.
    """
    # Ждём загрузки страницы вакансии
    try:
        page.locator(
            '[data-qa="vacancy-response-link-top"], '
            '[data-qa="vacancy-response-link-top-quick"]'
        ).or_(
            page.get_by_text("Откликнуться", exact=True)
        ).or_(
            page.get_by_text("Вы уже откликнулись")
        ).first.wait_for(timeout=10000)
    except Exception:
        current_url = page.url
        log.warning("  Кнопка отклика не найдена. URL: %s", current_url)
        page.screenshot(path="/app/storage/debug_no_apply.png")
        return "no_apply_button"

    # Проверяем, не откликались ли уже
    responded = page.get_by_text("Вы уже откликнулись")
    if responded.count() > 0:
        return "already_applied"

    # Ищем кнопку «Откликнуться» по data-qa
    respond_btn = page.locator('[data-qa="vacancy-response-link-top"]')
    if respond_btn.count() == 0:
        respond_btn = page.locator('[data-qa="vacancy-response-link-top-quick"]')
    # Фоллбек: ищем по тексту кнопки
    if respond_btn.count() == 0:
        respond_btn = page.get_by_text("Откликнуться", exact=True)
    if respond_btn.count() == 0:
        page.screenshot(path="/app/storage/debug_no_apply.png")
        return "no_apply_button"

    respond_btn.first.scroll_into_view_if_needed()
    respond_btn.first.click(force=True)
    page.wait_for_timeout(2000)

    # Модальное окно отклика
    # Шаг 1: Выбор резюме (если есть несколько)
    _select_resume(page, resume_id)

    # Шаг 2: Заполнение сопроводительного письма
    if cover_letter:
        _fill_cover_letter(page, cover_letter)

    # Шаг 3: Отправка
    submit_btn = page.locator('[data-qa="vacancy-response-submit-popup"]')
    if submit_btn.count() > 0:
        submit_btn.first.click()
        page.wait_for_timeout(2000)
    else:
        # Альтернативная кнопка отправки
        alt_submit = page.locator('[data-qa="vacancy-response-letter-submit"]')
        if alt_submit.count() > 0:
            alt_submit.first.click()
            page.wait_for_timeout(2000)

    # Проверяем результат
    success_indicators = [
        "text=Вы откликнулись",
        "text=Отклик отправлен",
        '[data-qa="vacancy-response-link-top-after"]',
        "text=Вы уже откликнулись",
    ]
    for selector in success_indicators:
        if page.locator(selector).count() > 0:
            return "applied"

    return "unknown_state"


def _select_resume(page: Page, resume_id: str) -> None:
    """
    Выбирает резюме в модальном окне отклика.

    Если resume_id задан — ищет резюме по ID (из href/data-атрибутов).
    Если не задан — оставляет первое выбранное по умолчанию.
    """
    resume_list = page.locator('[data-qa="vacancy-response-popup-resume"]')

    if resume_list.count() <= 1:
        return

    if not resume_id:
        log.info("  Несколько резюме доступно, используется первое по умолчанию")
        return

    # Ищем резюме по ID в href или data-атрибутах
    for i in range(resume_list.count()):
        item = resume_list.nth(i)
        html = item.evaluate("e => e.outerHTML")
        if resume_id in html:
            item.click()
            page.wait_for_timeout(500)
            log.info("  Выбрано резюме по ID: %s", resume_id)
            return

    log.warning("  Резюме с ID '%s' не найдено в списке, используется по умолчанию", resume_id)


def _fill_cover_letter(page: Page, cover_letter: str) -> None:
    """Заполняет поле сопроводительного письма в форме отклика."""
    # Вариант 1: поле в модальном окне
    letter_input = page.locator('[data-qa="vacancy-response-popup-form-letter-input"]')
    if letter_input.count() > 0 and letter_input.first.is_visible():
        letter_input.first.fill(cover_letter)
        page.wait_for_timeout(500)
        return

    # Вариант 2: textarea (альтернативная разметка)
    alt_textarea = page.locator('textarea[data-qa="vacancy-response-letter-toggle-textarea"]')
    if alt_textarea.count() > 0 and alt_textarea.first.is_visible():
        alt_textarea.first.fill(cover_letter)
        page.wait_for_timeout(500)
        return

    # Вариант 3: кнопка "Добавить сопроводительное" / "Написать сопроводительное"
    toggle_btn = page.locator('[data-qa="vacancy-response-letter-toggle"]')
    if toggle_btn.count() == 0:
        toggle_btn = page.get_by_text("сопроводительное", exact=False)
    if toggle_btn.count() > 0 and toggle_btn.first.is_visible():
        toggle_btn.first.click()
        page.wait_for_timeout(1000)

    # Вариант 4: найти любую видимую textarea на странице
    textareas = page.locator("textarea")
    for i in range(textareas.count()):
        ta = textareas.nth(i)
        if ta.is_visible():
            ta.fill(cover_letter)
            page.wait_for_timeout(500)
            return

    log.warning("  Поле для сопроводительного письма не найдено")
