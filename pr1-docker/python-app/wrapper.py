import ctypes, ctypes.util, os, sys
from pathlib import Path

SCMP_ACT_ERRNO = 0x00050000
EPERM = 1
lib = ctypes.CDLL("libseccomp.so.2", use_errno=True)
lib.seccomp_init.argtypes = [ctypes.c_uint32]; lib.seccomp_init.restype = ctypes.c_void_p
lib.seccomp_load.argtypes = [ctypes.c_void_p]
lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_int]

ctypes.CDLL(ctypes.util.find_library("c")).prctl(38, 1, 0, 0, 0)
ctx = lib.seccomp_init(0x7FFF0000)

# Блокируем оба syscall'а
lib.seccomp_rule_add(ctx, SCMP_ACT_ERRNO | EPERM, 83, 0)   # mkdir (x86_64)
lib.seccomp_rule_add(ctx, SCMP_ACT_ERRNO | EPERM, 258, 0)  # mkdirat (x86_64)

rc = lib.seccomp_load(ctx)
print(f"seccomp_load = {rc}", file=sys.stderr, flush=True)
if rc != 0:
    sys.exit(1)
print("seccomp loaded OK, about to execve", file=sys.stderr, flush=True)

os.chdir(Path(__file__).resolve().parent)
os.execvp(sys.executable, [
    sys.executable, "-m", "uvicorn", "app:app",
    "--host", "0.0.0.0", "--port", "8000",
])