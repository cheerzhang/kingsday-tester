import tkinter as tk
from tkinter import ttk
from role_ui import RoleTab
from event_ui import EventTab
from setup_ui import SetupTab
from auto_play_ui import AutoPlayTab

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        # ----------------------
        # Global UI scale (bigger)
        # ----------------------
        style = ttk.Style()
        try:
            style.theme_use("aqua")  # macOS native
        except Exception:
            pass

        style.configure(".", font=("Arial", 14))
        style.configure("TButton", padding=(12, 10))
        style.configure("TLabel", padding=(2, 2))
        style.configure("TEntry", padding=(6, 6))
        style.configure("TCombobox", padding=(6, 6))
        style.configure("TSpinbox", padding=(6, 6))
        style.configure("TLabelframe.Label", font=("Arial", 13, "bold"))

        # Make sure mouse clicks reliably focus the window
        self.after(100, self.focus_force)

        self.title("Kingsday Tester (Python) - Skeleton")
        self.geometry("900x600")

        # Top-level layout
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)

        # Notebook (tabs)
        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True)

        # Tab 1
        tab1 = RoleTab(nb)
        nb.add(tab1, text="Tab 1 (Role)")

        # Tab 2
        tab2 = EventTab(nb)
        nb.add(tab2, text="Tab 2 (Event)")
        
        # Tab 3: Setup
        tab3 = SetupTab(nb)
        nb.add(tab3, text="Tab 3 (Setup)")

        # Tab 4: AutoPlay
        tab4 = AutoPlayTab(nb)
        nb.add(tab4, text="Auto Play")

def run_app():
    app = MainApp()
    app.mainloop()