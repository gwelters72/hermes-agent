import threading
import yaml
import time
from pathlib import Path

# ============================================================
# CONFIG LADEN
# ============================================================

def load_config():
    # Suche config.yaml im aktuellen Verzeichnis oder im Plugin-Verzeichnis
    cfg = Path("config.yaml")
    if not cfg.exists():
        cfg = Path(__file__).parent / "config.yaml"
        
    if cfg.exists():
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass

    return {
        "mode": "simple",
        "timeout": 120,
        "cpu_models": [],
        "gpu_models": [],
        "debug": False,
    }


CONFIG = load_config()

MODE = CONFIG.get("mode", "simple")
TIMEOUT = CONFIG.get("timeout", 120)
CPU_MODEL_NAMES = set(CONFIG.get("cpu_models", []))
GPU_MODEL_NAMES = set(CONFIG.get("gpu_models", []))
DEBUG = CONFIG.get("debug", False)

# ============================================================
# LOCKS
# ============================================================

GLOBAL_LOCK = threading.Lock()
CPU_LOCK = threading.Lock()
GPU_LOCK = threading.Lock()

# Speicher für aktive Locks pro Session/Task
# Key: (session_id, task_id, type) -> Lock
_ACTIVE_LOCKS = {}
_LOCK_MAP_LOCK = threading.Lock()

# ============================================================
# HELFER
# ============================================================

def is_cpu_model(model_name):
    if not model_name: return False
    return model_name in CPU_MODEL_NAMES or any(model_name.startswith(p) for p in CPU_MODEL_NAMES)


def is_gpu_model(model_name):
    if not model_name: return False
    return model_name in GPU_MODEL_NAMES or any(model_name.startswith(p) for p in GPU_MODEL_NAMES)


def select_lock(model_name):
    if MODE == "cpu_gpu":
        if is_cpu_model(model_name):
            return CPU_LOCK, "CPU"
        if is_gpu_model(model_name):
            return GPU_LOCK, "GPU"
        return GLOBAL_LOCK, "GLOBAL"

    return GLOBAL_LOCK, "GLOBAL"


# ============================================================
# CONTROLLER
# ============================================================

class SequentialController:
    def __init__(self, timeout):
        self.timeout = timeout

    def _acquire(self, session_id, task_id, model_name, lock_type):
        lock, lock_name = select_lock(model_name)
        start_wait = time.time()
        
        acquired = lock.acquire(timeout=self.timeout)
        if not acquired:
            raise TimeoutError(f"Timeout beim Warten auf Lock ({self.timeout}s) für {lock_name}.")
            
        waited = time.time() - start_wait
        if DEBUG:
            print(f"[SEQ] model={model_name} lock={lock_name} waited={waited:.3f}s")
            
        with _LOCK_MAP_LOCK:
            _ACTIVE_LOCKS[(session_id, task_id, lock_type)] = lock

    def _release(self, session_id, task_id, lock_type):
        with _LOCK_MAP_LOCK:
            lock = _ACTIVE_LOCKS.pop((session_id, task_id, lock_type), None)
            
        if lock:
            lock.release()
            if DEBUG:
                print(f"[SEQ] released lock for session={session_id} task={task_id} type={lock_type}")

    # --- LLM Hooks ---

    def before_agent_step(self, session_id="", model="", **kwargs):
        # Wird bei 'pre_llm_call' aufgerufen
        self._acquire(session_id, "llm", model, "llm")
        return None

    def after_agent_step(self, session_id="", **kwargs):
        # Wird bei 'post_llm_call' aufgerufen
        self._release(session_id, "llm", "llm")
        return None


# ============================================================
# ABWÄRTSKOMPATIBILITÄT (falls benötigt)
# ============================================================

def build_sequential_plugins():
    # Diese Funktion wird im neuen System nicht mehr direkt benötigt,
    # da die Registrierung über __init__.py erfolgt.
    controller = SequentialController(timeout=TIMEOUT)
    return [
        controller.before_agent_step,
        controller.after_agent_step,
    ]
