import time
import random
import threading
import csv
from datetime import datetime
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from backend.USB_ports import get_com_ports
from backend.ph_metr import pHMetr
import matplotlib.pyplot as plt
from backend.pid import NonLinearPID
from backend.zasilacze_kuminkacja import KoradKD3005P

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class PhAutomationApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        # backend_functions
        self.zas_1 = None
        self.zas_2 = None
        self.ph_metr = None

        # Instancje PID tworzone raz na całą sesję aplikacji
        self.pid_salt = NonLinearPID()
        self.pid_base = NonLinearPID()

        self.gcp = get_com_ports()

        self.title("System Automatyzacji Dozowania Soli i Zasady")

        # --- TRYB PEŁNOEKRANOWY I SKALOWANIE DO ROZDZIELCZOŚCI ---
        self.is_fullscreen = True
        self.attributes("-fullscreen", True)

        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.geometry(f"{screen_width}x{screen_height}")

        self.bind("<Escape>", self.toggle_fullscreen)

        # Stan systemu
        self.is_running = False
        self.manual_mode = False

        # Odczyty i parametry
        self.current_ph = 7.00
        self.current_temp = 22.5
        self.time_counter = 0

        # Aktualne napięcia zasilaczy w trybie AUTO
        self.auto_salt_v = 0.0
        self.auto_base_v = 0.0

        self.time_data = []
        self.ph_data = []

        # Lista do przechowywania wszystkich rekordów raportu
        self.report_data = []

        self._create_widgets()
        self.log_message("Aplikacja została pomyślnie uruchomiona.", "INFO")

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes("-fullscreen", self.is_fullscreen)

    def _create_widgets(self):
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=15, pady=10)

        title_label = ctk.CTkLabel(
            header,
            text="Automatyzacja Dozowania - Kontrola pH (Wciśnij ESC aby opuścić pełny ekran)",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(side="left", padx=15, pady=10)

        self.status_label = ctk.CTkLabel(
            header,
            text="STATUS: ZATRZYMANY",
            text_color="#ef4444",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.status_label.pack(side="right", padx=15)

        main_container = ctk.CTkFrame(self)
        main_container.pack(fill="both", expand=True, padx=15, pady=5)

        left_panel = ctk.CTkFrame(main_container, width=340)
        left_panel.pack(side="left", fill="y", padx=10, pady=10)
        left_panel.pack_propagate(False)

        ports_header = ctk.CTkFrame(left_panel, fg_color="transparent")
        ports_header.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(ports_header, text="PORTY USB URZĄDZEŃ", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")

        btn_refresh = ctk.CTkButton(
            ports_header,
            text="Odśwież", width=70, height=24, font=ctk.CTkFont(size=11), command=self.refresh_ports)
        btn_refresh.pack(side="right")

        self.combo_salt = self._add_port_select(left_panel, "Pompa Soli (Zasilacz 1):", "COM3")
        self.combo_base = self._add_port_select(left_panel, "Pompa Zasady (Zasilacz 2):", "COM4")
        self.combo_ph = self._add_port_select(left_panel, "Miernik pH:", "COM5")

        ctk.CTkLabel(left_panel, text="NASTAWY PROCESU", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(left_panel, text="Zadana wartość pH:").pack(anchor="w", padx=10)
        self.entry_target_ph = ctk.CTkEntry(left_panel)
        self.entry_target_ph.insert(0, "7.0")
        self.entry_target_ph.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkLabel(left_panel, text="Maks. odchylenie NAD (+pH):").pack(anchor="w", padx=10)
        self.entry_max_above = ctk.CTkEntry(left_panel)
        self.entry_max_above.insert(0, "0.5")
        self.entry_max_above.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkLabel(left_panel, text="Maks. odchylenie POD (-pH):").pack(anchor="w", padx=10)
        self.entry_max_below = ctk.CTkEntry(left_panel)
        self.entry_max_below.insert(0, "0.5")
        self.entry_max_below.pack(fill="x", padx=10, pady=(0, 5))

        # --- SEKCJA: TRYB PRACY ZASILACZY ---
        ctk.CTkLabel(left_panel, text="TRYB ZASILACZY (AUTO)", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=10, pady=(5, 5))

        ctk.CTkLabel(left_panel, text="Zasilacz pracujący ze stałym napięciem:").pack(anchor="w", padx=10)
        self.combo_constant_psu = ctk.CTkOptionMenu(
            left_panel,
            values=["Pompa Soli (Zasilacz 1)", "Pompa Zasady (Zasilacz 2)", "Brak (Oba regulowane)"]
        )
        self.combo_constant_psu.set("Pompa Soli (Zasilacz 1)")
        self.combo_constant_psu.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkLabel(left_panel, text="Napięcie stałe zasilacza [V]:").pack(anchor="w", padx=10)
        self.entry_const_v = ctk.CTkEntry(left_panel)
        self.entry_const_v.insert(0, "5.0")
        self.entry_const_v.pack(fill="x", padx=10, pady=(0, 10))

        self.btn_start = ctk.CTkButton(
            left_panel,
            text="START PROCESU",
            fg_color="#10b981",
            hover_color="#059669",
            height=35,
            font=ctk.CTkFont(weight="bold"),
            command=self.start_process
        )
        self.btn_start.pack(fill="x", padx=10, pady=2)

        self.btn_stop = ctk.CTkButton(
            left_panel,
            text="STOP PROCESU",
            fg_color="#ef4444",
            hover_color="#dc2626",
            height=35,
            font=ctk.CTkFont(weight="bold"),
            command=self.stop_process)
        self.btn_stop.pack(fill="x", padx=10, pady=2)

        # --- OKIENKO KOMUNIKATÓW I BŁĘDÓW SYSTEMU ---
        ctk.CTkLabel(left_panel, text="KOMUNIKATY I BŁĘDY SYSTEMU", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=10, pady=(10, 2))

        self.log_box = ctk.CTkTextbox(left_panel, font=ctk.CTkFont(family="Courier", size=10), height=110)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_box.configure(state="disabled")

        right_panel = ctk.CTkFrame(main_container)
        right_panel.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        readings_frame = ctk.CTkFrame(right_panel)
        readings_frame.pack(fill="x", padx=10, pady=5)

        self.lbl_ph_read = ctk.CTkLabel(readings_frame, text="pH: 7.00", font=ctk.CTkFont(size=22, weight="bold"), text_color="#38bdf8")
        self.lbl_ph_read.pack(side="left", expand=True, pady=12)

        self.lbl_temp_read = ctk.CTkLabel(readings_frame, text="Temp: 22.5 °C", font=ctk.CTkFont(size=22, weight="bold"), text_color="#f43f5e")
        self.lbl_temp_read.pack(side="left", expand=True, pady=12)

        content_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Wykres
        chart_frame = ctk.CTkFrame(content_frame)
        chart_frame.pack(side="left", fill="both", expand=True, padx=(5, 5))
        self._setup_matplotlib(chart_frame)

        # Tabela
        table_frame = ctk.CTkFrame(content_frame, width=380)
        table_frame.pack(side="right", fill="both", padx=(5, 5))
        table_frame.pack_propagate(False)

        ctk.CTkLabel(table_frame, text="REJESTR ODCZYTÓW", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=10, pady=(8, 2))

        self.table_box = ctk.CTkTextbox(table_frame, font=ctk.CTkFont(family="Courier", size=11))
        self.table_box.pack(fill="both", expand=True, padx=10, pady=5)

        header_text = f"{'Czas':<8} | {'pH':<6} | {'Temp [°C]':<8}\n" + "-" * 30 + "\n"
        self.table_box.insert("end", header_text)
        self.table_box.configure(state="disabled")

        report_btn_frame = ctk.CTkFrame(table_frame, fg_color="transparent")
        report_btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        btn_save_csv = ctk.CTkButton(
            report_btn_frame, text="CSV", fg_color="#0284c7", hover_color="#0369a1", height=28,
            font=ctk.CTkFont(size=11), command=self.save_report_csv
        )
        btn_save_csv.pack(side="left", padx=(0, 2), expand=True, fill="x")

        btn_save_txt = ctk.CTkButton(
            report_btn_frame, text="TXT", fg_color="#475569", hover_color="#334155", height=28,
            font=ctk.CTkFont(size=11), command=self.save_report_txt
        )
        btn_save_txt.pack(side="right", padx=(2, 0), expand=True, fill="x")

        # PANEL STEROWANIA ZASILACZAMI
        manual_frame = ctk.CTkFrame(right_panel)
        manual_frame.pack(fill="x", padx=10, pady=10)

        self.switch_manual = ctk.CTkSwitch(
            manual_frame,
            text="Włącz sterowanie ręczne zasilaczami (Przejmij kontrolę)",
            font=ctk.CTkFont(weight="bold"),
            command=self.toggle_manual_mode
        )
        self.switch_manual.pack(anchor="w", padx=10, pady=8)

        sliders_frame = ctk.CTkFrame(manual_frame)
        sliders_frame.pack(fill="x", padx=10, pady=5)

        # Pompa Soli
        ctk.CTkLabel(sliders_frame, text="Zasilacz Pompy Soli (0-8V):").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.slider_salt = ctk.CTkSlider(sliders_frame, from_=0, to=8, number_of_steps=80, command=self._update_slider_labels)
        self.slider_salt.set(0)
        self.slider_salt.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

        self.lbl_salt_v = ctk.CTkLabel(sliders_frame, text="0.0 V (AUTO)", font=ctk.CTkFont(weight="bold"), width=120)
        self.lbl_salt_v.grid(row=0, column=2, padx=10, pady=8)

        # Pompa Zasady
        ctk.CTkLabel(sliders_frame, text="Zasilacz Pompy Zasady (0-8V):").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.slider_base = ctk.CTkSlider(sliders_frame, from_=0, to=8, number_of_steps=80, command=self._update_slider_labels)
        self.slider_base.set(0)
        self.slider_base.grid(row=1, column=1, padx=10, pady=8, sticky="ew")

        self.lbl_base_v = ctk.CTkLabel(sliders_frame, text="0.0 V (AUTO)", font=ctk.CTkFont(weight="bold"), width=120)
        self.lbl_base_v.grid(row=1, column=2, padx=10, pady=8)

        sliders_frame.columnconfigure(1, weight=1)
        self.toggle_manual_mode()

    def log_message(self, message: str, level: str = "INFO"):
        """Wpisuje komunikat/błąd do okna logów na panelu bocznym."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_line = f"[{timestamp}] [{level}] {message}\n"

        def _append():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", formatted_line)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

        self.after(0, _append)

    def _add_port_select(self, parent, label_text, default_val):
        ctk.CTkLabel(parent, text=label_text).pack(anchor="w", padx=10)
        initial_ports = self.gcp if self.gcp else ["Brak portów"]
        combo = ctk.CTkOptionMenu(parent, values=initial_ports)
        combo.pack(fill="x", padx=10, pady=(0, 5))
        return combo

    def _setup_matplotlib(self, parent):
        plt.style.use("dark_background")
        self.fig, self.ax = plt.subplots(figsize=(5, 3), dpi=100)
        self.fig.patch.set_facecolor("#2b2b2b")
        self.ax.set_facecolor("#1e1e1e")

        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)

    def _update_slider_labels(self, _=None):
        if self.manual_mode:
            v_salt = round(self.slider_salt.get(), 1)
            v_base = round(self.slider_base.get(), 1)
            self.lbl_salt_v.configure(text=f"{v_salt:.1f} V (MANUAL)")
            self.lbl_base_v.configure(text=f"{v_base:.1f} V (MANUAL)")

            if self.is_running and self.zas_1 and self.zas_2:
                try:
                    self.zas_1.set_voltage(v_salt)
                    self.zas_2.set_voltage(v_base)
                except Exception as e:
                    self.log_message(f"Błąd nastawy ręcznej V: {e}", "BŁĄD")

    def refresh_ports(self):
        self.gcp = get_com_ports()
        available_ports = self.gcp if self.gcp else ["Brak portów"]
        for combo in [self.combo_salt, self.combo_base, self.combo_ph]:
            current_selection = combo.get()
            combo.configure(values=available_ports)
            if current_selection in available_ports:
                combo.set(current_selection)
            else:
                combo.set(available_ports[0])
        self.log_message("Odświeżono listę portów USB.", "INFO")

    def toggle_manual_mode(self):
        self.manual_mode = bool(self.switch_manual.get())
        state = "normal" if self.manual_mode else "disabled"
        self.slider_salt.configure(state=state)
        self.slider_base.configure(state=state)
        self._update_slider_labels()

        mode_str = "RĘCZNY" if self.manual_mode else "AUTOMATYCZNY"
        self.log_message(f"Przełączono tryb zasilaczy na: {mode_str}", "INFO")

    def start_process(self):
        if not self.is_running:
            port_salt = self.combo_salt.get()
            port_base = self.combo_base.get()
            port_ph = self.combo_ph.get()

            if len({port_salt, port_base, port_ph}) < 3:
                self.log_message("Wybierz RÓŻNE porty COM dla urządzeń!", "OSTRZEŻENIE")

            self.log_message("Łączenie z urządzeniami...", "INFO")

            try:
                self.zas_1 = KoradKD3005P(port_salt)
                self.zas_2 = KoradKD3005P(port_base)
                self.log_message("Połączono z zasilaczami pompy soli i zasady.", "INFO")

                if hasattr(self.zas_1, 'enable_output'):
                    self.zas_1.enable_output(True)
                if hasattr(self.zas_2, 'enable_output'):
                    self.zas_2.enable_output(True)

            except Exception as e:
                self.log_message(f"Błąd połączenia z zasilaczami: {e}", "BŁĄD")
                self.stop_process()
                return

            try:
                self.ph_metr = pHMetr(port_ph)
                self.log_message(f"Otwarto port miernika pH na {port_ph}.", "INFO")
            except Exception as e:
                self.log_message(f"Błąd połączenia z miernikiem pH ({port_ph}): {e}", "BŁĄD")
                self.stop_process()
                return

            self.is_running = True
            self.status_label.configure(text="STATUS: PRACA AKTYWNA", text_color="#10b981")

            self.combo_salt.configure(state="disabled")
            self.combo_base.configure(state="disabled")
            self.combo_ph.configure(state="disabled")

            self.time_data.clear()
            self.ph_data.clear()
            self.time_counter = 0

            self.log_message("Proces został pomyślnie uruchomiony.", "INFO")
            threading.Thread(target=self._process_loop, daemon=True).start()

    def stop_process(self):
        self.is_running = False
        self.status_label.configure(text="STATUS: ZATRZYMANY", text_color="#ef4444")

        self.combo_salt.configure(state="normal")
        self.combo_base.configure(state="normal")
        self.combo_ph.configure(state="normal")

        if self.zas_1:
            try:
                if hasattr(self.zas_1, 'set_voltage'):
                    self.zas_1.set_voltage(0.0)
                if hasattr(self.zas_1, 'enable_output'):
                    self.zas_1.enable_output(False)
                if hasattr(self.zas_1, 'close'):
                    self.zas_1.close()
            except Exception as e:
                self.log_message(f"Błąd podczas rozłączania Zasilacza 1: {e}", "OSTRZEŻENIE")
            finally:
                self.zas_1 = None

        if self.zas_2:
            try:
                if hasattr(self.zas_2, 'set_voltage'):
                    self.zas_2.set_voltage(0.0)
                if hasattr(self.zas_2, 'enable_output'):
                    self.zas_2.enable_output(False)
                if hasattr(self.zas_2, 'close'):
                    self.zas_2.close()
            except Exception as e:
                self.log_message(f"Błąd podczas rozłączania Zasilacza 2: {e}", "OSTRZEŻENIE")
            finally:
                self.zas_2 = None

        if self.ph_metr:
            try:
                if hasattr(self.ph_metr, 'close'):
                    self.ph_metr.close()
                self.log_message("Zamknięto port miernika pH.", "INFO")
            except Exception as e:
                self.log_message(f"Błąd podczas rozłączania miernika pH: {e}", "OSTRZEŻENIE")
            finally:
                self.ph_metr = None

        self.auto_salt_v = 0.0
        self.auto_base_v = 0.0

        self.slider_salt.set(0)
        self.slider_base.set(0)
        self.lbl_salt_v.configure(text="0.0 V (AUTO)")
        self.lbl_base_v.configure(text="0.0 V (AUTO)")

        self.log_message("Proces został zatrzymany. Wszystkie urządzenia rozłączone.", "INFO")

    def _process_loop(self):
        while self.is_running:
            try:
                target_ph = float(self.entry_target_ph.get())
                max_above = float(self.entry_max_above.get())
                max_below = float(self.entry_max_below.get())
                const_v = float(self.entry_const_v.get())
            except ValueError:
                self.log_message("Nieprawidłowy format nastaw! Przyjęto wartości domyślne.", "OSTRZEŻENIE")
                target_ph, max_above, max_below, const_v = 7.0, 0.5, 0.5, 5.0

            wybrany_port_ph = self.combo_ph.get()

            if self.ph_metr:
                try:
                    ph, temp = self.ph_metr.read_data()
                    self.current_ph = ph
                    self.current_temp = temp
                except Exception as e:
                    self.log_message(f"Błąd odczytu ramki z miernika pH ({wybrany_port_ph}): {e}", "BŁĄD")
            else:
                self.log_message("Brak aktywnego połączenia z miernikiem pH!", "OSTRZEŻENIE")

            self.time_counter += 1

            if not self.manual_mode:
                mode = self.combo_constant_psu.get()
                try:
                    if mode == "Pompa Soli (Zasilacz 1)":
                        self.auto_salt_v = const_v
                        voltage = self.pid_base.compute(self.current_ph, target_ph, max_above, mode="acid")
                        self.auto_base_v = voltage

                        if self.zas_1: self.zas_1.set_voltage(const_v)
                        if self.zas_2: self.zas_2.set_voltage(voltage)

                    elif mode == "Pompa Zasady (Zasilacz 2)":
                        self.auto_base_v = const_v
                        voltage = self.pid_salt.compute(self.current_ph, target_ph, max_below, mode="base")
                        self.auto_salt_v = voltage

                        if self.zas_1: self.zas_1.set_voltage(voltage)
                        if self.zas_2: self.zas_2.set_voltage(const_v)

                except Exception as e:
                    self.log_message(f"Błąd podczas wysyłania napięcia do zasilacza: {e}", "BŁĄD")

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            time_only_str = now_str.split(" ")[1]

            self.report_data.append((now_str, self.current_ph, self.current_temp))

            self.time_data.append(self.time_counter)
            self.ph_data.append(self.current_ph)

            if len(self.time_data) > 40:
                self.time_data.pop(0)
                self.ph_data.pop(0)

            self.after(0, self._update_ui, target_ph, max_above, max_below, time_only_str)
            time.sleep(1)

    def _update_ui(self, target_ph, max_above, max_below, time_str):
        self.lbl_ph_read.configure(text=f"pH: {self.current_ph:.2f}")
        self.lbl_temp_read.configure(text=f"Temp: {self.current_temp:.1f} °C")

        if not self.manual_mode:
            self.slider_salt.set(self.auto_salt_v)
            self.slider_base.set(self.auto_base_v)
            self.lbl_salt_v.configure(text=f"{self.auto_salt_v:.1f} V (AUTO)")
            self.lbl_base_v.configure(text=f"{self.auto_base_v:.1f} V (AUTO)")

        row_text = f"{time_str:<8} | {self.current_ph:<6.2f} | {self.current_temp:<8.1f}\n"
        self.table_box.configure(state="normal")
        self.table_box.insert("end", row_text)
        self.table_box.see("end")
        self.table_box.configure(state="disabled")

        self.ax.clear()
        self.ax.set_title("Zmiana pH w czasie (odświeżanie co 1s)", color="white", fontsize=11)
        self.ax.set_xlabel("Czas [s]", color="white", fontsize=9)
        self.ax.set_ylabel("pH", color="white", fontsize=9)
        self.ax.plot(self.time_data, self.ph_data, color="#38bdf8", linewidth=2, label="Odczyt pH")
        self.ax.axhline(y=target_ph, color="#10b981", linestyle="-", linewidth=2, label="Zadane pH")
        self.ax.axhline(y=target_ph + max_above, color="#ef4444", linestyle="--", label="Maks. Góra")
        self.ax.axhline(y=target_ph - max_below, color="#ef4444", linestyle="--", label="Maks. Dół")
        self.ax.legend(loc="upper left", fontsize=8)
        self.ax.grid(True, linestyle=":", alpha=0.4)
        self.canvas.draw_idle()

    def save_report_csv(self):
        if not self.report_data:
            self.log_message("Brak danych do zapisu raportu CSV.", "OSTRZEŻENIE")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Pliki CSV", "*.csv"), ("Wszystkie pliki", "*.*")],
            title="Zapisz raport jako CSV"
        )
        if file_path:
            try:
                with open(file_path, mode="w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f, delimiter=";")
                    writer.writerow(["Data_i_Czas", "pH", "Temperatura_C"])
                    writer.writerows(self.report_data)
                self.log_message(f"Raport CSV zapisano w: {file_path}", "INFO")
            except Exception as e:
                self.log_message(f"Błąd zapisu pliku CSV: {e}", "BŁĄD")

    def save_report_txt(self):
        if not self.report_data:
            self.log_message("Brak danych do zapisu raportu TXT.", "OSTRZEŻENIE")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")],
            title="Zapisz raport jako TXT"
        )
        if file_path:
            try:
                with open(file_path, mode="w", encoding="utf-8") as f:
                    f.write("RAPORT AUTOMATYZACJI DOZOWANIA pH\n")
                    f.write("=" * 55 + "\n")
                    f.write(f"{'Data i Czas':<25} | {'pH':<10} | {'Temp [°C]':<10}\n")
                    f.write("-" * 55 + "\n")
                    for record in self.report_data:
                        f.write(f"{record[0]:<25} | {record[1]:<10.2f} | {record[2]:<10.1f}\n")
                self.log_message(f"Raport TXT zapisano w: {file_path}", "INFO")
            except Exception as e:
                self.log_message(f"Błąd zapisu pliku TXT: {e}", "BŁĄD")
