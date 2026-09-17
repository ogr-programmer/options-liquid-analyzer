# Options Liquid Analyzer

Python-анализатор CSV-данных, записанных QUIK QLua-скриптом детектора mispricing опционов.

## Возможности

- чтение ZIP-архива или папки с CSV;
- нормализация числовых и временных полей;
- обогащение сигналов данными по фьючерсу;
- анализ частоты сигналов по страйкам, фьючерсам, типам опционов и экспирациям;
- анализ распределения edge и расстояния страйка до фьючерса;
- оценка длительности событий OPEN/CLOSED;
- выгрузка Excel и графиков.

## Установка

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

## Запуск

```bash
python options_analyzer.py --input path/to/archive.zip --output results
```

Или для папки:

```bash
python options_analyzer.py --input path/to/csv_folder --output results
```

Ожидаемые файлы:

- `options_market_data.csv`
- `options_signals_v3.csv`

Результаты сохраняются в указанную папку: Excel-файл `options_analysis.xlsx` и PNG-графики.

## Структура проекта

```text
options-liquid-analyzer/
├── options_analyzer.py
├── requirements.txt
├── README.md
├── .gitignore
├── data/
│   └── .gitkeep
└── results/
    └── .gitkeep
```

Данные и результаты анализа не включаются в репозиторий по умолчанию.
