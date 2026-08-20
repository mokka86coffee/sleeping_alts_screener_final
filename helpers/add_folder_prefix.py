import os

# Получаем название текущей папки
folder_name = os.path.basename(os.getcwd())

# Проходимся по всем элементам в директории
for filename in os.listdir('.'):
    # Пропускаем если это не файл (например, если внутри есть подпапки)
    if os.path.isfile(filename):
        # Формируем новое имя: префикс + оригинальное имя
        new_filename = f"{folder_name}_{filename}"
        # Переименовываем файл
        os.rename(filename, new_filename)
        print(f"Переименовано: {filename} -> {new_filename}")
