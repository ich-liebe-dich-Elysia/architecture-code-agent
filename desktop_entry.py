"""Entry point used by the desktop shortcut and PyInstaller."""

from __future__ import annotations

import json
from pathlib import Path
import sys


def self_test() -> int:
    """Check packaged dependencies and widgets without network calls or UI."""
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False))}
    window = None
    desktop = None
    try:
        import ssl
        import tkinter as tk

        from agent.deepseek_client import DeepSeekClient
        from agent.desktop import AgentDesktop
        from agent.game_launcher import find_node
        from agent.llm_workflow import run_generation

        ssl.create_default_context()
        window = tk.Tk()
        window.withdraw()
        desktop = AgentDesktop(window)
        window.update_idletasks()
        report.update(
            ok=True,
            ssl_version=ssl.OPENSSL_VERSION,
            tk_version=tk.TkVersion,
            model=desktop.model.get(),
            workflow_imported=callable(run_generation) and callable(DeepSeekClient),
            node_available=bool(find_node()),
            initial_state="ready" if not desktop.busy else "unexpected_busy",
        )
    except Exception as error:
        report.update(error_type=type(error).__name__, error=str(error)[:1000])
    finally:
        if desktop is not None:
            desktop.closed = True
            desktop.launcher.stop()
        if window is not None:
            window.destroy()
    destination = root / ".build" / "exe-self-test.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        raise SystemExit(self_test())
    from agent.desktop import main

    main()
