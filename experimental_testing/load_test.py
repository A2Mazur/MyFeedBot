import asyncio
import csv
import logging
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt

from bot.short_feed import summarize_to_one_sentence


@dataclass
class LevelResult:
    concurrency: int
    total_tasks: int
    success_count: int
    error_count: int
    avg_time_sec: float
    min_time_sec: float
    max_time_sec: float
    total_wall_time_sec: float
    throughput_rps: float


CONCURRENCY_LEVELS = [1, 10, 50, 100, 200]

TEST_TEXTS = [
    "Рынок показал умеренный рост на фоне позитивной статистики, но инвесторы сохраняют осторожность из-за неопределенности в регуляторной повестке.",
    "В продуктовой аналитике отметили, что новые пользователи чаще завершают регистрацию, если им заранее показывать пример полезных сценариев.",
    "Обзор отрасли: компании пересматривают стратегии закупок, переходя на более гибкие контракты и делая ставку на локальных поставщиков.",
    "Команда поддержки зафиксировала снижение числа обращений после обновления интерфейса и упрощения процесса оплаты.",
    "В исследовании сообщается, что средняя глубина просмотра выросла, когда контент стали группировать по интересам и теме.",
    "Еженедельный обзор показывает, что сегмент облачных решений растет быстрее общего рынка. Это связано с миграцией критичных систем и ростом затрат на кибербезопасность. При этом часть компаний откладывает переход из-за отсутствия специалистов и рисков простоя. Эксперты считают, что в ближайшие месяцы ключевым фактором станет скорость внедрения стандартизированных практик и возможность измерять эффект на уровне бизнеса.",
    "Аналитический отчет по финтех-рынку отмечает рост безналичных транзакций в крупных городах и сохраняющуюся роль наличных в регионах. Банки усиливают контроль за рисками, а новые игроки делают ставку на партнерские интеграции. Основное ожидание — рост требований к отчетности и защите данных, что повысит стоимость разработки.",
    "В обзоре продуктовой команды указано, что A/B-тесты показали рост удержания, но снизили средний чек. Причина — агрессивные промо-кампании. В качестве следующего шага предлагается оптимизировать воронку и пересмотреть условия скидок, сохранив фокус на долгосрочной ценности пользователя.",
    "Отчет по медиа-рынку фиксирует повышение доли коротких форматов и одновременный спрос на глубокую аналитику. Издатели пересматривают стратегии, чтобы удерживать внимание и повышать доверие. Также отмечается рост роли рекомендаций и алгоритмов в распространении контента.",
    "Экономический обзор недели показывает умеренный рост в промышленности и стабилизацию в сфере услуг. Компании пересматривают планы инвестиций, уделяя внимание эффективности. В среднесрочной перспективе ключевым фактором остается доступность финансирования и готовность к обновлению оборудования.",
]


def _first_sentence(text: str) -> str:
    text = " ".join((text or "").split())
    if not text:
        return ""
    for sep in (". ", "! ", "? ", "… "):
        idx = text.find(sep)
        if idx != -1:
            return text[: idx + 1]
    return text


async def mock_processing(text: str) -> str:
    await asyncio.sleep(random.uniform(0.05, 0.2))
    return _first_sentence(text)


def build_tasks(concurrency: int, texts_per_user: int) -> list[str]:
    tasks: list[str] = []
    for user_idx in range(concurrency):
        for i in range(texts_per_user):
            text = TEST_TEXTS[(user_idx * texts_per_user + i) % len(TEST_TEXTS)]
            tasks.append(text)
    return tasks


async def simulate_user_request(text: str, mode: str) -> None:
    if mode == "mock":
        await mock_processing(text)
        return
    await summarize_to_one_sentence(text)


async def run_level(concurrency: int, texts_per_user: int, mode: str) -> LevelResult:
    texts = build_tasks(concurrency, texts_per_user)

    async def run_task(text: str) -> tuple[bool, float, str | None]:
        start = time.perf_counter()
        try:
            await simulate_user_request(text, mode)
            duration = time.perf_counter() - start
            return True, duration, None
        except Exception as exc:
            duration = time.perf_counter() - start
            return False, duration, str(exc)

    wall_start = time.perf_counter()
    results = await asyncio.gather(*[run_task(t) for t in texts])
    total_wall = time.perf_counter() - wall_start

    success_durations = [d for ok, d, _ in results if ok]
    error_count = sum(1 for ok, _, _ in results if not ok)
    success_count = len(success_durations)

    avg_time = sum(success_durations) / success_count if success_count else 0.0
    min_time = min(success_durations) if success_durations else 0.0
    max_time = max(success_durations) if success_durations else 0.0
    throughput = success_count / total_wall if total_wall > 0 else 0.0

    return LevelResult(
        concurrency=concurrency,
        total_tasks=len(texts),
        success_count=success_count,
        error_count=error_count,
        avg_time_sec=avg_time,
        min_time_sec=min_time,
        max_time_sec=max_time,
        total_wall_time_sec=total_wall,
        throughput_rps=throughput,
    )


def write_csv(results: list[LevelResult], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "concurrency",
                "total_tasks",
                "success_count",
                "error_count",
                "avg_time_sec",
                "min_time_sec",
                "max_time_sec",
                "total_wall_time_sec",
                "throughput_rps",
            ]
        )
        for r in results:
            writer.writerow(
                [
                    r.concurrency,
                    r.total_tasks,
                    r.success_count,
                    r.error_count,
                    f"{r.avg_time_sec:.6f}",
                    f"{r.min_time_sec:.6f}",
                    f"{r.max_time_sec:.6f}",
                    f"{r.total_wall_time_sec:.6f}",
                    f"{r.throughput_rps:.3f}",
                ]
            )


def write_log(results: list[LevelResult], path: Path) -> None:
    lines = [
        "concurrency,total_tasks,success_count,error_count,avg_time_sec,min_time_sec,max_time_sec,total_wall_time_sec,throughput_rps"
    ]
    for r in results:
        lines.append(
            f"{r.concurrency},{r.total_tasks},{r.success_count},{r.error_count},"
            f"{r.avg_time_sec:.6f},{r.min_time_sec:.6f},{r.max_time_sec:.6f},"
            f"{r.total_wall_time_sec:.6f},{r.throughput_rps:.3f}"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def plot_avg_time(results: list[LevelResult], path: Path) -> None:
    x = [r.concurrency for r in results]
    y = [r.avg_time_sec for r in results]
    plt.figure(figsize=(7, 4))
    plt.plot(x, y, marker="o")
    plt.title("Average Processing Time vs Concurrency")
    plt.xlabel("Concurrent users")
    plt.ylabel("Average time (sec)")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def plot_throughput(results: list[LevelResult], path: Path) -> None:
    x = [r.concurrency for r in results]
    y = [r.throughput_rps for r in results]
    plt.figure(figsize=(7, 4))
    plt.plot(x, y, marker="o")
    plt.title("Throughput vs Concurrency")
    plt.xlabel("Concurrent users")
    plt.ylabel("Throughput (tasks/sec)")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def plot_errors(results: list[LevelResult], path: Path) -> None:
    x = [r.concurrency for r in results]
    y = [r.error_count for r in results]
    plt.figure(figsize=(7, 4))
    plt.plot(x, y, marker="o")
    plt.title("Errors vs Concurrency")
    plt.xlabel("Concurrent users")
    plt.ylabel("Errors")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def print_report(results: list[LevelResult]) -> None:
    print("Load test report")
    for r in results:
        print(
            f"- concurrency {r.concurrency}: success {r.success_count}/{r.total_tasks}, "
            f"errors {r.error_count}, avg {r.avg_time_sec:.6f}s, min {r.min_time_sec:.6f}s, "
            f"max {r.max_time_sec:.6f}s, wall {r.total_wall_time_sec:.6f}s, "
            f"throughput {r.throughput_rps:.3f} rps"
        )


async def main() -> None:
    mode = os.getenv("LOAD_TEST_MODE", "mock").lower()
    texts_per_user = int(os.getenv("LOAD_TEST_TEXTS_PER_USER", str(len(TEST_TEXTS))))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler()],
    )

    logging.info("Load test started. mode=%s users=%s texts_per_user=%s", mode, CONCURRENCY_LEVELS, texts_per_user)

    results: list[LevelResult] = []
    for concurrency in CONCURRENCY_LEVELS:
        logging.info("Running level: %s users", concurrency)
        level_result = await run_level(concurrency, texts_per_user, mode)
        results.append(level_result)
        logging.info(
            "Level done: users=%s total=%s success=%s errors=%s avg=%.6f min=%.6f max=%.6f wall=%.6f rps=%.3f",
            level_result.concurrency,
            level_result.total_tasks,
            level_result.success_count,
            level_result.error_count,
            level_result.avg_time_sec,
            level_result.min_time_sec,
            level_result.max_time_sec,
            level_result.total_wall_time_sec,
            level_result.throughput_rps,
        )

    write_csv(results, Path("load_test_results.csv"))
    write_log(results, Path("load_test.log"))

    plot_avg_time(results, Path("load_avg_time.png"))
    plot_throughput(results, Path("load_throughput.png"))
    plot_errors(results, Path("load_errors.png"))

    print_report(results)


if __name__ == "__main__":
    asyncio.run(main())
