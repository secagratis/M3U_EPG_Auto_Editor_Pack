import os
import re
import io
import gzip
import urllib.request
import xml.etree.ElementTree as ET
import difflib
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


def normalize_name(text):
    if not text:
        return ""
    s = text.lower().strip()
    # Rimuove prefissi/suffissi comuni (IT:, FHD, HD, 4K, SD, HEVC, ecc.)
    s = re.sub(r'^(it|ita|uk|us|fr|de|es)\s*[:|\-]\s*', '', s)
    s = re.sub(r'\b(full\s*hd|fhd|uhd|4k|hd|sd|hevc|h265|h264|1080p|720p|50fps|backup|alt|vip|it|ita)\b', '', s)
    # Rimuove caratteri non alfanumerici
    s = re.sub(r'[^a-z0-9]', '', s)
    return s


class M3UEPGAutoEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("M3U & EPG Auto-Editor (Abbinamento Automatico tvg-id)")
        self.root.geometry("1180x720")
        self.root.configure(bg="#12141a")

        self.m3u_header = "#EXTM3U"
        self.channels = []  # list of dicts
        self.epg_channels = {}  # id -> display_name
        self.epg_norm_map = {}  # normalized -> id
        self.epg_all_ids = []

        self._setup_styles()
        self._build_ui()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        bg_dark = "#12141a"
        bg_panel = "#1b1f2a"
        bg_card = "#232836"
        fg_text = "#e4e8f0"
        accent = "#2563eb"

        style.configure("TFrame", background=bg_dark)
        style.configure("Panel.TFrame", background=bg_panel)
        style.configure("TLabel", background=bg_panel, foreground=fg_text, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=bg_dark, foreground="#ffffff", font=("Segoe UI", 14, "bold"))
        style.configure("Status.TLabel", background=bg_dark, foreground="#9ca3af", font=("Segoe UI", 9))

        style.configure("TButton", background=accent, foreground="white", font=("Segoe UI", 9, "bold"), borderwidth=0, padding=6)
        style.map("TButton", background=[("active", "#1d4ed8")])

        style.configure("Green.TButton", background="#059669", foreground="white", font=("Segoe UI", 9, "bold"), borderwidth=0, padding=6)
        style.map("Green.TButton", background=[("active", "#047857")])

        style.configure("Secondary.TButton", background="#374151", foreground="white", font=("Segoe UI", 9), borderwidth=0, padding=6)
        style.map("Secondary.TButton", background=[("active", "#4b5563")])

        style.configure("Treeview",
                        background=bg_card,
                        foreground=fg_text,
                        fieldbackground=bg_card,
                        rowheight=27,
                        font=("Segoe UI", 9),
                        borderwidth=0)
        style.configure("Treeview.Heading",
                        background="#2d3344",
                        foreground="#ffffff",
                        font=("Segoe UI", 9, "bold"),
                        borderwidth=0)
        style.map("Treeview", background=[("selected", accent)], foreground=[("selected", "white")])

    def _build_ui(self):
        # Header
        top = ttk.Frame(self.root, style="TFrame", padding=(12, 10))
        top.pack(fill=tk.X)
        ttk.Label(top, text="🛠️ M3U & EPG Auto-Editor", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(
            top,
            text="Abbina automaticamente i canali M3U agli ID della guida XMLTV ed esporta la playlist corretta",
            background="#12141a", foreground="#94a3b8", font=("Segoe UI", 9)
        ).pack(side=tk.LEFT, padx=14)

        # Input Frame
        inp = ttk.Frame(self.root, style="Panel.TFrame", padding=10)
        inp.pack(fill=tk.X, padx=12, pady=(0, 8))

        # M3U row
        ttk.Label(inp, text="1. Playlist M3U:").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        self.m3u_var = tk.StringVar()
        tk.Entry(inp, textvariable=self.m3u_var, bg="#232836", fg="white", insertbackground="white", relief=tk.FLAT, font=("Segoe UI", 10)).grid(row=0, column=1, sticky="ew", padx=4, pady=4, ipady=4)
        ttk.Button(inp, text="Sfoglia M3U...", style="Secondary.TButton", command=self.browse_m3u).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(inp, text="Carica M3U", command=self.load_m3u_thread).grid(row=0, column=3, padx=4, pady=4)

        # EPG row
        ttk.Label(inp, text="2. Guida EPG (XML):").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=4)
        self.epg_var = tk.StringVar()
        tk.Entry(inp, textvariable=self.epg_var, bg="#232836", fg="white", insertbackground="white", relief=tk.FLAT, font=("Segoe UI", 10)).grid(row=1, column=1, sticky="ew", padx=4, pady=4, ipady=4)
        ttk.Button(inp, text="Sfoglia EPG...", style="Secondary.TButton", command=self.browse_epg).grid(row=1, column=2, padx=4, pady=4)
        ttk.Button(inp, text="Carica EPG", command=self.load_epg_thread).grid(row=1, column=3, padx=4, pady=4)

        inp.columnconfigure(1, weight=1)

        # Action Bar
        act = ttk.Frame(self.root, style="Panel.TFrame", padding=(10, 8))
        act.pack(fill=tk.X, padx=12, pady=(0, 8))

        ttk.Button(act, text="⚡ Abbina Automaticamente Tutti i Canali", style="Green.TButton", command=self.auto_match_all).pack(side=tk.LEFT, padx=(0, 8))

        self.only_unmatched_var = tk.BooleanVar(value=False)
        cb = tk.Checkbutton(
            act, text="Mostra solo non abbinati", variable=self.only_unmatched_var,
            bg="#1b1f2a", fg="#e4e8f0", selectcolor="#232836", activebackground="#1b1f2a",
            activeforeground="white", font=("Segoe UI", 9), command=self.refresh_table
        )
        cb.pack(side=tk.LEFT, padx=8)

        ttk.Label(act, text="Filtra:").pack(side=tk.LEFT, padx=(12, 4))
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *a: self.refresh_table())
        tk.Entry(act, textvariable=self.filter_var, bg="#232836", fg="white", insertbackground="white", relief=tk.FLAT, width=22, font=("Segoe UI", 9)).pack(side=tk.LEFT, ipady=3)

        ttk.Button(act, text="💾 Salva Nuova Playlist M3U...", command=self.export_m3u).pack(side=tk.RIGHT)

        # Main Table
        table_frame = ttk.Frame(self.root, style="Panel.TFrame", padding=8)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 6))

        cols = ("num", "name", "group", "old_id", "new_id", "epg_name", "status")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("num", text="#")
        self.tree.heading("name", text="Nome Canale (M3U)")
        self.tree.heading("group", text="Gruppo")
        self.tree.heading("old_id", text="tvg-id Originale")
        self.tree.heading("new_id", text="Nuovo tvg-id (EPG)")
        self.tree.heading("epg_name", text="Nome nell'EPG")
        self.tree.heading("status", text="Stato Abbinamento")

        self.tree.column("num", width=45, anchor="center")
        self.tree.column("name", width=210, anchor="w")
        self.tree.column("group", width=130, anchor="w")
        self.tree.column("old_id", width=160, anchor="w")
        self.tree.column("new_id", width=190, anchor="w")
        self.tree.column("epg_name", width=180, anchor="w")
        self.tree.column("status", width=170, anchor="center")

        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Double-1>", self.edit_selected_channel)

        # Status Bar
        self.status_var = tk.StringVar(value="Pronto. Carica prima la playlist M3U e poi il file EPG XMLTV. Doppio clic su una riga per modificare manualmente.")
        ttk.Label(self.root, textvariable=self.status_var, style="Status.TLabel", padding=(12, 6)).pack(fill=tk.X)

    def browse_m3u(self):
        path = filedialog.askopenfilename(title="Seleziona Playlist M3U", filetypes=[("Playlist M3U", "*.m3u *.m3u8"), ("Tutti i file", "*.*")])
        if path:
            self.m3u_var.set(path)
            self.load_m3u_thread()

    def browse_epg(self):
        path = filedialog.askopenfilename(title="Seleziona Guida EPG XMLTV", filetypes=[("File XMLTV", "*.xml *.gz"), ("Tutti i file", "*.*")])
        if path:
            self.epg_var.set(path)
            self.load_epg_thread()

    def _fetch_bytes(self, source):
        if source.startswith(("http://", "https://")):
            req = urllib.request.Request(source, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=35) as resp:
                raw = resp.read()
        else:
            with open(source, "rb") as f:
                raw = f.read()

        if source.lower().endswith(".gz") or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return raw

    def load_m3u_thread(self):
        src = self.m3u_var.get().strip()
        if not src:
            messagebox.showwarning("Attenzione", "Inserisci un URL o seleziona un file M3U.")
            return
        self.status_var.set("Caricamento playlist M3U...")
        threading.Thread(target=self._parse_m3u, args=(src,), daemon=True).start()

    def _parse_m3u(self, src):
        try:
            raw = self._fetch_bytes(src)
            text = raw.decode("utf-8", errors="replace")
            lines = text.splitlines()

            header = "#EXTM3U"
            parsed = []
            current_extinf = None
            extra_lines = []

            for line in lines:
                s = line.strip()
                if not s:
                    continue
                if s.startswith("#EXTM3U"):
                    header = s
                elif s.startswith("#EXTINF:"):
                    current_extinf = s
                    extra_lines = []
                elif s.startswith("#") and current_extinf:
                    extra_lines.append(s)
                elif not s.startswith("#") and current_extinf:
                    tvg_id = self._get_attr(current_extinf, "tvg-id")
                    tvg_name = self._get_attr(current_extinf, "tvg-name")
                    tvg_logo = self._get_attr(current_extinf, "tvg-logo")
                    group = self._get_attr(current_extinf, "group-title") or "Generale"
                    name = current_extinf.split(",")[-1].strip() if "," in current_extinf else (tvg_name or "Canale")

                    parsed.append({
                        "raw_extinf": current_extinf,
                        "extra_lines": extra_lines,
                        "url": s,
                        "name": name,
                        "group": group,
                        "old_id": tvg_id,
                        "tvg_name": tvg_name,
                        "tvg_logo": tvg_logo,
                        "new_id": tvg_id,
                        "epg_name": "",
                        "status": "In attesa"
                    })
                    current_extinf = None
                    extra_lines = []

            self.m3u_header = header
            self.channels = parsed
            self.root.after(0, self._on_m3u_loaded)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Errore M3U", str(e)))

    def _get_attr(self, line, attr):
        m = re.search(rf'{attr}="([^"]*)"', line, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    def _on_m3u_loaded(self):
        self.refresh_table()
        self.status_var.set(f"Playlist M3U caricata: {len(self.channels)} canali.")
        if self.epg_channels:
            self.auto_match_all()

    def load_epg_thread(self):
        src = self.epg_var.get().strip()
        if not src:
            messagebox.showwarning("Attenzione", "Inserisci un URL o seleziona un file EPG XMLTV.")
            return
        self.status_var.set("Lettura rapida canali dall'EPG XMLTV...")
        threading.Thread(target=self._parse_epg_channels, args=(src,), daemon=True).start()

    def _parse_epg_channels(self, src):
        try:
            raw = self._fetch_bytes(src)
            epg_ch = {}
            norm_map = {}

            context = ET.iterparse(io.BytesIO(raw), events=("end",))
            for event, elem in context:
                if elem.tag == "channel":
                    cid = elem.attrib.get("id", "").strip()
                    if cid:
                        disp_names = [d.text.strip() for d in elem.findall("display-name") if d.text and d.text.strip()]
                        primary_name = disp_names[0] if disp_names else cid
                        epg_ch[cid] = primary_name

                        norm_id = normalize_name(cid)
                        if norm_id and norm_id not in norm_map:
                            norm_map[norm_id] = cid
                        for dn in disp_names:
                            ndn = normalize_name(dn)
                            if ndn and ndn not in norm_map:
                                norm_map[ndn] = cid
                    elem.clear()
                elif elem.tag == "programme":
                    elem.clear()

            self.epg_channels = epg_ch
            self.epg_norm_map = norm_map
            self.epg_all_ids = sorted(epg_ch.keys())
            self.root.after(0, self._on_epg_loaded)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Errore EPG", str(e)))

    def _on_epg_loaded(self):
        self.status_var.set(f"EPG analizzata: {len(self.epg_channels)} canali disponibili nell'XML.")
        if self.channels:
            self.auto_match_all()

    def auto_match_all(self):
        if not self.channels:
            messagebox.showwarning("Attenzione", "Carica prima una playlist M3U.")
            return
        if not self.epg_channels:
            messagebox.showwarning("Attenzione", "Carica prima un file EPG XMLTV.")
            return

        epg_lower_map = {k.lower(): k for k in self.epg_channels.keys()}
        epg_disp_lower = {v.lower(): k for k, v in self.epg_channels.items()}
        norm_keys = list(self.epg_norm_map.keys())

        matched_count = 0
        for ch in self.channels:
            old_id = ch["old_id"]
            tvg_name = ch["tvg_name"]
            name = ch["name"]

            if old_id and old_id in self.epg_channels:
                ch["new_id"] = old_id
                ch["epg_name"] = self.epg_channels[old_id]
                ch["status"] = "✅ Esatto (ID)"
                matched_count += 1
                continue

            found_cid = None
            for cand in (old_id, tvg_name, name):
                if not cand:
                    continue
                cl = cand.lower()
                if cl in epg_lower_map:
                    found_cid = epg_lower_map[cl]
                    break
                if cl in epg_disp_lower:
                    found_cid = epg_disp_lower[cl]
                    break

            if found_cid:
                ch["new_id"] = found_cid
                ch["epg_name"] = self.epg_channels[found_cid]
                ch["status"] = "✅ Esatto (Nome)"
                matched_count += 1
                continue

            for cand in (old_id, tvg_name, name):
                nc = normalize_name(cand)
                if nc and nc in self.epg_norm_map:
                    found_cid = self.epg_norm_map[nc]
                    break

            if found_cid:
                ch["new_id"] = found_cid
                ch["epg_name"] = self.epg_channels[found_cid]
                ch["status"] = "🟢 Normalizzato"
                matched_count += 1
                continue

            nc_main = normalize_name(name or tvg_name)
            if nc_main and len(nc_main) >= 3:
                close = difflib.get_close_matches(nc_main, norm_keys, n=1, cutoff=0.82)
                if close:
                    found_cid = self.epg_norm_map[close[0]]
                    ch["new_id"] = found_cid
                    ch["epg_name"] = self.epg_channels[found_cid]
                    ch["status"] = "🟡 Simile (Auto)"
                    matched_count += 1
                    continue

            ch["epg_name"] = "-"
            ch["status"] = "❌ Non trovato"

        self.refresh_table()
        self.status_var.set(f"Abbinamento completato: {matched_count} su {len(self.channels)} canali abbinati all'EPG!")

    def refresh_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        q = self.filter_var.get().strip().lower()
        only_unmatched = self.only_unmatched_var.get()

        for idx, ch in enumerate(self.channels):
            if only_unmatched and "❌" not in ch["status"]:
                continue
            if q and (
                q not in ch["name"].lower()
                and q not in ch["group"].lower()
                and q not in ch["new_id"].lower()
                and q not in ch["epg_name"].lower()
            ):
                continue

            self.tree.insert(
                "", tk.END, iid=str(idx),
                values=(idx + 1, ch["name"], ch["group"], ch["old_id"], ch["new_id"], ch["epg_name"], ch["status"])
            )

    def edit_selected_channel(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        ch = self.channels[idx]

        win = tk.Toplevel(self.root)
        win.title(f"Modifica Canale: {ch['name']}")
        win.geometry("500x260")
        win.configure(bg="#1b1f2a")
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text=f"Canale M3U: {ch['name']}", bg="#1b1f2a", fg="white", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16, pady=(14, 6))
        tk.Label(win, text="Seleziona o digita il tvg-id dell'EPG:", bg="#1b1f2a", fg="#cbd5e1", font=("Segoe UI", 9)).pack(anchor="w", padx=16)

        combo_var = tk.StringVar(value=ch["new_id"])
        options = [f"{cid}  ({disp})" for cid, disp in sorted(self.epg_channels.items())]
        combo = ttk.Combobox(win, textvariable=combo_var, values=options, font=("Segoe UI", 10))
        combo.pack(fill=tk.X, padx=16, pady=8)

        def save_edit():
            val = combo_var.get().strip()
            if "  (" in val:
                val = val.split("  (", 1)[0].strip()
            ch["new_id"] = val
            if val in self.epg_channels:
                ch["epg_name"] = self.epg_channels[val]
                ch["status"] = "✏️ Manuale"
            elif val:
                ch["epg_name"] = "(ID Personalizzato)"
                ch["status"] = "✏️ Manuale"
            else:
                ch["epg_name"] = "-"
                ch["status"] = "❌ Non trovato"
            self.refresh_table()
            win.destroy()

        btn_row = ttk.Frame(win, style="Panel.TFrame")
        btn_row.pack(fill=tk.X, padx=16, pady=14)
        ttk.Button(btn_row, text="Salva Modifica", style="Green.TButton", command=save_edit).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_row, text="Annulla", style="Secondary.TButton", command=win.destroy).pack(side=tk.RIGHT)

    def _build_updated_extinf(self, ch):
        line = ch["raw_extinf"]
        new_id = ch["new_id"]
        if re.search(r'tvg-id="[^"]*"', line, re.IGNORECASE):
            line = re.sub(r'tvg-id="[^"]*"', f'tvg-id="{new_id}"', line, count=1, flags=re.IGNORECASE)
        else:
            parts = line.split(" ", 1)
            if len(parts) == 2:
                line = f'{parts[0]} tvg-id="{new_id}" {parts[1]}'
            else:
                comma_parts = line.split(",", 1)
                if len(comma_parts) == 2:
                    line = f'{comma_parts[0]} tvg-id="{new_id}",{comma_parts[1]}'
        return line

    def export_m3u(self):
        if not self.channels:
            messagebox.showwarning("Attenzione", "Nessun canale da esportare.")
            return

        out_path = filedialog.asksaveasfilename(
            title="Salva Playlist M3U Aggiornata",
            defaultextension=".m3u",
            initialfile="playlist_epg_abbinata.m3u",
            filetypes=[("Playlist M3U", "*.m3u"), ("Playlist M3U8", "*.m3u8")]
        )
        if not out_path:
            return

        try:
            header = self.m3u_header
            epg_src = self.epg_var.get().strip()
            if epg_src.startswith(("http://", "https://")) and "url-tvg=" not in header.lower():
                header = f'#EXTM3U url-tvg="{epg_src}"'

            out_lines = [header]
            for ch in self.channels:
                out_lines.append(self._build_updated_extinf(ch))
                for ex in ch["extra_lines"]:
                    out_lines.append(ex)
                out_lines.append(ch["url"])

            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(out_lines) + "\n")

            messagebox.showinfo("Esportazione Completata", f"Playlist salvata con successo in:\n{out_path}")
            self.status_var.set(f"Esportata nuova playlist M3U in: {out_path}")
        except Exception as e:
            messagebox.showerror("Errore Salvataggio", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = M3UEPGAutoEditor(root)
    root.mainloop()
