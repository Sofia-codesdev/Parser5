import json            # модуль для работы с файлами json
import time                # модуль для измерения времени выполнения 
import webbrowser             # модуль для открытия ссылок в браузере
import logging                # модуль для логгирования
from functools import wraps   # декоратор для cохранения имени функции в обертке
from pathlib import Path      # для работы с путями у файлам (проверка на существование файла json)

import pandas as pd               # библиотека для работы с таблицами 
import matplotlib                 # библиотека для построения графиков
matplotlib.use("Agg")             # Matplotlib рисует график в памяти и сохраняет его в файл
import matplotlib.pyplot as plt   # модуль для рисования графиков


logging.basicConfig(              # базовая настройка логгирования
    filename="parser.log",        # имя файла для логгирования
    level=logging.INFO,           # уровень логгирования INFO и выше (WARNING, ERROR)
    format="%(asctime)s - %(levelname)s - %(message)s",  # формат: время, уровень, сообщение
    encoding="utf-8",              # кодировка файла для русских букв
)
logger = logging.getLogger(__name__)  # создаем логгер для данного файла(parser.py)


def log_time(func):                   # декоратор принимает функцию func
    @wraps(func)                      # сохраняет имя и dockstring функции funk
    def wrapper(*args, **kwargs):     # обертка принимающая любые аргументы 
        start = time.time()           # запоминаем время старта
        try:             
            result = func(*args, **kwargs)  # вызываем функцию
            elapsed = time.time() - start   # считаем время затраченное на выполнение функции
            logger.info(f"Функция '{func.__name__}' выполнена за {elapsed:.2f} сек.") # логгируем
            return result         # возвращаем результат
        except Exception as e:
            elapsed = time.time() - start  
            logger.error(f"Функция '{func.__name__}' ошибка за {elapsed:.2f} сек: {e}")  # логгируем ошибку
            raise
    return wrapper    # возвращаем обертку


@log_time       # начинаем замер времени выполнения функции
def open_wb(url: str = "https://www.wildberries.by") -> bool: # функция открытия сайта
    try:
        result = webbrowser.open(url, new=2)  # открыть в новой вкладке
        logger.info(f"Открыт сайт: {url}") # логгируем
        return result
    except Exception as e:
        logger.error(f"Не удалось открыть сайт: {e}") # логгируем ошибку
        return False


@log_time
def data_collecting(json_path: str = "wb_response.json") -> list[dict]:
    path = Path(json_path)
    if not path.exists():   # если файла нет
        logger.error(f"Файл {json_path} не найден. Сохраните ответ из DevTools.")
        raise FileNotFoundError(   # выбрасываем исключение
            f"Файл {json_path} не найден"
        )

    with open(path, "r", encoding="utf-8") as f: # открыть файл по пути path в режиме read c кодировкой для русских букв и положить в переменную f
        data = json.load(f)          # data становится словарем

    # В ответе search.wb.ru товары лежат в ключе "products"
    # В ответе catalog.wb.ru — в "data" -> "products"
    products = data.get("products")   # пробуем взять список товаров из "products"
    if products is None:        # если ключа нет 
        products = data.get("data", {}).get("products", [])   # ищем в data.products

    if not products:           # если список пустой
        logger.warning("В JSON не найдено поле 'products' с товарами.")  # логгируем предупреждение
        return []             # возвращаем пустой список

    collected_items = []             #список для сбора товаров 
    for item in products:              # перебираем каждый товар     
        sizes = item.get("sizes", [])   # берем список размеров
        price_info = sizes[0].get("price", {}) if sizes else {}  # цена первого размера
        sale_price = price_info.get("product", 0) / 100    # цена со скидкой 
        base_price = price_info.get("basic", 0) / 100     # без скидки

        collected_items.append({       # добавляем словарь с полями товара
            "Артикул": item.get("id"),
            "Бренд": item.get("brand"),
            "Название": item.get("name"),
            "Цена_BYN": sale_price,
            "Базовая_цена_BYN": base_price,
            "Рейтинг": item.get("reviewRating"),
            "Количество_отзывов": item.get("feedbacks"),
            "Ссылка": f"https://www.wildberries.by/catalog/{item.get('id')}/detail.aspx",
        })

    logger.info(f"Из JSON загружено товаров: {len(collected_items)}") # логгируем 
    return collected_items    # возвращаем список словарей

@log_time
def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    original = len(df)    # запоминаем исходное число строк
    df = df.drop_duplicates(subset=["Артикул"], keep="first") # убираем дубликаты по артикулу
    df = df.dropna(subset=["Название", "Бренд"]) # удаляем строки без названия 
    df = df[df["Цена_BYN"] > 0]   # оставляем товары с ценой > 0
    df["Артикул"] = df["Артикул"].astype(int) # артикул целое число
    df["Рейтинг"] = pd.to_numeric(df["Рейтинг"], errors="coerce").fillna(0)   # рейтинг - число, если нет то заменяет на 0
    df["Количество_отзывов"] = pd.to_numeric(df["Количество_отзывов"], errors="coerce").fillna(0).astype(int)
    logger.info(f"Очистка: было {original}, стало {len(df)}")  # логгируем результат
    return df.reset_index(drop=True)    # возвращаем с новыми индексами


@log_time
def interpret_data(df: pd.DataFrame) -> pd.DataFrame:
    df["Скидка_%"] = (
        (df["Базовая_цена_BYN"] - df["Цена_BYN"]) / df["Базовая_цена_BYN"] * 100
    ).round(1)     # добавляем колонку скидки в процентах с округлением до 1 знака после запятой
    df.loc[df["Базовая_цена_BYN"] == 0, "Скидка_%"] = 0 # на ноль не делим 
    df = df.sort_values("Количество_отзывов", ascending=False).reset_index(drop=True)  # сортируем отзывы по убыванию
    logger.info("Добавлен столбец 'Скидка_%', данные отсортированы.")  # логгируем
    return df     # воозваращаем результат



@log_time
def save_results(df: pd.DataFrame, csv_path: str = "wb_tvs_sample.csv", png_path: str = "price_hist.png"):
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")  # сохраняем таблицу в CSV
    logger.info(f"CSV сохранён: {csv_path} ({len(df)} строк)") # логгируем

    fig, ax = plt.subplots(figsize=(10, 6))   # создаем фигуру 10*6 и оси
    ax.hist(df["Цена_BYN"], bins=15, color="#3498db", edgecolor="white", alpha=0.85) # гистограмма цен, 15 корзин
    ax.set_title("Распределение цен на телевизоры (Wildberries.by)", fontsize=14, fontweight="bold") # заголовок
    ax.set_xlabel("Цена, BYN", fontsize=12) # название оси X
    ax.set_ylabel("Количество товаров", fontsize=12)  # название оси Y
    ax.grid(axis="y", alpha=0.3)  # сетка по горихонтали
    mean_price = df["Цена_BYN"].mean()  # средняя цена
    ax.axvline(mean_price, color="#e74c3c", linestyle="--", linewidth=2,
               label=f"Средняя: {mean_price:.2f} BYN")    # вертикальная линия средней цены
    ax.legend()  # показываем легенду
    plt.tight_layout()   # без обрезки и склейки
    plt.savefig(png_path, dpi=150, bbox_inches="tight") # сохраняем PNG
    plt.close(fig) # закрываем фигуру
    logger.info(f"Гистограмма сохранена: {png_path}")  # логгируем



if __name__ == "__main__":    # код выполняется только при прямом запуске файла
    open_wb()

    try:
        tv_data = data_collecting("wb_response.json")   # загружаем данные из JSON
    except FileNotFoundError as e: # если файла нет
        print(f"\n⚠ Ошибка: {e}")
        logger.error(str(e))
        raise SystemExit(1)   # завершаем программу с кодом 1

    if not tv_data:    # если товаров нет
        print("\n⚠ JSON загружен, но товары не найдены. Проверьте, что сохранили ответ с 'products'.")
        logger.warning("Пустой список товаров из JSON.")
        raise SystemExit(1)

    df = pd.DataFrame(tv_data)  # список словарей → DataFrame
    df = clean_data(df)        # очистка
    df = interpret_data(df)    # интерпретация данных(расчет скидок и сортировка количества отзывов по убыванию )
    save_results(df)     # сохраняем рузультаты

    pd.set_option("display.max_columns", None)  # показывать все столбцы
    pd.set_option("display.width", 200)          # ширина вывода
    pd.set_option("display.max_colwidth", 40)   #  максимальная ширина одной ячейки

    print("\n" + "=" * 70)
    print("ДАННЫЕ О ТЕЛЕВИЗОРАХ (из локального JSON)")
  
    print(df.to_string(index=False))  # печатаем таблицу без индексов
 
    print(f"Всего позиций: {len(df)}")
    print("CSV: wb_tvs_sample.csv")
    print("График: price_hist.png")
    print("Лог: parser.log")