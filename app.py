from __future__ import annotations

import ctypes

from ui.main_window import PlatScoutApp


def main() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = PlatScoutApp()
    app.mainloop()


if __name__ == "__main__":
    main()
