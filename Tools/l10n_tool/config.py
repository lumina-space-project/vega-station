from pathlib import Path

# Делаем пути абсолютными относительно этого файла конфигурации
# Это гарантирует, что скрипт будет работать, откуда бы его ни запустили
CONFIG_DIR = Path(__file__).resolve().parent

# Настройте этот путь под вашу реальную структуру!
# По умолчанию: ./../../Resources/Locale/
LOCALES_DIR = CONFIG_DIR.parent.parent / 'Resources' / 'Locale'

# IGNORE_LOCALES = { 'pl-PL', 'fr-FR' } # etc.
BASE_LOCALE = 'en-US'

# 3. Настройки поведения
HARD_MODE = False       # Если True - скрипт будет автоматически исправлять файлы
NO_TRASH = False        # Если True - лишние файлы удаляются навсегда, а не перемещаются в .trash
SET_MISSING_STR = '__MISSING__'
