from __future__ import annotations

import logging
import re

from playwright.sync_api import Page

log = logging.getLogger("hh_bot")


def search_vacancies(page: Page, search_url: str) -> list[dict]:
    """
    Парсит страницы поиска вакансий на hh.ru и возвращает список вакансий.

    Принимает URL поиска, скопированный из браузера hh.ru.
    Автоматически проходит по всем страницам пагинации.
    """
    vacancies = []
    current_page = 0

    while True:
        # Добавляем номер страницы к URL
        url = _add_page_param(search_url, current_page)
        log.info("Загружаю страницу %d: %s", current_page + 1, url)

        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Парсим вакансии на текущей странице
        page_vacancies = _parse_vacancy_list(page)

        if not page_vacancies:
            log.info("Вакансий на странице %d не найдено — конец результатов", current_page + 1)
            break

        vacancies.extend(page_vacancies)
        log.info("Страница %d: найдено %d вакансий (всего: %d)",
                 current_page + 1, len(page_vacancies), len(vacancies))

        # Если на странице меньше вакансий чем обычно — это последняя
        if len(page_vacancies) < 20:
            log.info("Последняя страница достигнута (вакансий на странице: %d)", len(page_vacancies))
            break

        current_page += 1

    log.info("Поиск завершён: найдено %d вакансий", len(vacancies))
    return vacancies


def get_vacancy_description(page: Page, vacancy_url: str) -> str:
    """Переходит на страницу вакансии и извлекает текст описания."""
    page.goto(vacancy_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)

    desc_locator = page.locator('[data-qa="vacancy-description"]')
    if desc_locator.count() > 0:
        html = desc_locator.first.inner_text()
        return html.strip()

    return ""


def _parse_vacancy_list(page: Page) -> list[dict]:
    """Парсит список вакансий на текущей странице результатов поиска."""
    vacancies = []

    # Основной селектор карточек вакансий
    cards = page.locator('[data-qa="vacancy-serp__vacancy"]')
    count = cards.count()

    if count == 0:
        # Альтернативный селектор — hh.ru иногда меняет разметку
        cards = page.locator(".vacancy-card--clickable")
        count = cards.count()

    for i in range(count):
        card = cards.nth(i)
        try:
            vacancy = _parse_vacancy_card(card)
            if vacancy:
                vacancies.append(vacancy)
        except Exception as e:
            log.warning("Ошибка парсинга карточки #%d: %s", i, e)

    return vacancies


def _parse_vacancy_card(card) -> dict | None:
    """Извлекает данные из одной карточки вакансии."""
    # Название и ссылка
    title_link = card.locator('[data-qa="serp-item__title"]')
    if title_link.count() == 0:
        title_link = card.locator("a[data-qa*='title']")
    if title_link.count() == 0:
        return None

    title = title_link.first.inner_text().strip()
    url = title_link.first.get_attribute("href") or ""

    # Извлекаем ID вакансии из URL
    vacancy_id = _extract_vacancy_id(url)
    if not vacancy_id:
        return None

    # Компания
    employer = ""
    employer_el = card.locator('[data-qa="vacancy-serp__vacancy-employer"]')
    if employer_el.count() == 0:
        employer_el = card.locator('[data-qa*="employer"]')
    if employer_el.count() > 0:
        employer = employer_el.first.inner_text().strip()

    # Зарплата
    salary = ""
    salary_el = card.locator('[data-qa="vacancy-serp__vacancy-compensation"]')
    if salary_el.count() > 0:
        salary = salary_el.first.inner_text().strip()

    return {
        "id": vacancy_id,
        "title": title,
        "employer": employer,
        "salary": salary,
        "url": url if url.startswith("http") else f"https://hh.ru{url}",
    }


def _extract_vacancy_id(url: str) -> str | None:
    """Извлекает ID вакансии из URL вида /vacancy/12345678."""
    match = re.search(r"/vacancy/(\d+)", url)
    return match.group(1) if match else None


def _add_page_param(url: str, page_num: int) -> str:
    """Добавляет или заменяет параметр page в URL."""
    if page_num == 0:
        return url

    if "page=" in url:
        return re.sub(r"page=\d+", f"page={page_num}", url)

    separator = "&" if "?" in url else "?"
    return f"{url}{separator}page={page_num}"
