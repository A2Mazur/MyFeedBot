import asyncio
import csv
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt

from bot.short_feed import summarize_to_one_sentence


@dataclass
class Result:
    category: str
    duration_sec: float
    input_len: int
    output_len: int
    reduction_pct: float


CATEGORY_RANGES = {
    "short": (100, 200),
    "medium": (300, 700),
    "long": (800, 1500),
}

BASE_TEXTS = {
    "short": [
        "Курс рубля укрепился после утренних торгов, трейдеры связывают это с ростом цен на сырьевые товары и снижением спроса на валюту.",
        "Маркетплейс запустил новую программу лояльности, обещая пользователям повышенные скидки и бесплатную доставку в регионы.",
        "Городские власти сообщили о ремонте ключевых развязок, из-за чего на выходных ожидаются заторы и временные перекрытия.",
        "В отчете сервиса доставки указано, что среднее время ожидания сократилось благодаря оптимизации маршрутов и расширению штата.",
        "Аналитики отметили рост интереса к ИИ-инструментам у малого бизнеса, особенно в сфере маркетинга и поддержки клиентов.",
    ],
    "medium": [
        "Финансовая компания подвела итоги квартала: выручка выросла на 12%, а операционная маржа осталась на уровне прошлого года. Руководство объясняет умеренный рост повышенными расходами на разработку и расширение команды продаж. На следующий квартал прогноз осторожный: ожидаются сезонные колебания и давление со стороны конкурентов.",
        "Обзор отрасли показывает, что рынок подписочных сервисов постепенно насыщается. Потребители стали внимательнее выбирать, какие услуги им действительно нужны, а какие можно отменить. Компании отвечают пакетными предложениями и гибкими тарифами, но это снижает средний чек.",
        "Власти представили план модернизации общественного транспорта, включая обновление подвижного состава и внедрение бесконтактной оплаты. Эксперты считают, что ключевой эффект будет заметен через год, когда завершится настройка инфраструктуры и логистики. До тех пор возможны временные сбои и пересмотр расписаний.",
        "Технологический обзор недели: крупные игроки фокусируются на безопасности, а стартапы — на скорости вывода функций. На фоне роста требований к соответствию стандартам компании пересматривают процессы разработки. Это увеличивает время релизов, но снижает риски инцидентов.",
        "В исследовании поведения пользователей указано, что люди чаще открывают приложения утром и вечером. Днем активность снижается, особенно в будни. Бренды учитывают эти пики и планируют рассылки и уведомления в оптимальные окна.",
    ],
    "long": [
        "Еженедельный аналитический обзор рынка демонстрирует смешанную динамику. В сегменте технологий отмечается рост спроса на инфраструктурные решения, в то время как потребительские сервисы сталкиваются с замедлением. Участники рынка связывают это с ростом затрат на привлечение пользователей и более осторожным поведением клиентов. Дополнительно компании сообщают о пересмотре бюджетов на маркетинг и переходе к долгосрочным проектам, которые дают эффект не сразу. Эксперты выделяют два тренда: повышение роли данных в управлении продуктами и усиление внимания к устойчивости бизнес-моделей. На этом фоне инвестиционная активность остается умеренной, но стратегические сделки продолжаются. В ближайшие месяцы ожидаются изменения в регулировании, что может повлиять на стоимость капитала и темпы роста. Отдельные аналитики прогнозируют стабилизацию во втором полугодии, если инфляционное давление продолжит снижаться.",
        "Большой обзор отрасли финансовых технологий: банки ускоряют внедрение цифровых каналов, одновременно усиливая контроль за рисками. В отчете указано, что пользователи ценят удобство, но требуют прозрачности и быстрого решения спорных ситуаций. На фоне роста конкуренции сервисы добавляют персонализированные рекомендации, однако это повышает нагрузку на команды безопасности. Исследователи отмечают, что успешные проекты фокусируются на трех направлениях: качественная поддержка, надежность инфраструктуры и предсказуемость тарифов. В отдельных регионах наблюдается рост доли безналичных операций, а в малых городах все еще сохраняется привязанность к наличным. На рынке также растет интерес к интеграциям с торговыми платформами и системами учета, что упрощает работу бизнеса. В перспективе ожидается усиление требований к хранению данных и отчетности, что потребует дополнительных инвестиций.",
        "В обзоре продуктовой аналитики за месяц команда описывает результаты A/B-тестов и основные выводы. По ключевым метрикам удержание выросло на 4%, но средний чек снизился из-за активности промо-кампаний. В отчет включены детали по сегментам: новые пользователи реагируют на упрощенную регистрацию, постоянные — на улучшенный поиск и фильтры. Также отмечается рост обращений в поддержку по вопросам оплаты, что указывает на необходимость доработки платежного потока. Команда рекомендует сосредоточиться на стабильности и оптимизации скорости загрузки, поскольку это напрямую влияет на конверсию. В дорожной карте запланированы улучшения интерфейса, пересмотр тарифов и более гибкая настройка уведомлений. Эксперты считают, что наибольший эффект даст устранение узких мест в процессе онбординга.",
        "Отчет по рынку медиа: аудитория распределяется между короткими форматами и глубокими аналитическими материалами. Издатели ищут баланс, чтобы удерживать внимание и одновременно повышать доверие. Рост расходов на производство контента заставляет редакции оптимизировать процессы, активнее использовать данные и автоматизацию. В исследовании подчеркивается, что пользователи меньше доверяют заголовкам, если они не соответствуют содержанию, и охотнее делятся материалами с четкой структурой. Дополнительно отмечается влияние социальных сетей, где алгоритмы задают тон распространению. В ближайшие месяцы ожидаются изменения в рекламном рынке и пересмотр форматов сотрудничества с брендами.",
        "Экономический обзор недели показывает, что в промышленности сохраняется умеренный рост, а в сфере услуг — признаки стабилизации. Компании пересматривают планы инвестиций, уделяя внимание эффективности и снижению издержек. На фоне неопределенности усиливается интерес к сценарному планированию и инструментам прогнозирования. Эксперты отмечают, что рост производительности зависит не только от технологий, но и от управления персоналом. В регионах фиксируются различия в динамике: крупные города растут быстрее, а малые — осторожнее. В среднесрочной перспективе ключевым фактором станет доступность финансирования и готовность бизнеса к обновлению оборудования.",
    ],
}

FILLER_SENTENCES = [
    "Это влияет на ожидания пользователей и пересмотр планов развития.",
    "Эксперты предупреждают, что эффект станет заметен не сразу.",
    "Компании тестируют новые форматы, чтобы повысить вовлеченность.",
    "Решение зависит от качества данных и стабильности инфраструктуры.",
    "Рынок реагирует на изменения умеренно, без резких колебаний.",
]


def normalize_length(text: str, min_len: int, max_len: int) -> str:
    text = " ".join((text or "").split())
    if not text:
        return text

    idx = 0
    while len(text) < min_len:
        text = f"{text} {FILLER_SENTENCES[idx % len(FILLER_SENTENCES)]}"
        idx += 1

    if len(text) > max_len:
        cut = text[:max_len]
        last = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind("… "))
        if last != -1:
            text = cut[: last + 1]
        else:
            text = cut.rstrip()
            if not text.endswith("."):
                text += "."

    return text


def build_tests(per_category: int) -> list[tuple[str, str]]:
    tests: list[tuple[str, str]] = []
    for category, (min_len, max_len) in CATEGORY_RANGES.items():
        base = BASE_TEXTS[category]
        for i in range(per_category):
            text = base[i % len(base)]
            text = normalize_length(text, min_len, max_len)
            tests.append((category, text))
    return tests


async def process_text(category: str, text: str) -> tuple[str, Result]:
    start = time.time()
    output = await summarize_to_one_sentence(text)
    duration = time.time() - start
    input_len = len(text)
    output_len = len(output)
    reduction_pct = 0.0
    if input_len > 0:
        reduction_pct = (1.0 - (output_len / input_len)) * 100.0
    return output, Result(category, duration, input_len, output_len, reduction_pct)


async def run_tests(per_category: int) -> tuple[list[str], list[Result]]:
    outputs: list[str] = []
    results: list[Result] = []
    for category, text in build_tests(per_category):
        output, result = await process_text(category, text)
        outputs.append(output)
        results.append(result)
    return outputs, results


def write_log(results: list[Result], log_path: Path) -> None:
    lines = ["category,time_sec,input_len,output_len,reduction_pct"]
    for r in results:
        lines.append(
            f"{r.category},{r.duration_sec:.6f},{r.input_len},{r.output_len},{r.reduction_pct:.2f}"
        )
    log_path.write_text("\n".join(lines), encoding="utf-8")


def write_csv(results: list[Result], csv_path: Path) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "time_sec", "input_len", "output_len", "reduction_pct"])
        for r in results:
            writer.writerow(
                [
                    r.category,
                    f"{r.duration_sec:.6f}",
                    r.input_len,
                    r.output_len,
                    f"{r.reduction_pct:.2f}",
                ]
            )


def plot_processing_time(results: list[Result], path: Path) -> None:
    x = list(range(1, len(results) + 1))
    y = [r.duration_sec for r in results]
    plt.figure(figsize=(8, 4))
    plt.plot(x, y, marker="o")
    plt.title("Processing Time per Test")
    plt.xlabel("Test #")
    plt.ylabel("Time (sec)")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def plot_text_lengths(results: list[Result], path: Path) -> None:
    x = list(range(1, len(results) + 1))
    y_input = [r.input_len for r in results]
    y_output = [r.output_len for r in results]
    plt.figure(figsize=(8, 4))
    plt.plot(x, y_input, marker="o", label="Input length")
    plt.plot(x, y_output, marker="o", label="Output length")
    plt.title("Text Length Comparison")
    plt.xlabel("Test #")
    plt.ylabel("Length (chars)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def plot_reduction_by_category(results: list[Result], path: Path) -> None:
    categories = ["short", "medium", "long"]
    averages: list[float] = []
    for category in categories:
        values = [r.reduction_pct for r in results if r.category == category]
        avg = sum(values) / len(values) if values else 0.0
        averages.append(avg)
    plt.figure(figsize=(6, 4))
    plt.bar(categories, averages)
    plt.title("Average Reduction by Category")
    plt.xlabel("Category")
    plt.ylabel("Reduction (%)")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def summarize(results: list[Result]) -> dict:
    durations = [r.duration_sec for r in results]
    reductions = [r.reduction_pct for r in results]
    avg_time = sum(durations) / len(durations) if durations else 0.0
    min_time = min(durations) if durations else 0.0
    max_time = max(durations) if durations else 0.0
    avg_reduction = sum(reductions) / len(reductions) if reductions else 0.0

    by_category: dict[str, dict[str, float]] = {}
    for category in CATEGORY_RANGES.keys():
        cat_times = [r.duration_sec for r in results if r.category == category]
        cat_reductions = [r.reduction_pct for r in results if r.category == category]
        by_category[category] = {
            "avg_time": sum(cat_times) / len(cat_times) if cat_times else 0.0,
            "avg_reduction": sum(cat_reductions) / len(cat_reductions) if cat_reductions else 0.0,
            "count": float(len(cat_times)),
        }

    return {
        "total": len(results),
        "avg_time": avg_time,
        "min_time": min_time,
        "max_time": max_time,
        "avg_reduction": avg_reduction,
        "by_category": by_category,
    }


async def main() -> None:
    per_category = 12
    outputs, results = await run_tests(per_category)
    _ = outputs

    write_log(results, Path("performance.log"))
    write_csv(results, Path("performance.csv"))

    plot_processing_time(results, Path("processing_time.png"))
    plot_text_lengths(results, Path("text_compression.png"))
    plot_reduction_by_category(results, Path("reduction_by_category.png"))

    summary = summarize(results)

    print("Performance report")
    print(f"Total tests: {summary['total']}")
    print(f"Average time: {summary['avg_time']:.6f} sec")
    print(f"Min time: {summary['min_time']:.6f} sec")
    print(f"Max time: {summary['max_time']:.6f} sec")
    print(f"Average reduction: {summary['avg_reduction']:.2f}%")
    print("By category:")
    for category in ["short", "medium", "long"]:
        cat = summary["by_category"].get(category, {})
        print(
            f"- {category}: avg time {cat.get('avg_time', 0.0):.6f} sec, "
            f"avg reduction {cat.get('avg_reduction', 0.0):.2f}%"
        )


if __name__ == "__main__":
    asyncio.run(main())
