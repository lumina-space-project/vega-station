from collections import defaultdict
import logging
import os
import argparse
import re
import sys
import shutil
import questionary
from pathlib import Path
from datetime import datetime
from fluent.syntax import FluentParser, FluentSerializer, ast

from config import (
    BASE_LOCALE,
    LOCALES_DIR,
    HARD_MODE,
    NO_TRASH,
    SET_MISSING_STR,
)

def show_logotype():
    ascii_logo = """
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠤⠒⠈⠉⠉⠉⠉⠒⠀⠀⠤⣀⠀⠀⠀⠀    ___    _____ _______           __               __
⠀⠀⠀⠀⠀⠀⠀⠀⠀⣰⠁⠀⠀⠀⠀⠀⠀⢀⣄⠀⠀⠀⠀⠑⡄⠀⠀    |   |  | _   |   _   .-----.   |  |_.-----.-----|  |
⠀⠀⠀⠀⠀⠀⠀⠀⠰⠿⠿⠿⠣⣶⣿⡏⣶⣿⣿⠷⠶⠆⠀⠀⠘⠀     |.  |  |.|   |.  |   |     |   |   _|  _  |  _  |  |⠀
⠀⠀⠀⠀⠀⠀⠠⠴⡅⠀⠀⠠⢶⣿⣿⣷⡄⣀⡀⡀⠀⠀⠀⠀⠀⡇⠀    |.  |__`-|.  |.  |   |__|__|   |____|_____|_____|__|
⠀⣰⡶⣦⠀⠀⠀⡰⠀⠀⠸⠟⢸⣿⣿⣷⡆⠢⣉⢀⠀⠀⠀⠀⠀⠀⠀    |:  1   ||:  |:  1   |
⠀⢹⣧⣿⣇⠀⠀⡇⠀⢠⣷⣲⣺⣿⣿⣇⠤⣤⣿⣿⠀⢸⠀⣤⣶⠦⠀⠀   |::.. . ||::.|::.. . |  Version 1.0.0
⠀⠀⠙⢿⣿⣦⡀⢇⠀⠸⣿⣿⣿⣿⣿⣿⣿⣿⣿⠇⠀⡜⣾⣿⡃⠇⢀⣤⡀  `-------'`---`-------'
⠀⠀⠀⠀⠙⢿⣿⣮⡆⠀⠙⠿⣿⣿⣾⣿⡿⡿⠋⢀⠞⢀⣿⣿⣿⣿⣿⡟⠁
⠀⠀⠀⠀⠀⠀⠛⢿⠇⣶⣤⣄⢀⣰⣷⣶⣿⠁⡰⢃⣴⣿⡿⢋⠏⠉⠁⠀⠀  🛠️  DEVELOPER:
⠀⠀⠀⠀⠀⠀⠀⠠⢾⣿⣿⣿⣞⠿⣿⣿⢿⢸⣷⣌⠛⠋⠀⠘⠀⠀⠀    ├─ Head of Department : @m4rn3lle
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⠙⣿⣿⣿⣶⣶⣿⣯⣿⣿⣿⣆⠀⠇       └─ For Project : VEGA Station
    """

    print(ascii_logo)

## Setup logging config
def setup_logging(log_enabled=False, log_file=None):
    config = {
        "level": logging.INFO,
        "format": "[%(levelname)s] %(message)s",
        "encoding": "utf-8",

    }

    if log_file is None:
        log_file = f'loc_{datetime.now().strftime("%Y%m%d%H%M%S")}.log'

    if log_enabled:
        path = os.path.dirname(log_file)

        if path and not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

        config['filename'] = log_file
    else:
        config['stream'] = sys.stdout

    logging.basicConfig(**config)

    return log_file


# Сканирование директорий и сбор информации о файлах
def scan_directory(directory):
    ftl_files = {}
    directories = set()
    all_syntax_errors = {}  # { 'rel_path': [ошибки, ...] }

    for root, dirs, files in os.walk(directory):
        # Собираем относительные пути всех директорий
        for d in dirs:
            full_dir_path = os.path.join(root, d)
            rel_dir_path = os.path.relpath(full_dir_path, directory)
            directories.add(rel_dir_path)

        # Собираем файлы
        for file in files:
            if file.endswith('.ftl'):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, directory)
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Извлекаем ключи (включая атрибуты) и синтаксические ошибки
                        identifiers, file_errors = get_ftl_data(content)

                        if file_errors:
                            all_syntax_errors[rel_path] = (full_path, file_errors)
                            for err in file_errors:
                                logging.error(f"Syntax error in {full_path}: {err}")

                        ftl_files[rel_path] = (full_path, identifiers)
                except Exception as e:
                    logging.error(f"Error parsing FTL file {full_path}: {e}")

    return ftl_files, directories, all_syntax_errors


# Функция для чтения FTL-файлов
def read_ftl_files(directory):
    ftl_files = {}
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.ftl'):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, directory)
                with open(full_path, 'r', encoding='utf-8') as f:
                    ftl_files[rel_path] = (full_path, f.read())

    return ftl_files

# Основная функция для сравнения и обработки каталогов локализации
def compare_directories(default_dir, target_dir, isHard = False, no_trash = False):
    # Списки для файлов
    missing_files = []
    extra_files = []
    valid_files = defaultdict(list)

    # Списки для директорий
    missing_dirs = []
    extra_dirs = []
    valid_dirs = defaultdict(list)

     # Структура для хранения diffs в FTL-keys:
    # { 'rel_path': {'missing_keys': [...], 'extra_keys': [...]} }
    ftl_keys_diff = {}

    # Сканируем директории и получаем информацию об ошибках синтаксиса
    default_ftl, default_dirs, default_errors = scan_directory(default_dir)
    target_ftl, target_dirs, target_errors = scan_directory(target_dir)

    # директория для удаляемых файлов
    trash_dir = os.path.abspath('.trash')

    # Объединяем все синтаксические ошибки в один общий словарь для вывода
    # Структура: { 'rel_path': {'full_path': '...', 'errors': [...]}, ... }
    syntax_report = {}
    for r_path, (f_path, errs) in {**default_errors, **target_errors}.items():
        syntax_report[r_path] = {'full_path': f_path, 'errors': errs}

    # Ищем отсутствующие и валидные папки
    for rel_dir in default_dirs:
        default_full_dir = os.path.join(default_dir, rel_dir)
        if rel_dir not in target_dirs:
            missing_dirs.append(default_full_dir)
        else:
            target_full_dir = os.path.join(target_dir, rel_dir)
            valid_dirs[rel_dir].extend([default_full_dir, target_full_dir])

    # Ищем лишние папки
    for rel_dir in target_dirs:
        if rel_dir not in default_dirs:
            target_full_dir = os.path.join(target_dir, rel_dir)
            extra_dirs.append(target_full_dir)

            if isHard:
                # Проверяем, существует ли еще директория
                # (она могла удалиться/переместиться вместе с родительской папкой ранее)
                if os.path.exists(target_full_dir):
                    if no_trash:
                        shutil.rmtree(target_full_dir)
                        continue

                    trash_dir_path = os.path.join(trash_dir, rel_dir)

                    # Если папка в .trash уже есть, удаляем её перед перемещением новой
                    if os.path.exists(trash_dir_path):
                        shutil.rmtree(trash_dir_path)

                    # Создаем родительский контейнер в .trash, если необходимо
                    os.makedirs(os.path.dirname(trash_dir_path), exist_ok=True)

                    # Перемещаем всю директорию целиком
                    shutil.move(target_full_dir, trash_dir_path)

    # Ищем отсутствующие и валидные файлы
    for rel_path, (default_full_path, default_keys) in default_ftl.items():
        if rel_path not in target_ftl:
            missing_files.append(default_full_path)
            # --- ЛОГИКА --hard ДЛЯ ОТСУТСТВУЮЩИХ ФАЙЛОВ ---
            if isHard:
                # Определяем, где должен лежать файл в целевой папке
                target_full_path = os.path.join(target_dir, rel_path)
                # Создаем поддиректории, если их еще нет
                os.makedirs(os.path.dirname(target_full_path), exist_ok=True)

                # Генерируем контент: берем структуру ключей из default_keys
                # Чтобы не ломать Fluent-синтаксис атрибутов (с точкой),
                # фильтруем только корневые ключи. Атрибуты запишутся внутри.
                # Для простоты генерируем базовые пары ключ = заглушка
                ftl_lines = []
                for key in sorted(default_keys):
                    if '.' not in key:  # Корневой ключ Fluent
                        ftl_lines.append(f"{key} = {SET_MISSING_STR}")

                with open(target_full_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(ftl_lines) + '\n')
        else:
            target_full_path, target_keys = target_ftl[rel_path]
            valid_files[rel_path].extend([default_full_path, target_full_path])

            # Сравниваем идентификаторы внутри валидного файла
            missing_keys = default_keys - target_keys
            extra_keys = target_keys - default_keys

            if missing_keys or extra_keys:
                ftl_keys_diff[rel_path] = {
                    'missing_keys': list(missing_keys),
                    'extra_keys': list(extra_keys)
                }

            # --- ЛОГИКА --hard ДЛЯ СУЩЕСТВУЮЩИХ ФАЙЛОВ ---
            if isHard and (missing_keys or extra_keys):
                parser = FluentParser()
                serializer = FluentSerializer(with_junk=False)

                # Читаем сырой контент обоих файлов для работы с AST
                with open(default_full_path, 'r', encoding='utf-8') as f:
                    def_content = f.read()
                with open(target_full_path, 'r', encoding='utf-8') as f:
                    tar_content = f.read()

                def_resource = parser.parse(def_content)
                tar_resource = parser.parse(tar_content)

                # Собираем существующие переводы из целевого файла
                target_entries = {
                    entry.id.name: entry
                    for entry in tar_resource.body
                    if isinstance(entry, (ast.Message, ast.Term))
                }

                new_body = []
                missing_pattern = ast.Pattern(elements=[ast.TextElement(value=SET_MISSING_STR)])

                # Пересобираем файл по структуре дефолтного (удаляет extra_keys, упорядочивает структуру)
                for entry in def_resource.body:
                    if isinstance(entry, (ast.Message, ast.Term)):
                        key_name = entry.id.name

                        if key_name in target_entries:
                            # Ключ есть — переносим его перевод
                            tar_entry = target_entries[key_name]

                            # Синхронизируем атрибуты внутри ключа
                            updated_attributes = []
                            if entry.attributes:
                                tar_attrs = {attr.id.name: attr for attr in tar_entry.attributes} if tar_entry.attributes else {}
                                for def_attr in entry.attributes:
                                    attr_name = def_attr.id.name
                                    if attr_name in tar_attrs:
                                        updated_attributes.append(tar_attrs[attr_name])
                                    else:
                                        updated_attributes.append(ast.Attribute(id=ast.Identifier(name=attr_name), value=missing_pattern))

                            if isinstance(entry, ast.Message):
                                val = tar_entry.value if tar_entry.value or not entry.value else missing_pattern
                                synchronized_entry = ast.Message(id=ast.Identifier(name=key_name), value=val, attributes=updated_attributes)
                            else:
                                val = tar_entry.value if tar_entry.value else missing_pattern
                                synchronized_entry = ast.Term(id=ast.Identifier(name=key_name), value=val, attributes=updated_attributes)

                            new_body.append(synchronized_entry)
                        else:
                            # Ключа нет — создаем с нуля с заглушками (включая его атрибуты)
                            new_attributes = []
                            if entry.attributes:
                                for def_attr in entry.attributes:
                                    new_attributes.append(ast.Attribute(id=ast.Identifier(name=def_attr.id.name), value=missing_pattern))

                            if isinstance(entry, ast.Message):
                                val = missing_pattern if entry.value else None
                                new_entry = ast.Message(id=ast.Identifier(name=key_name), value=val, attributes=new_attributes)
                            else:
                                new_entry = ast.Term(id=ast.Identifier(name=key_name), value=missing_pattern, attributes=new_attributes)

                            new_body.append(new_entry)
                    else:
                        # Сохраняем комментарии и разметку из дефолтного файла
                        new_body.append(entry)

                # Записываем обновленный контент обратно в целевой файл
                updated_resource = ast.Resource(body=new_body)
                updated_content = serializer.serialize(updated_resource)

                with open(target_full_path, 'w', encoding='utf-8') as f:
                    f.write(updated_content)

    for rel_path, (target_full_path, _) in target_ftl.items():
        if rel_path not in default_ftl:
            extra_files.append(target_full_path)
            # --- ЛОГИКА --hard ДЛЯ ЛИШНИХ ФАЙЛОВ ---
            if isHard:
                if no_trash: # Не использовать корзину
                    os.remove(target_full_path)
                    continue
                # Формируем путь внутри корзины с сохранением структуры подпапок
                trash_file_path = os.path.join(trash_dir, rel_path)

                os.makedirs(os.path.dirname(trash_file_path), exist_ok=True)
                # Перемещаем файл (если такой уже был в trash, заменяем его)
                if os.path.exists(trash_file_path):
                    os.remove(trash_file_path)
                shutil.move(target_full_path, trash_file_path)
    return (
        missing_files, extra_files, valid_files,
        missing_dirs, extra_dirs, valid_dirs,
        ftl_keys_diff, syntax_report
    )

def get_ftl_data(content):
    """
    Парсит FTL контент.
    Возвращает:
      - identifiers (set): Все ID  и их атрибуты.
      - syntax_errors (list): Список синтаксических ошибок (Junk).
    """
    parser = FluentParser()
    resource = parser.parse(content)
    identifiers = set()
    syntax_errors = []

    for entry in resource.body:
        # Проверка на синтаксические ошибки
        if isinstance(entry, ast.Junk):
            # Извлекаем срез текста, где произошла ошибка
            # Конвертируем код ошибки в читаемый вид, если аннотации доступны
            annot_msg = entry.annotations[0].message if entry.annotations else "Unknown syntax error"
            # Для удобства берем первые 40 символов ошибочной строки
            problematic_text = entry.content.strip().split('\n')[0][:40]
            syntax_errors.append(f"{annot_msg} возле текста: '{problematic_text}...'")
            continue
        # Проверяем, является ли запись сообщением (Message) или термом (Term)
        if isinstance(entry, (ast.Message, ast.Term)):
            # Добавляем корневой идентификатор сообщения
            msg_id = entry.id.name
            identifiers.add(msg_id)

            # Добавляем атрибуты сообщения (если они есть)
            for attr in entry.attributes:
                # Получится строка вида: "login-button.title"
                full_attr_name = f"{msg_id}.{attr.id.name}"
                identifiers.add(full_attr_name)

    return identifiers, syntax_errors

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def clean_ansi(text):
    """Удаляет ANSI-последовательности цветов для чистой записи в файл."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def print_report(missing_files, extra_files, valid_files,
                 missing_dirs, extra_dirs, valid_dirs,
                 ftl_keys_diff, syntax_report, log_file_path=None):

    # Тут собираем текст репорта
    buffer = []

    def log(text):
        print(text)  # Вывод в консоль с сохранением всех цветов
        buffer.append(text)

    log(f"\n{Colors.BOLD}{Colors.HEADER}<===== L10N TOOL REPORT OUTPUT =====>{Colors.ENDC}\n")

    # СИНТАКСИЧЕСКИЕ ОШИБКИ
    if syntax_report:
        log(f"{Colors.BOLD}{Colors.FAIL}[CRITICAL] SYNTAX ERRORS DETECTED:{Colors.ENDC}")
        for rel_path, data in syntax_report.items():
            log(f"  {Colors.FAIL}•{Colors.ENDC} {rel_path} ({data['full_path']})")
            for err in data['errors']:
                log(f"    {Colors.FAIL}└── {err}{Colors.ENDC}")
        log("")

    # СТРУКТУРНЫЕ РАСХОЖДЕНИЯ (Директории)
    if missing_dirs or extra_dirs:
        log(f"{Colors.BOLD}{Colors.OKBLUE}[STRUCTURE] DIRECTORY MISMATCHES:{Colors.ENDC}")
        for d in missing_dirs:
            log(f"  {Colors.FAIL}[MISSING DIR]{Colors.ENDC} {d}")
        for d in extra_dirs:
            log(f"  {Colors.WARNING}[EXTRA DIR]  {Colors.ENDC} {d}")
        log("")

    # СТРУКТУРНЫЕ РАСХОЖДЕНИЯ (Файлы)
    if missing_files or extra_files:
        log(f"{Colors.BOLD}{Colors.OKBLUE}[STRUCTURE] FILE MISMATCHES:{Colors.ENDC}")
        for f in missing_files:
            log(f"  {Colors.FAIL}[MISSING FILE]{Colors.ENDC} {f}")
        for f in extra_files:
            log(f"  {Colors.WARNING}[EXTRA FILE]  {Colors.ENDC} {f}")
        log("")

    # РАСХОЖДЕНИЯ В КЛЮЧАХ ЛОКАЛИЗАЦИИ
    if ftl_keys_diff:
        log(f"{Colors.BOLD}{Colors.WARNING}[CONTENT] MISMATCHED FTL KEYS IN VALID FILES:{Colors.ENDC}")
        for rel_path, diff in ftl_keys_diff.items():
            log(f"  {Colors.BOLD}{rel_path}{Colors.ENDC}:")
            if diff['missing_keys']:
                log(f"    {Colors.FAIL}[-] Missing keys:{Colors.ENDC}")
                for key in sorted(diff['missing_keys']):
                    log(f"        • {key}")
            if diff['extra_keys']:
                log(f"    {Colors.WARNING}[+] Extra keys:{Colors.ENDC}")
                for key in sorted(diff['extra_keys']):
                    log(f"        • {key}")
        log("")

    # ИТОГОВАЯ СВОДНАЯ ТАБЛИЦА
    total_valid_files = len(valid_files)
    total_keys_errors = len(ftl_keys_diff)

    log(f"{Colors.BOLD}========================================{Colors.ENDC}")
    log(f"{Colors.BOLD}SUMMARY STATS:{Colors.ENDC}")
    log(f"  • FTL files founded       : {Colors.OKGREEN}{total_valid_files}{Colors.ENDC}")
    log(f"  • Missing / Extra Folders : {Colors.FAIL if missing_dirs else Colors.OKGREEN}{len(missing_dirs)}{Colors.ENDC} / {Colors.WARNING if extra_dirs else Colors.OKGREEN}{len(extra_dirs)}{Colors.ENDC}")
    log(f"  • Missing / Extra Files   : {Colors.FAIL if missing_files else Colors.OKGREEN}{len(missing_files)}{Colors.ENDC} / {Colors.WARNING if extra_files else Colors.OKGREEN}{len(extra_files)}{Colors.ENDC}")
    log(f"  • Files Syntax Status     : {Colors.FAIL if syntax_report else Colors.OKGREEN}{len(syntax_report)} broken{Colors.ENDC}")
    log(f"  • FTL Keys Status         : {Colors.OKGREEN}{total_valid_files - total_keys_errors} OK{Colors.ENDC} | {Colors.FAIL if total_keys_errors else Colors.OKGREEN}{total_keys_errors} mismatched{Colors.ENDC}")
    log(f"{Colors.BOLD}========================================{Colors.ENDC}")

    # Определение финального статуса
    has_critical_errors = (syntax_report or missing_files or missing_dirs or ftl_keys_diff)
    has_warnings = (extra_dirs or extra_files)

    if has_critical_errors:
        log(f"\n{Colors.FAIL}{Colors.BOLD}STATUS: VALIDATION FAILED{Colors.ENDC}")
    elif has_warnings:
        log(f"\n{Colors.WARNING}{Colors.BOLD}STATUS: SUCCESS WITH WARNINGS (Extra items detected){Colors.ENDC}")
    else:
        log(f"\n{Colors.OKGREEN}{Colors.BOLD}STATUS: SUCCESS{Colors.ENDC}")

    # Логика записи в файл
    if log_file_path:
        try:
            # Превращаем накопленный массив строк в один текст
            full_raw_text = "\n".join(buffer) + "\n"

            clean_text = clean_ansi(full_raw_text)

            with open(log_file_path, 'w', encoding='utf-8') as f:
                f.write(clean_text)
            print(f"\n{Colors.OKBLUE}[INFO] Report successfully saved to: {log_file_path}{Colors.ENDC}")
        except Exception as e:
            sys.stderr.write(f"\n{Colors.FAIL}[ERROR] Failed to write log file: {e}{Colors.ENDC}\n")

def main():
    show_logotype()

    parser = argparse.ArgumentParser(description='Localization Tool')
    parser.add_argument('-l', '--log', action='store_true', help='Enable logging to a file')
    parser.add_argument('--log-file', type=Path, help='Path to the log file (used if --log is enabled)')
    parser.add_argument('--locales-dir', type=Path, help='Path to the locales directory')
    parser.add_argument('--base-locale', type=str, help='Path to the base locale (e.g., en-US)')
    parser.add_argument('--hard', action='store_true', help='Perform hard synchronization')
    parser.add_argument('--no-trash', action='store_true', help='Disable usage of the .trash directory')

    args = parser.parse_args()

    log_file = setup_logging(args.log, args.log_file)

    base_locale = args.base_locale or BASE_LOCALE
    locales_dir = args.locales_dir or LOCALES_DIR
    hard_mode = args.hard or HARD_MODE
    no_trash = args.no_trash or NO_TRASH

    if not os.path.exists(locales_dir):
        logging.info(f"{locales_dir} directory not found")
        exit(1)

    ftl_dir_pattern = re.compile(r"^[a-z]{2}-[A-Z]{2}$")
    locales = [d for d in os.listdir(locales_dir)
               if d != base_locale and
               os.path.isdir(os.path.join(locales_dir, d)) and
               ftl_dir_pattern.match(d)
               ]

    if not locales:
        logging.info("No localization directories found")
        exit(1)

    target_locale = questionary.select(
        "Select a locale:",
        choices=[*locales, "Exit"
        ],
    ).ask()

    if target_locale not in locales:
        logging.info("Script terminated by user or invalid value selected.")
        exit(0)


    print_report(*compare_directories(
    Path(locales_dir) / base_locale,
    Path(locales_dir) / target_locale, hard_mode, no_trash),
    log_file_path=log_file if args.log else None)

if __name__ == "__main__":
    main()
