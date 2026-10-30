import os
import time
import random
import threading

# Параметры нагрузки (можно переопределить через env)
CPU_THREADS = int(os.getenv("CPU_THREADS", "2"))
MEM_STEP_MB = int(os.getenv("MEM_STEP_MB", "50"))      # сколько МБ аллоцировать за шаг
MEM_SLEEP = float(os.getenv("MEM_SLEEP", "1.0"))       # пауза между шагами
MEM_LIMIT_MB = int(os.getenv("MEM_LIMIT_MB", "1024"))  # потолок, чтобы не убить ноду

memory_hog = []  # глобальный список — держим ссылки, чтобы GC не собрал


def cpu_burner():
    """Бесконечно жрёт CPU бессмысленными вычислениями."""
    x = 0.0
    while True:
        for _ in range(1_000_000):
            x = (x * 1.0000001) % 3.14159 + random.random()
        # небольшая пауза, чтобы не 100% всегда — «имитация работы»
        time.sleep(0.05)


def memory_burner():
    """Постепенно выделяет память блоками, пока не упрётся в MEM_LIMIT_MB."""
    global memory_hog
    while True:
        current_mb = len(memory_hog) * MEM_STEP_MB
        if current_mb < MEM_LIMIT_MB:
            memory_hog.append(bytearray(MEM_STEP_MB * 1024 * 1024))
            print(f"[mem] allocated ~{current_mb + MEM_STEP_MB} MB", flush=True)
        else:
            # «полезная работа»: бесконечно шафлим и пересчитываем
            random.shuffle(memory_hog)
            print(f"[mem] holding {current_mb} MB, working...", flush=True)
        time.sleep(MEM_SLEEP)


def main():
    print(f"[batch] starting: cpu_threads={CPU_THREADS} "
          f"mem_limit={MEM_LIMIT_MB}MB step={MEM_STEP_MB}MB", flush=True)

    threads = [threading.Thread(target=cpu_burner, daemon=True)
               for _ in range(CPU_THREADS)]
    threads.append(threading.Thread(target=memory_burner, daemon=True))

    for t in threads:
        t.start()

    while True:
        time.sleep(60)
        print("[batch] still working (no-op)...", flush=True)


if __name__ == "__main__":
    main()