import os

def should_replace(name):
    """
    Проверяет, нужно ли заменять точку на нижнее подчёркивание.
    Условие: ровно два слова и ровно одна точка.
    """
    # Разделяем имя на слова по подчёркиванию
    words = name.split('_')
    # Проверяем, что получилось ровно два слова
    return len(words) == 2 and '.' in name and name.count('.') == 1

def replace_in_file(input_path, output_path):
    """
    Заменяет точку на нижнее подчёркивание в имени файла, если условие выполняется.
    """
    new_name = should_replace(os.path.basename(input_path))
    if new_name:
        os.rename(input_path, output_path)

def process_directory(directory):
    """
    Рекурсивно обрабатывает все файлы в директории.
    """
    for root, _, files in os.walk(directory):
        for filename in files:
            file_path = os.path.join(root, filename)
            # Проверяем, относится ли имя файла к нужным шаблонам
            if should_replace(filename):
                new_path = os.path.join(root, filename.replace('.', '_'))
                replace_in_file(file_path, new_path)

# Пример использования: заменить в текущей директории
if __name__ == '__main__':
    current_dir = os.getcwd()  # Укажите нужную директорию
    process_directory(current_dir)
