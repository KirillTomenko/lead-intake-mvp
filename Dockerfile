# Используем официальный образ Python 3.12 (slim - облегченный)
FROM python:3.12-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем только requirements.txt сначала (для кэширования слоев Docker)
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код проекта
COPY . .

# Создаем папки для статических файлов и шаблонов (если их нет)
RUN mkdir -p static templates

# Открываем порт 8000
EXPOSE 8000

# Запускаем сервер (без --reload для продакшена)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]