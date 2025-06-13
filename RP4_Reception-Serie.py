import serial
import threading
import tkinter as tk
from tkinter import scrolledtext

# Configuration du port série
SERIAL_PORT = "COM3"  # Remplace par ton port (ex: "COM3" sur Windows ou "/dev/ttyUSB0" sur Linux)
BAUD_RATE = 9600      # Doit correspondre à la vitesse de l'émetteur série

def read_serial():
    """Lit les données du port série et les affiche dans la fenêtre texte."""
    while True:
        if ser.in_waiting:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            text_box.insert(tk.END, line + '\n')
            text_box.see(tk.END)

# Initialisation du port série
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
except serial.SerialException:
    print(f"Erreur : impossible d’ouvrir le port {SERIAL_PORT}")
    exit()

# Création de l’interface Tkinter
root = tk.Tk()
root.title("Lecture Série")

text_box = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=60, height=20)
text_box.pack(padx=10, pady=10)

# Démarrage du thread de lecture série
thread = threading.Thread(target=read_serial, daemon=True)
thread.start()

# Boucle principale de la GUI
root.mainloop()

# Fermeture du port série quand la fenêtre est fermée
ser.close()
