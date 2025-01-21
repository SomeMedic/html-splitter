# Split HTML Project

**Цель**: Разбить HTML на фрагменты, не превышающие заданный размер, сохраняя структуру.

## Установка и запуск через Poetry

```bash
git clone https://github.com/SomeMedic/html-splitter.git
cd html-splitter
```

# Установить Poetry (если ещё не установлено):
```bash
choco install poetry
```

# Установить зависимости
```bash
poetry install
```

# Запустить тесты (unittest)
```bash
poetry run python -m unittest discover
```

# Запуск основного скрипта
```bash
poetry run python split_msg.py --max-len=4096 source.html
```
