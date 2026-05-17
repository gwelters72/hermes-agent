from .sequential_model import build_sequential_plugins

def register(ctx):
    # Die build_sequential_plugins Funktion gibt eine Liste von Funktionen zurück.
    # Da wir das Plugin-System von Hermes nutzen, registrieren wir die Hooks hier einzeln.
    
    # Wir laden die Konfiguration, um zu entscheiden, welche Hooks wir registrieren.
    from .sequential_model import CONFIG, SequentialController
    
    controller = SequentialController(timeout=CONFIG.get("timeout", 120))
    
    # Registrierung der Hooks
    # Hinweis: In der aktuellen Hermes-Version sind Plugin-Hooks synchron.
    # Die sequential_model.py muss daher auf threading.Lock umgestellt werden,
    # um im synchronen Kontext zu funktionieren, oder wir nutzen eine andere Strategie.
    
    ctx.register_hook("pre_llm_call", controller.before_agent_step)
    ctx.register_hook("post_llm_call", controller.after_agent_step)
