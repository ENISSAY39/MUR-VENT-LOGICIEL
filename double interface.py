import tkinter as tk
from tkinter import ttk
import json
import threading
import time
import random

class GVMControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Contrôle GVM - Système de Ventilation Modulaire")

        self.grid_rows = 3
        self.grid_cols = 3
        self.fan_status = {}
        self.publish_cell = 24
        self.current_mode = "percentage"
        self.selected_fans = set()

        self.initialize_fan_data()
        self.create_frames()
        self.show_home()

        self.update_thread = threading.Thread(target=self.update_rpm_data, daemon=True)
        self.update_thread.start()

    def create_frames(self):
        self.home_frame = ttk.Frame(self.root)

        ttk.Label(self.home_frame, text="Système de Contrôle GVM", font=('Helvetica', 16)).pack(pady=20)
        ttk.Button(self.home_frame, text="Mode Contrôle (Puissance %)",
                   command=lambda: self.show_grid_mode("percentage")).pack(pady=10, ipadx=20, ipady=10)
        ttk.Button(self.home_frame, text="Mode Surveillance (RPM)",
                   command=lambda: self.show_grid_mode("rpm")).pack(pady=10, ipadx=20, ipady=10)

        self.control_frame = ttk.Frame(self.root)
        self.create_control_interface()

        self.monitor_frame = ttk.Frame(self.root)
        self.create_monitor_interface()

    def show_home(self):
        self.hide_all_frames()
        self.home_frame.pack(fill=tk.BOTH, expand=True)

    def show_grid_mode(self, mode):
        self.current_mode = mode
        self.hide_all_frames()

        if mode == "percentage":
            self.control_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.monitor_frame.pack(fill=tk.BOTH, expand=True)

        if not hasattr(self, 'back_button') or not self.back_button.winfo_ismapped():
            self.back_button.pack(side=tk.BOTTOM, pady=10)

    def hide_all_frames(self):
        for frame in [self.home_frame, self.control_frame, self.monitor_frame]:
            frame.pack_forget()
        if hasattr(self, 'back_button'):
            self.back_button.pack_forget()

    def initialize_fan_data(self):
        for cell_row in range(1, self.grid_rows + 1):
            for cell_col in range(1, self.grid_cols + 1):
                cell_id = f"{cell_row}{cell_col}"
                self.fan_status[cell_id] = {
                    'power': [0] * 9,
                    'rpm': [0] * 9,
                    'active': False,
                    'functional': True
                }

    def create_control_interface(self):
        main_frame = ttk.Frame(self.control_frame, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        container = ttk.Frame(main_frame)
        container.pack(fill=tk.BOTH, expand=True)

        buttons_frame = ttk.Frame(container)
        buttons_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        ttk.Label(buttons_frame, text="Contrôles", font=('Helvetica', 12)).pack(pady=5)
        ttk.Label(buttons_frame, text="Puissance (%):").pack(pady=(10,0))

        self.power_var = tk.IntVar(value=0)
        power_slider = ttk.Scale(buttons_frame, from_=0, to=100, variable=self.power_var,
                                 command=lambda v: self.power_label.config(text=f"{int(float(v))}%"))
        power_slider.pack(padx=5)
        self.power_label = ttk.Label(buttons_frame, text="0%")
        self.power_label.pack(pady=(0, 10))

        ttk.Button(buttons_frame, text="Appliquer à sélection", command=self.apply_power_selected).pack(pady=5, ipadx=10, ipady=5)
        ttk.Button(buttons_frame, text="Appliquer à tous", command=self.apply_power_all).pack(pady=5, ipadx=10, ipady=5)
        ttk.Button(buttons_frame, text="Arrêter tout", command=self.stop_all).pack(pady=5, ipadx=10, ipady=5)
        ttk.Button(buttons_frame, text="Générer JSON", command=self.show_json).pack(pady=5, ipadx=10, ipady=5)

        ttk.Label(buttons_frame, text="Cellule de publication:").pack(pady=(20, 5))
        self.publish_var = tk.StringVar(value=str(self.publish_cell))
        ttk.Entry(buttons_frame, textvariable=self.publish_var, width=5).pack()

        grid_frame = ttk.Frame(container)
        grid_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.create_fan_grid(grid_frame, "percentage")

        self.status_console = tk.Text(main_frame, height=10, state=tk.DISABLED)
        self.status_console.pack(fill=tk.BOTH, expand=True, pady=10)
        scrollbar = ttk.Scrollbar(self.status_console)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.status_console.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.status_console.yview)

        if not hasattr(self, 'back_button'):
            self.back_button = ttk.Button(self.root, text="Retour à l'accueil", command=self.show_home)

    def create_monitor_interface(self):
        main_frame = ttk.Frame(self.monitor_frame, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        grid_frame = ttk.Frame(main_frame)
        grid_frame.pack(fill=tk.BOTH, expand=True)

        self.create_fan_grid(grid_frame, "rpm")

        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)

        ttk.Label(control_frame, text="Mode Surveillance RPM", font=('Helvetica', 12)).pack()

        legend_frame = ttk.Frame(control_frame)
        legend_frame.pack(pady=5)
        ttk.Label(legend_frame, text="Légende:").grid(row=0, column=0, padx=5)
        tk.Label(legend_frame, text="   Normal   ", bg="green", fg="white").grid(row=0, column=1, padx=5)
        tk.Label(legend_frame, text="   Erreur   ", bg="red", fg="white").grid(row=0, column=2, padx=5)
        tk.Label(legend_frame, text="   Inactif   ", bg="SystemButtonFace").grid(row=0, column=3, padx=5)

        if not hasattr(self, 'back_button'):
            self.back_button = ttk.Button(self.root, text="Retour à l'accueil", command=self.show_home)

    def create_fan_grid(self, parent, mode):
        if hasattr(self, f'{mode}_grid_frame'):
            getattr(self, f'{mode}_grid_frame').destroy()

        grid_frame = ttk.Frame(parent)
        grid_frame.pack(fill=tk.BOTH, expand=True)
        setattr(self, f'{mode}_grid_frame', grid_frame)

        for i in range(self.grid_rows):
            grid_frame.rowconfigure(i, weight=1)
        for j in range(self.grid_cols):
            grid_frame.columnconfigure(j, weight=1)

        for cell_row in range(1, self.grid_rows + 1):
            for cell_col in range(1, self.grid_cols + 1):
                cell_id = f"{cell_row}{cell_col}"
                cell_frame = ttk.LabelFrame(grid_frame, text=f"Cell {cell_id}", padding="5")
                cell_frame.grid(row=cell_row - 1, column=cell_col - 1, padx=2, pady=2, sticky="nsew")

                for fan_row in range(3):
                    for fan_col in range(3):
                        fan_idx = fan_row * 3 + fan_col
                        btn = tk.Button(cell_frame, width=8, height=2)

                        if mode == "percentage":
                            btn.config(text="0%",
                                       command=lambda cr=cell_row, cc=cell_col, fr=fan_row + 1, fc=fan_col + 1:
                                       self.select_fan(cr, cc, fr, fc))
                        else:
                            btn.config(text="0 RPM")

                        btn.grid(row=fan_row, column=fan_col, padx=1, pady=1)

                        key = f"btn_{fan_idx}" if mode == "percentage" else f"rpm_btn_{fan_idx}"
                        self.fan_status[cell_id][key] = btn

    def select_fan(self, cell_row, cell_col, fan_row, fan_col):
        cell_id = f"{cell_row}{cell_col}"
        fan_idx = (fan_row - 1) * 3 + (fan_col - 1)
        fan_key = (cell_id, fan_idx)
        btn = self.fan_status[cell_id][f"btn_{fan_idx}"]

        if fan_key in self.selected_fans:
            self.selected_fans.remove(fan_key)
            power = self.fan_status[cell_id]['power'][fan_idx]
            rpm = self.fan_status[cell_id]['rpm'][fan_idx]
            expected = power * 10
            functional = abs(rpm - expected) <= 500
            if power > 0:
                btn.config(bg="green" if functional else "red", fg="white")
            else:
                btn.config(bg="SystemButtonFace", fg="black")
        else:
            self.selected_fans.add(fan_key)
            btn.config(bg="blue", fg="white")

        self.log_status(f"Ventilateurs sélectionnés : {len(self.selected_fans)}")

    def apply_power_selected(self):
        if not self.selected_fans:
            self.log_status("Aucun ventilateur sélectionné.")
            return
        power = self.power_var.get()
        for cell_id, fan_idx in self.selected_fans:
            self.fan_status[cell_id]['power'][fan_idx] = power
            btn = self.fan_status[cell_id][f"btn_{fan_idx}"]
            btn.config(text=f"{power}%", bg="blue" if power > 0 else "SystemButtonFace",
                       fg="white" if power > 0 else "black")
        self.log_status(f"Puissance appliquée: {power}% à {len(self.selected_fans)} ventilateurs sélectionnés")
        self.generate_command_json()

    def apply_power_all(self):
        power = self.power_var.get()
        self.selected_fans.clear()
        for cell_row in range(1, self.grid_rows + 1):
            for cell_col in range(1, self.grid_cols + 1):
                cell_id = f"{cell_row}{cell_col}"
                for fan_idx in range(9):
                    self.fan_status[cell_id]['power'][fan_idx] = power
                    btn = self.fan_status[cell_id][f"btn_{fan_idx}"]
                    btn.config(text=f"{power}%", bg="green" if power > 0 else "SystemButtonFace",
                               fg="white" if power > 0 else "black")
        self.log_status(f"Puissance appliquée: {power}% à tous les ventilateurs")
        self.generate_command_json()

    def stop_all(self):
        self.power_var.set(0)
        self.selected_fans.clear()
        for cell_row in range(1, self.grid_rows + 1):
            for cell_col in range(1, self.grid_cols + 1):
                cell_id = f"{cell_row}{cell_col}"
                for fan_idx in range(9):
                    self.fan_status[cell_id]['power'][fan_idx] = 0
                    btn = self.fan_status[cell_id][f"btn_{fan_idx}"]
                    btn.config(text="0%", bg="SystemButtonFace", fg="black")
        self.log_status("Tous les ventilateurs arrêtés")
        self.generate_command_json()

    def update_rpm_data(self):
        while True:
            time.sleep(1)
            for cell_row in range(1, self.grid_rows + 1):
                for cell_col in range(1, self.grid_cols + 1):
                    cell_id = f"{cell_row}{cell_col}"
                    for fan_idx in range(9):
                        power = self.fan_status[cell_id]['power'][fan_idx]
                        rpm = power * 10 + random.randint(-300, 300)
                        rpm = max(rpm, 0)
                        self.fan_status[cell_id]['rpm'][fan_idx] = rpm

                        if self.current_mode == "rpm":
                            btn = self.fan_status[cell_id].get(f"rpm_btn_{fan_idx}")
                            if btn:
                                expected = power * 10
                                functional = abs(rpm - expected) <= 500
                                if power == 0:
                                    btn.config(text="0 RPM", bg="SystemButtonFace", fg="black")
                                else:
                                    btn.config(text=f"{rpm} RPM", bg="green" if functional else "red", fg="white")

    def show_json(self):
        json_str = self.generate_command_json()

        # Création d'une nouvelle fenêtre
        json_window = tk.Toplevel(self.root)
        json_window.title("Commande JSON")

        # Zone de texte pour afficher le JSON
        text_widget = tk.Text(json_window, wrap=tk.WORD)
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_widget.insert(tk.END, json_str)
        text_widget.config(state=tk.DISABLED)

        # Bouton pour fermer la fenêtre
        ttk.Button(json_window, text="Fermer", command=json_window.destroy).pack(pady=10)


    def generate_command_json(self):
        command = {
            "publish_cell": int(self.publish_var.get()) if self.publish_var.get().isdigit() else 24,
            "fan_power": {}
        }
        for cell_row in range(1, self.grid_rows + 1):
            for cell_col in range(1, self.grid_cols + 1):
                cell_id = f"{cell_row}{cell_col}"
                command["fan_power"][cell_id] = self.fan_status[cell_id]['power']
        return json.dumps(command, indent=2)

    def log_status(self, message):
        if self.current_mode == "percentage":
            console = self.status_console
            console.config(state=tk.NORMAL)
            console.insert(tk.END, message + "\n")
            console.see(tk.END)
            console.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = GVMControlApp(root)
    root.mainloop()

