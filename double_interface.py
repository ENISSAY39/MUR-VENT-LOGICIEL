import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog
import json
import threading
import time
import random
import os


class GVMControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Contrôle GVM - Système de Ventilation Modulaire")

        self.profile_name = "Nouveau Profil"
        self.is_modified = False
        self.grid_rows = 3
        self.grid_cols = 3
        self.fan_status = {}
        self.current_mode = "create"
        self.selected_fans = set()
        self.sequences = {}  # {name: {'powers': {...}, 'duration': int}}
        self.sequence_buttons = []

        self.initialize_fan_data()
        self.create_frames()
        self.show_home()

        self.update_thread = threading.Thread(target=self.update_rpm_data, daemon=True)
        self.update_thread.start()

    def create_frames(self):
        self.home_frame = ttk.Frame(self.root)

        ttk.Label(self.home_frame, text="Système de Contrôle GVM", font=('Helvetica', 16)).pack(pady=20)
        ttk.Button(self.home_frame, text="Création de profil",
                   command=lambda: self.show_grid_mode("create")).pack(pady=10, ipadx=20, ipady=10)
        ttk.Button(self.home_frame, text="Execution de profil",
                   command=lambda: self.show_grid_mode("execute")).pack(pady=10, ipadx=20, ipady=10)

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

        if mode == "create":
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
        ttk.Label(buttons_frame, text="Puissance (%):").pack(pady=(10, 0))

        self.power_var = tk.IntVar(value=0)

        def on_slider_change(v):
            val = int(float(v))
            self.power_entry_var.set(str(val))  # Met à jour le champ Entry

        def on_entry_change(*args):
            try:
                val = int(self.power_entry_var.get())
                val = max(0, min(100, val))  # Clamp entre 0 et 100
                self.power_var.set(val)
            except ValueError:
                pass  # Ignore l'entrée invalide

        power_slider = ttk.Scale(buttons_frame, from_=0, to=100, variable=self.power_var, command=on_slider_change)
        power_slider.pack(padx=5)

        self.power_entry_var = tk.StringVar(value="0")
        self.power_entry_var.trace_add("write", on_entry_change)

        power_entry = ttk.Entry(buttons_frame, textvariable=self.power_entry_var, width=5, justify='center')
        power_entry.pack(pady=5)

        ttk.Button(buttons_frame, text="Appliquer à sélection", command=self.apply_power_selected).pack(pady=5, ipadx=10, ipady=5)
        ttk.Button(buttons_frame, text="Appliquer à tous", command=self.apply_power_all).pack(pady=5, ipadx=10, ipady=5)
        ttk.Button(buttons_frame, text="Reset la grille", command=self.reset_grille).pack(pady=5, ipadx=10, ipady=5)

        # RIGHT SIDE: Sequences
        sequence_frame = ttk.Frame(container)
        sequence_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.sequence_list_frame = ttk.Frame(sequence_frame)
        self.sequence_list_frame.pack(fill=tk.Y, pady=(0, 10))

        ttk.Label(self.sequence_list_frame, text="Liste des séquences", font=('Helvetica', 10)).pack(pady=5)

        self.sequence_buttons_frame = ttk.Frame(self.sequence_list_frame)
        self.sequence_buttons_frame.pack()

        ttk.Button(sequence_frame, text="Créer séquence", command=self.create_sequence).pack(pady=10, ipadx=10, ipady=5)
        
        self.profile_label = ttk.Label(container, text=f"Profil: {self.profile_name}", font=('Helvetica', 10))
        self.profile_label.pack(side=tk.TOP, pady=(0, 5))
        
        grid_frame = ttk.Frame(container)
        grid_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.create_fan_grid(grid_frame, "create")

        if not hasattr(self, 'back_button'):
            self.back_button = ttk.Button(self.root, text="Retour à l'accueil", command=self.show_home)

        ttk.Button(sequence_frame, text="Sauvegarder profil", command=self.sauvegarder_profil).pack(pady=2, ipadx=10, ipady=5)
        ttk.Button(sequence_frame, text="Charger profil", command=self.charger_profil).pack(pady=2, ipadx=10, ipady=5)

    def update_profile_label(self):
        self.profile_label.config(text=f"Profil: {self.profile_name}")

    def create_monitor_interface(self):
        main_frame = ttk.Frame(self.monitor_frame, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        grid_frame = ttk.Frame(main_frame)
        grid_frame.pack(fill=tk.BOTH, expand=True)

        self.create_fan_grid(grid_frame, "execute")

        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=10)

        ttk.Label(control_frame, text="Execution de profil", font=('Helvetica', 12)).pack()

        legend_frame = ttk.Frame(control_frame)
        legend_frame.pack(pady=5)
        ttk.Label(legend_frame, text="Légende:").grid(row=0, column=0, padx=5)
        tk.Label(legend_frame, text="   Normal   ", bg="green", fg="white").grid(row=0, column=1, padx=5)
        tk.Label(legend_frame, text="   Erreur   ", bg="red", fg="white").grid(row=0, column=2, padx=5)
        tk.Label(legend_frame, text="   Inactif   ", bg="lightgrey").grid(row=0, column=3, padx=5)

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
                cell_frame.configure(width=150, height=150)  # ajuster la taille au besoin
                cell_frame.grid_propagate(False)

                for k in range(3):
                    cell_frame.columnconfigure(k, weight=1)
                    cell_frame.rowconfigure(k, weight=1)

                for fan_row in range(3):
                    for fan_col in range(3):
                        fan_idx = fan_row * 3 + fan_col
                        btn = tk.Button(cell_frame, text="0%" if mode == "create" else "0 RPM")

                        if mode == "create":
                            btn.config(text="0%",
                                       command=lambda cr=cell_row, cc=cell_col, fr=fan_row + 1, fc=fan_col + 1:
                                       self.select_fan(cr, cc, fr, fc))
                        else:
                            btn.config(text="0 RPM")

                        btn.grid(row=fan_row, column=fan_col, padx=1, pady=1, sticky="nsew")

                        key = f"btn_{fan_idx}" if mode == "create" else f"rpm_btn_{fan_idx}"
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
                btn.config(bg="lightgrey", fg="black")
        else:
            self.selected_fans.add(fan_key)
            btn.config(bg="blue", fg="white")

    def apply_power_selected(self):
        if not self.selected_fans:
            return
        power = self.power_var.get()
        for cell_id, fan_idx in self.selected_fans:
            self.fan_status[cell_id]['power'][fan_idx] = power
            btn = self.fan_status[cell_id][f"btn_{fan_idx}"]
            btn.config(text=f"{power}%", bg="green" if power > 0 else "lightgrey",
                       fg="white" if power > 0 else "black")
        self.selected_fans.clear()
        self.mark_as_modified()

    def apply_power_all(self):
        power = self.power_var.get()
        self.selected_fans.clear()
        for cell_id in self.fan_status:
            for fan_idx in range(9):
                self.fan_status[cell_id]['power'][fan_idx] = power
                btn = self.fan_status[cell_id][f"btn_{fan_idx}"]
                btn.config(text=f"{power}%", bg="green" if power > 0 else "lightgrey",
                           fg="white" if power > 0 else "black")
        self.mark_as_modified()

    def reset_grille(self):
        self.mark_as_modified()
        self.selected_fans.clear()  # Désélectionne tous les ventilateurs

        for cell_id, data in self.fan_status.items():
            data['power'] = [0] * 9  # Remet les puissances à 0

            for i in range(9):
                btn_key = f"btn_{i}"
                if btn_key in data:
                    btn = data[btn_key]
                    btn.config(text="0%", bg="lightgrey", fg="black")  # Réinitialise le texte et la couleur

    def update_rpm_data(self):
        while True:
            time.sleep(1)
            for cell_id in self.fan_status:
                for fan_idx in range(9):
                    power = self.fan_status[cell_id]['power'][fan_idx]
                    rpm = power * 10 + random.randint(-300, 300)
                    rpm = max(rpm, 0)
                    self.fan_status[cell_id]['rpm'][fan_idx] = rpm

                    if self.current_mode == "execute":
                        btn = self.fan_status[cell_id].get(f"rpm_btn_{fan_idx}")
                        if btn:
                            expected = power * 10
                            functional = abs(rpm - expected) <= 500
                            if power == 0:
                                btn.config(text="0 RPM", bg="lightgrey", fg="black")
                            else:
                                btn.config(text=f"{rpm} RPM", bg="green" if functional else "red", fg="white")

    def create_sequence(self):
        # Demande la durée (en secondes) via une fenêtre modale
        duration = simpledialog.askinteger("Durée de la séquence",
                                           "Entrez la durée en secondes pour cette séquence:",
                                           minvalue=1, initialvalue=5)
        if duration is None:
            return  # Annulé

        # Nom par défaut
        base_name = f"Seq{len(self.sequences) + 1}"
        name = base_name
        i = 1
        while name in self.sequences:
            i += 1
            name = f"{base_name}_{i}"

        snapshot = {cell_id: self.fan_status[cell_id]['power'][:] for cell_id in self.fan_status}
        self.sequences[name] = {'powers': snapshot, 'duration': duration}
        self.add_sequence_button(name)
        self.reset_grid()
        self.mark_as_modified()

    def reset_grid(self):
        for cell_id in self.fan_status:
            for fan_idx in range(9):
                self.fan_status[cell_id]['power'][fan_idx] = 0
                btn = self.fan_status[cell_id][f"btn_{fan_idx}"]
                btn.config(text="0%", bg="lightgrey", fg="black")

    def add_sequence_button(self, name):
        frame = ttk.Frame(self.sequence_buttons_frame)
        frame.pack(pady=2, fill=tk.X)

        btn = ttk.Button(frame, text=name, width=15)
        btn.pack(side=tk.LEFT)
        btn.bind("<Double-Button-1>", lambda e, n=name: self.rename_sequence(n))

        # Ajout du label "Temps"
        time_label = ttk.Label(frame, text="Temps")
        time_label.pack(side=tk.LEFT, padx=(10, 2)) 

        dur_var = tk.StringVar(value=str(self.sequences[name]['duration']))
        dur_entry = ttk.Entry(frame, textvariable=dur_var, width=5)
        dur_entry.pack(side=tk.LEFT, padx=5)

        # Sauvegarde la durée à chaque changement
        def update_duration(*args):
            val = dur_var.get()
            if val.isdigit() and int(val) > 0:
                self.sequences[name]['duration'] = int(val)
            else:
                dur_var.set(str(self.sequences[name]['duration']))
        dur_var.trace_add("write", update_duration)

        # Bouton "Charger"
        load_btn = ttk.Button(frame, text="Charger", command=lambda n=name: self.load_sequence(n))
        load_btn.pack(side=tk.LEFT, padx=5)

        # 🔹 Bouton "Enregistrer modifs"
        save_btn = ttk.Button(frame, text="Enregistrer modifs", command=lambda n=name: self.save_current_grid_to_sequence(n))
        save_btn.pack(side=tk.LEFT, padx=5)

        # Bouton "Supprimer"
        del_btn = ttk.Button(frame, text="Supprimer", command=lambda n=name, f=frame: self.delete_sequence(n, f))
        del_btn.pack(side=tk.LEFT)

        self.sequence_buttons.append((frame, name))

    def rename_sequence(self, old_name):
        new_name = simpledialog.askstring("Renommer la séquence", "Entrez le nouveau nom :", initialvalue=old_name)
        if new_name and new_name != old_name:
            if new_name in self.sequences:
                messagebox.showerror("Erreur", "Ce nom existe déjà.")
                return

            # Renommer dans le dictionnaire
            self.sequences[new_name] = self.sequences.pop(old_name)

            # Met à jour l'interface
            for frame, name in self.sequence_buttons:
                if name == old_name:
                    for child in frame.winfo_children():
                        # Met à jour le nom affiché sur le bouton
                        if isinstance(child, ttk.Button) and child.cget("text") == old_name:
                            child.config(text=new_name)
                            child.bind("<Double-Button-1>", lambda e, n=new_name: self.rename_sequence(n))

                        # Recharge les boutons "Charger" et "Supprimer"
                        if isinstance(child, ttk.Button) and child.cget("text") == "Charger":
                            child.config(command=lambda n=new_name: self.load_sequence(n))
                        if isinstance(child, ttk.Button) and child.cget("text") == "Supprimer":
                            child.config(command=lambda n=new_name, f=frame: self.delete_sequence(n, f))

                    # Met à jour le nom dans la liste interne
                    idx = self.sequence_buttons.index((frame, name))
                    self.sequence_buttons[idx] = (frame, new_name)
                    break

    def delete_sequence(self, name, frame):
        if messagebox.askyesno("Confirmer la suppression", f"Supprimer la séquence '{name}' ?"):
            if name in self.sequences:
                del self.sequences[name]
                self.mark_as_modified()
            frame.destroy()
            self.sequence_buttons = [t for t in self.sequence_buttons if t[1] != name]

    def save_current_grid_to_sequence(self, name):
        if name in self.sequences:
            new_snapshot = {
                cell_id: self.fan_status[cell_id]['power'][:] for cell_id in self.fan_status
            }
            self.sequences[name]['powers'] = new_snapshot
            messagebox.showinfo("Modifications enregistrées", f"La séquence '{name}' a été mise à jour.")
            self.mark_as_modified()

    def load_sequence(self, name):
        if name in self.sequences:
            snapshot = self.sequences[name]['powers']
            for cell_id in self.fan_status:
                for i in range(9):
                    self.fan_status[cell_id]['power'][i] = snapshot[cell_id][i]
                    btn = self.fan_status[cell_id][f"btn_{i}"]
                    power = snapshot[cell_id][i]
                    btn.config(text=f"{power}%", bg="green" if power > 0 else "lightgrey",
                               fg="white" if power > 0 else "black")
            self.selected_fans.clear()

    def sauvegarder_profil(self):
        profil_nom = simpledialog.askstring("Nom du profil", "Entrez un nom pour le profil :")
        if not profil_nom:
            return

        dossier = filedialog.askdirectory(title="Choisissez un dossier de sauvegarde")
        if not dossier:
            return

        chemin_fichier = os.path.join(dossier, f"{profil_nom}.json")

        try:
            if self.sequences:
                # Profil Dynamique
                data = {
                    "type": "dynamique",
                    "sequences": self.sequences
                }
            else:
                # Profil Statique
                grid_snapshot = {
                    cell_id: self.fan_status[cell_id]['power'][:] for cell_id in self.fan_status
                }
                data = {
                    "type": "statique",
                    "grid": grid_snapshot
                }

            with open(chemin_fichier, "w") as f:
                json.dump(data, f, indent=2)

            messagebox.showinfo("Succès", f"Profil enregistré : {chemin_fichier}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Échec de l'enregistrement : {e}")

    def charger_profil(self):
        filepath = tk.filedialog.askopenfilename(filetypes=[("Fichiers JSON", "*.json")])
        if not filepath:
            return

        try:
            with open(filepath, "r") as f:
                data = json.load(f)

            profil_type = data.get("type")

            if profil_type == "dynamique":
                self.sequences = data.get("sequences", {})
                self.actualiser_sequence_buttons()
                messagebox.showinfo("Chargé", "Profil dynamique chargé avec succès.")
                self.profile_name = os.path.splitext(os.path.basename(filepath))[0]
                self.is_modified = False
                self.update_profile_label()
            elif profil_type == "statique":
                self.sequences.clear()
                self.actualiser_sequence_buttons()
                grid_data = data.get("grid", {})
                for cell_id in self.fan_status:
                    if cell_id in grid_data:
                        for i in range(9):
                            power = grid_data[cell_id][i]
                            self.fan_status[cell_id]['power'][i] = power
                            btn = self.fan_status[cell_id].get(f"btn_{i}")
                            if btn:
                                btn.config(text=f"{power}%", bg="green" if power > 0 else "lightgrey",
                                        fg="white" if power > 0 else "black")
                self.selected_fans.clear()
                messagebox.showinfo("Chargé", "Profil statique chargé avec succès.")
                self.profile_name = os.path.splitext(os.path.basename(filepath))[0]
                self.is_modified = False
                self.update_profile_label()
            else:
                raise ValueError("Type de profil inconnu.")
        except Exception as e:
            messagebox.showerror("Erreur", f"Échec du chargement du profil : {e}")

    def mark_as_modified(self):
        if not self.is_modified:
            self.is_modified = True
            self.profile_name = "Nouveau Profil"
            self.update_profile_label()

    def actualiser_sequence_buttons(self):
        # Nettoyer l'interface
        for widget in self.sequence_buttons_frame.winfo_children():
            widget.destroy()
        self.sequence_buttons.clear()
        
        # Recréer les boutons
        for name in self.sequences:
            self.add_sequence_button(name)


if __name__ == "__main__":
    root = tk.Tk()
    app = GVMControlApp(root)
    root.mainloop()