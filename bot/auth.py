import json
import logging
import os

from playwright.sync_api import BrowserContext, Page

COOKIES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "storage", "cookies.json"
)
LOGIN_URL = "https://hh.ru/account/login"
RESUMES_URL = "https://hh.ru/applicant/resumes"

log = logging.getLogger("hh_bot")


def save_cookies(context: BrowserContext) -> None:
    cookies = context.cookies()
    os.makedirs(os.path.dirname(COOKIES_PATH), exist_ok=True)
    with open(COOKIES_PATH, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False)
    log.info("Cookies сохранены")


def load_cookies(context: BrowserContext) -> bool:
    if not os.path.exists(COOKIES_PATH):
        return False
    try:
        with open(COOKIES_PATH, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        log.info("Cookies загружены из файла")
        return True
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Не удалось загрузить cookies: %s", e)
        return False


def is_logged_in(page: Page) -> bool:
    """Проверяет авторизацию, открыв страницу резюме."""
    page.goto(RESUMES_URL, wait_until="domcontentloaded", timeout=30000)
    # Если редиректит на логин — не авторизованы
    if "/account/login" in page.url:
        return False
    # Дополнительная проверка: ищем элементы залогиненного пользователя
    page.wait_for_timeout(1000)
    if page.get_by_text("Войти", exact=True).count() > 0:
        return False
    return True


def login(page: Page, username: str, password: str) -> bool:
    """
    Авторизация на hh.ru через пошаговый флоу (2026):
    1. Выбор типа аккаунта (соискатель) → «Войти»
    2. Переключение на «Почта» → ввод email
    3. Клик «Войти с паролем» → ввод пароля → отправка
    4. Если пароль не сработал — fallback на OTP-код
    """
    log.info("Попытка авторизации для %s", username)
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    # Шаг 1: Выбор типа аккаунта — «Я ищу работу» уже выбран, жмём «Войти»
    submit_btn = page.locator('[data-qa="submit-button"]')
    if submit_btn.count() > 0:
        submit_btn.click()
        page.wait_for_timeout(2000)

    # Шаг 2: Переключаемся на «Почта» (по умолчанию — «Телефон»)
    email_tab = page.get_by_text("Почта", exact=True)
    if email_tab.count() > 0:
        email_tab.first.click()
        page.wait_for_timeout(1000)

    # Шаг 3: Вводим email
    email_input = page.locator('[data-qa="applicant-login-input-email"]')
    if email_input.count() == 0:
        email_input = page.locator('input[inputmode="email"]')
    if email_input.count() == 0:
        log.error("Не удалось найти поле ввода email")
        return False

    email_input.fill(username)
    page.wait_for_timeout(500)

    # Шаг 4: Пробуем «Войти с паролем»
    pwd_btn = page.locator('[data-qa="expand-login-by-password"]')
    if pwd_btn.count() > 0 and password:
        log.info("Вхожу с паролем")
        pwd_btn.evaluate("e => e.click()")
        page.wait_for_timeout(1000)

        pwd_input = page.locator('[data-qa="applicant-login-input-password"]')
        if pwd_input.count() > 0:
            pwd_input.fill(password)
            page.wait_for_timeout(500)

            submit_btn = page.locator('[data-qa="submit-button"]')
            submit_btn.click()

            try:
                page.wait_for_url(
                    lambda url: "/account/login" not in url,
                    timeout=15000,
                )
                log.info("Авторизация по паролю успешна")
                return True
            except Exception:
                log.info("Вход по паролю не удался, пробую OTP")

    # Шаг 5: Fallback на OTP — нажимаем «Дальше»
    # Нужно вернуться на страницу с email, если мы застряли
    if page.locator('[data-qa="applicant-login-input-password"]').count() > 0:
        # Мы на странице пароля — жмём «Назад» и идём через OTP
        back_btn = page.locator('[data-qa="go-back-button"]')
        if back_btn.count() > 0:
            back_btn.click()
            page.wait_for_timeout(2000)
            # Повторяем: Войти → Почта → email → Дальше
            page.locator('[data-qa="submit-button"]').click()
            page.wait_for_timeout(2000)
            page.get_by_text("Почта", exact=True).first.click()
            page.wait_for_timeout(1000)
            page.locator('[data-qa="applicant-login-input-email"]').fill(username)
            page.wait_for_timeout(500)

    submit_btn = page.locator('[data-qa="submit-button"]')
    submit_btn.click()
    page.wait_for_timeout(3000)

    # Шаг 6: Ввод OTP-кода
    otp_input = page.locator('[data-qa="magritte-pincode-input-field"]')
    if otp_input.count() > 0:
        log.warning("hh.ru отправил OTP-код на %s. Введите код в консоли.", username)
        otp = input("Введите 4-значный код из письма: ").strip()
        otp_input.fill(otp)
        page.wait_for_timeout(3000)
    else:
        log.error("Не найдено поле для OTP-кода — возможно изменилась разметка")
        return False

    # Проверяем результат
    if "/account/login" in page.url:
        error = page.locator('[data-qa="form-helper-error"]')
        if error.count() > 0:
            log.error("Ошибка авторизации: %s", error.first.inner_text())
        else:
            log.error("Авторизация не удалась — проверьте код")
        return False

    log.info("Авторизация успешна")
    return True


def ensure_logged_in(
    context: BrowserContext, page: Page, username: str, password: str
) -> bool:
    """Гарантирует что пользователь авторизован, используя cookies или логин."""
    # Попробовать загрузить cookies
    if load_cookies(context):
        if is_logged_in(page):
            log.info("Сессия активна (cookies)")
            return True
        log.info("Cookies устарели, пробуем залогиниться заново")

    # Логин через форму
    if login(page, username, password):
        save_cookies(context)
        return True

    return False
