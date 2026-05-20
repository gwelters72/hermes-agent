# Hermes Agent Sequential Plugin

Dieses Repository ist ein Fork von `hermes-agent` und ergänzt ein Plugin,
das die Ausführung des Hermes-Agenten **seriell** oder **CPU/GPU‑optimiert**
steuert. Das Plugin wird automatisch von Hermes geladen, sobald dieses
Package installiert ist.

Damit funktioniert das Plugin in:

- `hermes` (CLI)
- `hermes server`
- `hermes web`
- `hermes api`
- Tools, Memory, Sessions
- OpenAI-kompatibler API

Es sind **keine Änderungen** am Hermes-Server oder der Hermes-CLI notwendig.

---

## 🚀 Features

- **Simple Mode**  
  Alle Modell- und Tool-Requests laufen strikt nacheinander.

- **CPU/GPU Mode**  
  Zwei getrennte Queues (CPU & GPU), parallele Ausführung möglich.

- **Timeouts**  
  Schutz vor Deadlocks und hängenden Modellen.

- **Automatische Plugin-Ladung**  
  Hermes lädt das Plugin automatisch über das Hook-System.

- **Konfigurierbar über `config.yaml`**  
  Optional im aktuellen Arbeitsverzeichnis.

- **Debug-Logging**  
  Optional aktivierbar, um Lock-Aktivität sichtbar zu machen.

---

## 📦 Installation

```bash
git clone https://github.com/gwelters72/hermes-agent-sequential.git
cd hermes-agent-sequential
chmod +x install.sh
./install.sh
