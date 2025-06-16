import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog
import json
import threading
import time
import random
import os
import serial
import queue
import csv

from functools import partial

class GVMControlApp:
    def __init__(self, root, grid_rows=3, grid_cols=3):
        self.root = root
        self.root.title("Contrôle GVM - Système de Ventilation Modulaire")
        
        self.loop_profile_var = tk.BooleanVar(value=False)

        self.profile_name = "Aucun profil chargé"
        self.is_modified = False
        self.grid_rows = grid_rows
        self.grid_cols = grid_cols
        self.pwm_values = []
        self.rpm_values = []
        self.airflow_values = []
        self.airflow_percentage = []
        self.rpm_data = {}
        self.fan_status = {}
        self.current_mode = "create"
        self.selected_fans = set()
        self.sequences = {}  # {name: {'powers': {...}, 'duration': int}}
        self.sequence_buttons = []
        self.rpm_receiver = RPMReceiver()
        self.rpm_receiver.start()

        self.initialize_fan_data()
        self.create_frames()
        self.show_home()
        self.charger_csv_ventilateur()
        self.obtenir_indice_depuis_pourcentage(50)

        self.update_thread = threading.Thread(target=self.update_rpm_data, daemon=True)
        self.update_thread.start()
        
        self.loop_profile_var = tk.BooleanVar(value=False)

    def charger_csv_ventilateur(self):
        # Récupérer le dossier où se trouve le script actuel
        dossier_script = os.path.dirname(os.path.abspath(__file__))
        # Construire le chemin complet vers le fichier CSV dans ce dossier
        filepath = os.path.join(dossier_script, "data_value_fan.csv")
        if not filepath:
            return

        self.pwm_values.clear()
        self.rpm_values.clear()
        self.airflow_values.clear()

        try:
            with open(filepath, newline='', encoding='latin-1') as csvfile:
                reader = csv.reader(csvfile, delimiter=';')
                next(reader)  # ignore l'en-tête
                for row in reader:
                    if len(row) != 3:
                        continue
                    try:
                        pwm = int(row[0].strip())
                        rpm = int(row[1].strip())
                        airflow = float(row[2].strip().replace(',', '.'))
                        self.pwm_values.append(pwm)
                        self.rpm_values.append(rpm)
                        self.airflow_values.append(airflow)
                    except ValueError:
                        continue
            messagebox.showinfo("Succès", f"Fichier chargé : {os.path.basename(filepath)}")
            self.generer_airflow_reduit()
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors du chargement du CSV : {e}")

    def generer_airflow_reduit(self):
        if not self.airflow_values or len(self.airflow_values) < 2:
            raise ValueError("La liste airflow_values doit contenir au moins deux valeurs.")

        airflow_debut = self.airflow_values[0]
        airflow_fin = self.airflow_values[-1]

        # 17 valeurs également espacées entre airflow_debut et airflow_fin
        step = (airflow_fin - airflow_debut) / 19  # 18 intervalles => 19 points entre les extrêmes
        valeurs_interpolees = [airflow_debut + i * step for i in range(1, 19)]  # on saute le début (0) et la première vraie valeur

        # On cherche pour chaque valeur interpolée la plus proche dans la vraie liste
        airflow_reduit = [0.0]  # première valeur fixée à 0
        airflow_reduit.append(self.airflow_values[0])  # deuxième valeur : premier élément réel

        for v in valeurs_interpolees:
            valeur_proche = min(self.airflow_values, key=lambda x: abs(x - v))
            airflow_reduit.append(valeur_proche)

        airflow_reduit.append(self.airflow_values[-1])  # dernière valeur réelle
        self.airflow_percentage = airflow_reduit

    def obtenir_indice_depuis_pourcentage(self, pourcentage):
        """
        Reçoit une valeur entre 0 et 100 avec des paliers de 5.
        1. Divise la valeur par 5 pour trouver l’indice dans self.airflow_percentage.
        2. Cherche la valeur correspondante dans self.airflow_values.
        3. Retourne l’indice de cette valeur dans self.airflow_values.
        Si la valeur est 0, retourne -1.
        """
        if pourcentage % 5 != 0 or not (0 <= pourcentage <= 100):
            raise ValueError("Le pourcentage doit être un multiple de 5 entre 0 et 100.")

        index_percentage = pourcentage // 5

        try:
            valeur_airflow = self.airflow_percentage[index_percentage]
            #print(valeur_airflow)
        except IndexError:
            raise IndexError("Index hors limite dans airflow_percentage.")

        if valeur_airflow == 0:
            return -1

        try:
            index_airflow = self.airflow_values.index(valeur_airflow)
            #print(index_airflow)
            return index_airflow
            
        except ValueError:
            raise ValueError("La valeur airflow n’a pas été trouvée dans airflow_values.")
    
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
        self.stop_serial_communication()

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

        self.power_var_create = tk.IntVar(value=0)
        self.power_entry_var_create = tk.StringVar(value="0")

        power_slider = ttk.Scale(
            buttons_frame,
            from_=0, to=100,
            variable=self.power_var_create,
            command=partial(self.on_slider_change, "create")
        )
        power_slider.pack(padx=5)

        entry = ttk.Entry(buttons_frame, textvariable=self.power_entry_var_create, width=5)
        entry.pack()

        self.power_entry_var_create.trace_add("write", partial(self.on_entry_change, "create"))

        ttk.Button(buttons_frame, text="Appliquer à sélection", command=lambda: self.apply_power_selected("create")).pack(pady=5, ipadx=10, ipady=5)
        ttk.Button(buttons_frame, text="Appliquer à tous", command=lambda: self.apply_power_all("create")).pack(pady=5, ipadx=10, ipady=5)
        ttk.Button(buttons_frame, text="Reset la grille", command=lambda: self.reset_grille("create")).pack(pady=5, ipadx=10, ipady=5)

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

        self.loop_checkbox = ttk.Checkbutton(sequence_frame, text="Boucler le profil", variable=self.loop_profile_var)
        self.loop_checkbox.pack(pady=5)


    def create_monitor_interface(self):
        # Frame principale pour la page "execute"
        main_frame = ttk.Frame(self.monitor_frame, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        container = ttk.Frame(main_frame)
        container.pack(fill=tk.BOTH, expand=True)

        self.profile_label_execute = ttk.Label(container, text=f"Profil: {self.profile_name}", font=('Helvetica', 10))
        self.profile_label_execute.pack(side=tk.TOP, pady=(0, 5))


        buttons_frame = ttk.Frame(container)
        buttons_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        ttk.Label(buttons_frame, text="Contrôles", font=('Helvetica', 12)).pack(pady=5)
        ttk.Label(buttons_frame, text="Puissance (%):").pack(pady=(10, 0))

        self.power_var_execute = tk.IntVar(value=0)
        self.power_entry_var_execute = tk.StringVar(value="0")

        power_slider = ttk.Scale(
            buttons_frame,
            from_=0, to=100,
            variable=self.power_var_execute,
            command=partial(self.on_slider_change, "execute")
        )
        power_slider.pack(padx=5)

        entry = ttk.Entry(buttons_frame, textvariable=self.power_entry_var_execute, width=5)
        entry.pack()

        self.power_entry_var_execute.trace_add("write", partial(self.on_entry_change, "execute"))

        ttk.Button(buttons_frame, text="Appliquer à sélection", command=lambda: self.apply_power_selected("execute")).pack(pady=5, ipadx=10, ipady=5)
        ttk.Button(buttons_frame, text="Appliquer à tous", command=lambda: self.apply_power_all("execute")).pack(pady=5, ipadx=10, ipady=5)
        ttk.Button(buttons_frame, text="Reset la grille", command=lambda: self.reset_grille("execute")).pack(pady=5, ipadx=10, ipady=5)
        ttk.Button(buttons_frame, text="Charger profil", command=self.charger_profil).pack(pady=5, ipadx=10, ipady=5)
        self.send_button = ttk.Button(buttons_frame, text="Envoyer commande", command=self.start_serial_communication, state='normal')
        self.send_button.pack(pady=5, ipadx=10, ipady=5)
        self.stop_button = ttk.Button(buttons_frame, text="Arrêter l'envoi", command=self.stop_serial_communication, state='disabled')
        self.stop_button.pack(pady=5, ipadx=10, ipady=5)

        grid_frame = ttk.Frame(container)
        grid_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.create_fan_grid(grid_frame, "execute")

        # control_frame = ttk.Frame(main_frame)
        # control_frame.pack(fill=tk.X, pady=10)

        # ttk.Label(control_frame, text="Exécution de profil", font=('Helvetica', 12)).pack()

        # legend_frame = ttk.Frame(control_frame)
        # legend_frame.pack(pady=5)

        # ttk.Label(legend_frame, text="Légende:").grid(row=0, column=0, padx=5)
        # tk.Label(legend_frame, text="   Normal   ", bg="green", fg="white").grid(row=0, column=1, padx=5)
        # tk.Label(legend_frame, text="   Erreur   ", bg="red", fg="white").grid(row=0, column=2, padx=5)
        # tk.Label(legend_frame, text="   Inactif   ", bg="lightgrey").grid(row=0, column=3, padx=5)

        # ---------------------------
        # 🔹 Bouton retour (optionnel)
        # ---------------------------
        if not hasattr(self, 'back_button'):
            self.back_button = ttk.Button(self.root, text="Retour à l'accueil", command=self.show_home)

    def on_slider_change(self, mode, value):
        val = int(float(value))
        entry_var = getattr(self, f"power_entry_var_{mode}")
        entry_var.set(str(val))

    def on_entry_change(self, mode, *args):
        try:
            entry_var = getattr(self, f"power_entry_var_{mode}")
            power_var = getattr(self, f"power_var_{mode}")
            val = int(entry_var.get())
            val = max(0, min(100, val))
            power_var.set(val)
        except ValueError:
            pass
        
    def update_profile_label(self):
        if hasattr(self, 'profile_label'):
            self.profile_label.config(text=f"Profil: {self.profile_name}")
        if hasattr(self, 'profile_label_execute'):
            self.profile_label_execute.config(text=f"Profil: {self.profile_name}")
        
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
                self.rpm_data[cell_id] = [0] * 9
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
                        btn = tk.Button(cell_frame, text="0%")

                        if mode == "create":
                            btn.config(text="0%",
                                       command=lambda cr=cell_row, cc=cell_col, fr=fan_row + 1, fc=fan_col + 1:
                                       self.select_fan(cr, cc, fr, fc,"create"))
                        else:
                            btn.config(
                                command=lambda cr=cell_row, cc=cell_col, fr=fan_row + 1, fc=fan_col + 1:
                                self.select_fan(cr, cc, fr, fc, "execute")
                            )
                            Tooltip(btn, lambda c=cell_id, idx=fan_idx: self.get_rpm_text(c, idx))

                        btn.grid(row=fan_row, column=fan_col, padx=1, pady=1, sticky="nsew")

                        key = f"create_btn_{fan_idx}" if mode == "create" else f"execute_btn_{fan_idx}"
                        self.fan_status[cell_id][key] = btn

    def get_rpm_text(self, cell_id, fan_idx):
        try:
            rpm_values = self.rpm_data.get(cell_id, [])
            if 0 <= fan_idx < len(rpm_values):
                return f"RPM: {rpm_values[fan_idx]}"
            else:
                return "RPM non disponible"
        except Exception as e:
            return f"Erreur : {str(e)}"
    
    def select_fan(self, cell_row, cell_col, fan_row, fan_col,mode):
        cell_id = f"{cell_row}{cell_col}"
        fan_idx = (fan_row - 1) * 3 + (fan_col - 1)
        fan_key = (cell_id, fan_idx)
        btn = self.fan_status[cell_id][f"create_btn_{fan_idx}" if mode == "create" else f"execute_btn_{fan_idx}"]

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

    def apply_power_selected(self, mode):
        if not self.selected_fans:
            return
        power = self.power_var_create.get() if mode =="create" else self.power_var_execute.get()
        for cell_id, fan_idx in self.selected_fans:
            self.fan_status[cell_id]['power'][fan_idx] = power
            btn = self.fan_status[cell_id][f"create_btn_{fan_idx}" if mode == "create" else f"execute_btn_{fan_idx}"]
            btn.config(text=f"{power}%", bg="green" if power > 0 else "lightgrey",
                       fg="white" if power > 0 else "black")
        self.selected_fans.clear()
        self.mark_as_modified()
        self.stop_serial_communication()
        
    def apply_power_all(self, mode):
        power = self.power_var_create.get() if mode =="create" else self.power_var_execute.get()
        self.selected_fans.clear()
        for cell_id in self.fan_status:
            for fan_idx in range(9):
                self.fan_status[cell_id]['power'][fan_idx] = power
                btn = self.fan_status[cell_id][f"create_btn_{fan_idx}" if mode == "create" else f"execute_btn_{fan_idx}"]
                btn.config(text=f"{power}%", bg="green" if power > 0 else "lightgrey",
                           fg="white" if power > 0 else "black")
        self.mark_as_modified()
        self.stop_serial_communication()

    def reset_grille(self, mode):
        self.mark_as_modified()
        self.stop_serial_communication()
        self.selected_fans.clear()  # Désélectionne tous les ventilateurs

        for cell_id, data in self.fan_status.items():
            data['power'] = [0] * 9  # Remet les puissances à 0

            for i in range(9):
                btn_key = f"create_btn_{i}" if mode == "create" else f"execute_btn_{i}"
                if btn_key in data:
                    btn = data[btn_key]
                    btn.config(text="0%", bg="lightgrey", fg="black")  # Réinitialise le texte et la couleur

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
        self.stop_serial_communication()

    def reset_grid(self):
        for cell_id in self.fan_status:
            for fan_idx in range(9):
                self.fan_status[cell_id]['power'][fan_idx] = 0
                btn = self.fan_status[cell_id][f"create_btn_{fan_idx}" if self.current_mode == "create" else f"execute_btn_{fan_idx}"]
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
                self.stop_serial_communication()
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
            self.stop_serial_communication()

    def load_sequence(self, name):
        if name in self.sequences:
            snapshot = self.sequences[name]['powers']
            for cell_id in self.fan_status:
                for i in range(9):
                    self.fan_status[cell_id]['power'][i] = snapshot[cell_id][i]
                    btn = self.fan_status[cell_id][f"create_btn_{i}"]
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
                data = {
                    "type": "dynamique",
                    "sequences": self.sequences,
                    "loop": self.loop_profile_var.get()  # 🔁 Ajout ici
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
            
            self.loop_profile_var.set(data.get("loop", False))  # 🔁 Charge l'état si présent

            profil_type = data.get("type")

            self.reset_grille(self.current_mode)

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
                            btn = self.fan_status[cell_id].get(f"create_btn_{i}" if self.current_mode == "create" else f"execute_btn_{i}")
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
        
        # Recréer les bouton
        for name in self.sequences:
            self.add_sequence_button(name)

    def start_serial_communication(self):
        self.serial_log_window = tk.Toplevel(self.root)
        self.serial_log_window.title("Envoi des chaînes JSON")
        self.serial_log_text = tk.Text(self.serial_log_window, height=20, width=80, state='disabled')
        self.serial_log_text.pack(padx=10, pady=10)

        self.serial_active = True
        self.serial_queue = queue.Queue()

        # Lance le thread d'envoi série
        self.serial_thread = threading.Thread(target=self.serial_send_loop, daemon=True)
        self.serial_thread.start()

        # Rafraîchit l'affichage des logs
        self.update_serial_log_display()

        self.stop_button.config(state='normal')
        self.send_button.config(state='disabled')

    def serial_send_loop(self):
        try:
            ser = serial.Serial('/dev/serial0', 115200, timeout=1)
        except Exception as e:
            self.serial_queue.put(f"Erreur ouverture port série: {e}")
            return

        if self.sequences:
            # 🔁 Envoi continu des séquences
            try:
                self.serial_queue.put("🚀 Démarrage de l'envoi cyclique des séquences.")
                first_cycle = True
                while self.serial_active and (first_cycle or self.loop_profile_var.get()):
                    first_cycle = False

                    for seq_name in self.sequences:
                        seq = self.sequences[seq_name]
                        powers = seq['powers']
                        duration = seq['duration']
                        self.serial_queue.put(f"⏱ Envoi de la séquence '{seq_name}' pendant {duration} secondes")

                        cell_ids = sorted(powers.keys())
                        seq_start = time.time()
                        seq_end = seq_start + duration

                        while time.time() < seq_end and self.serial_active:
                            loop_start = time.time()
                            for publish_cell in cell_ids:
                                json_message = {cell_id: powers[cell_id] for cell_id in cell_ids}
                                json_message["Publish"] = int(publish_cell)
                                try:
                                    msg = json.dumps(json_message)
                                    ser.write((msg + '\n').encode('utf-8'))
                                    self.serial_queue.put(f"Envoyé → {msg}")
                                except Exception as e:
                                    self.serial_queue.put(f"Erreur d'envoi: {e}")
                            time.sleep(max(0, 1.0 - (time.time() - loop_start)))
                self.serial_queue.put("🛑 Envoi interrompu par l'utilisateur.")
            except Exception as e:
                self.serial_queue.put(f"Erreur lors de l'exécution des séquences: {e}")
        else:
            # 🔁 Envoi continu du profil statique
            try:
                powers = {cell_id: self.fan_status[cell_id]['power'][:] for cell_id in self.fan_status}
                cell_ids = sorted(powers.keys())

                self.serial_queue.put("📤 Envoi du profil statique : 1 JSON par cellule réparti sur 1 seconde.")

                while self.serial_active:
                    loop_start = time.time()

                    for publish_cell in cell_ids:
                        json_message = {cell_id: powers[cell_id] for cell_id in cell_ids}
                        json_message["Publish"] = int(publish_cell)

                        try:
                            msg = json.dumps(json_message)
                            ser.write((msg + '\n').encode('utf-8'))
                            self.serial_queue.put(f"Envoyé (statique) → {msg}")
                        except Exception as e:
                            self.serial_queue.put(f"Erreur d'envoi (statique): {e}")
                    time.sleep(max(0, 1.0 - (time.time() - loop_start)))

                self.serial_queue.put("🛑 Envoi statique arrêté par l'utilisateur.")
            except Exception as e:
                self.serial_queue.put(f"Erreur lors de l'envoi du profil statique: {e}")

    def stop_serial_communication(self):
        self.serial_active = False
        self.stop_button.config(state='disabled')
        self.send_button.config(state='normal')

        if hasattr(self, 'serial_log_window') and self.serial_log_window.winfo_exists():
            self.serial_log_window.destroy()
        
    def update_serial_log_display(self):
        try:
            while not self.serial_queue.empty():
                line = self.serial_queue.get_nowait()
                self.serial_log_text.configure(state='normal')
                self.serial_log_text.insert(tk.END, line + "\n")
                self.serial_log_text.configure(state='disabled')
                self.serial_log_text.see(tk.END)
        except queue.Empty:
            pass
        if self.serial_active:
            self.root.after(100, self.update_serial_log_display)

    def update_rpm_data(self):
        while True:
            rpm_values = self.rpm_receiver.get_all_rpms()
            # Utiliser `after` pour mettre à jour l'UI dans le thread principal
            self.root.after(0, self.update_rpm_display, rpm_values)
            time.sleep(0.1)

    def update_rpm_display(self, rpm_values):
        for cell_id, rpms in rpm_values.items():
            self.rpm_data[cell_id] = rpms  # met à jour les données utilisées par les tooltips

class RPMReceiver:
    def __init__(self, port='/dev/serial0', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.running = False
        self.data = {}  # {cell_id: [rpm1, rpm2, ..., rpm9]}
        self.lock = threading.Lock()

    def start(self):
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1)
            self.running = True
            self.thread = threading.Thread(target=self.listen_loop, daemon=True)
            self.thread.start()
            print(f"[INFO] Lecture série démarrée sur {self.port} à {self.baudrate} bauds.")
        except Exception as e:
            print(f"[ERREUR] Impossible d’ouvrir le port série : {e}")

    def stop(self):
        self.running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            print("[INFO] Connexion série fermée.")

    def listen_loop(self):
        while self.running:
            try:
                line = self.serial_conn.readline().decode('utf-8').strip()
                if line:
                    self.handle_message(line)
            except Exception as e:
                print(f"[ERREUR] Problème de lecture : {e}")
            time.sleep(0.05)

    def handle_message(self, message):
        try:
            data = json.loads(message)
            cell_id = str(data.get("cell"))  # ⚠️ conversion en string
            rpm_values = data.get("RPM")

            if isinstance(rpm_values, list) and len(rpm_values) == 9:
                with self.lock:
                    self.data[cell_id] = rpm_values
        except json.JSONDecodeError:
            print(f"[AVERTISSEMENT] JSON invalide : {message}")

    def get_rpm_for_cell(self, cell_id):
        with self.lock:
            return self.data.get(cell_id, None)

    def get_all_rpms(self):
        with self.lock:
            return dict(self.data)  # copie du dict
        
    def get_rpm_text(self, cell_id, fan_idx):
        rpm_values = self.rpm_data.get(cell_id, [])
        print(f"Tooltip for {cell_id}[{fan_idx}] → {rpm_values}")
        if 0 <= fan_idx < len(rpm_values):
            return f"RPM: {rpm_values[fan_idx]}"
        else:
            return "RPM non disponible"


# # Exemple d'utilisation
# if __name__ == "__main__":
#     receiver = RPMReceiver()
#     receiver.start()

#     try:
#         while True:
#             time.sleep(5)
#             print("[INFO] Valeurs RPM stockées :")
#             print(receiver.get_all_rpms())
#     except KeyboardInterrupt:
#         print("\n[INFO] Arrêt demandé par l'utilisateur.")
#     finally:
#         receiver.stop()

class Tooltip:
    def __init__(self, widget, textfunc):
        self.widget = widget
        self.textfunc = textfunc
        self.tipwindow = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tipwindow or not self.textfunc:
            return
        text = self.textfunc()
        if not text:
            return

        x = y = 0
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")

        label = tk.Label(tw, text=text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        tw = self.tipwindow
        if tw:
            tw.destroy()
        self.tipwindow = None

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()  # Cache temporairement la fenêtre principale

    rows = simpledialog.askinteger("Configuration initiale", "Nombre de lignes de cellules :", minvalue=1, initialvalue=3)
    cols = simpledialog.askinteger("Configuration initiale", "Nombre de colonnes de cellules :", minvalue=1, initialvalue=3)

    if rows is None or cols is None:
        messagebox.showinfo("Annulé", "Lancement annulé.")
        root.destroy()
    else:
        root.deiconify()  # Réaffiche la fenêtre principale
        app = GVMControlApp(root, grid_rows=rows, grid_cols=cols)
        root.mainloop()

