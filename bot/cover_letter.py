import logging
import re

import anthropic

log = logging.getLogger("hh_bot")


def generate_cover_letter(
    vacancy_title: str,
    employer: str,
    description: str,
    resume_summary: str,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
) -> str:
    """
    Генерирует персонализированное сопроводительное письмо через Claude API.

    Возвращает текст письма (500-1000 символов) или пустую строку при ошибке.
    """
    client = anthropic.Anthropic(api_key=api_key)

    # Ограничиваем длину описания чтобы не раздувать промпт
    description_trimmed = description[:3000] if description else "Описание не доступно"

    prompt = f"""Напиши сопроводительное письмо на русском языке для отклика на вакансию.

Вакансия: {vacancy_title}
Компания: {employer}

Описание вакансии:
{description_trimmed}

Мой опыт (краткое резюме):
{resume_summary}

Требования к письму:
- Длина: 3-5 предложений (500-1000 символов)
- Тон: профессиональный, но не формальный
- Покажи конкретную связь между моим опытом и требованиями вакансии
- Не начинай с "Здравствуйте" или "Уважаемый"
- Начни сразу с сути — почему я подхожу
- Не используй шаблонные фразы вроде "с большим интересом прочитал"
- Пиши от первого лица
- Верни только текст письма, без заголовков и подписи"""

    try:
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        log.info("Сопроводительное письмо сгенерировано (%d символов)", len(text))
        return text
    except anthropic.APIError as e:
        log.error("Ошибка Claude API: %s", e)
        return ""
    except Exception as e:
        log.error("Непредвиденная ошибка при генерации письма: %s", e)
        return ""
