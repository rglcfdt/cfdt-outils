import os
import re
import stat
import time
import socket
import threading
import unicodedata
from pathlib import Path, PurePosixPath
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import paramiko


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
SSH_HOST = "vps-1d06fb01.vps.ovh.net"
SSH_PORT = 56035
SSH_USER = "cfdt"
SSH_KEY = Path.home() / ".ssh" / "cfdt_cfdt"

UPLOAD_REMOTE_DIR = PurePosixPath("/opt/cfdt/data/imports")
DOWNLOAD_REMOTE_ROOT = PurePosixPath("/opt/cfdt")
LOCAL_DOWNLOAD_ENV = "CFDT_SCRIPTS_UNIX"

MAX_RETRIES = 5
RETRY_DELAY_SECONDS = 5
CHUNK_SIZE = 1024 * 1024


class TransferCancelled(Exception):
    pass


def safe_filename(filename: str) -> str:
    """Normalise uniquement le nom des fichiers envoyés vers le VPS."""
    path = Path(filename)
    stem = unicodedata.normalize("NFKD", path.stem)
    stem = stem.encode("ascii", "ignore").decode("ascii").lower()
    stem = re.sub(r"[^a-z0-9]+", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip("_") or "fichier"
    suffix = re.sub(r"[^a-zA-Z0-9.]", "", path.suffix).lower()
    return f"{stem}{suffix}"


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("o", "Kio", "Mio", "Gio", "Tio"):
        if value < 1024 or unit == "Tio":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} o"


class ScpTransferApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Transferts sécurisés VPS CFDT")
        self.root.geometry("1000x720")
        self.root.minsize(820, 580)

        self.upload_files = []
        self.cancel_event = threading.Event()
        self.running = False
        self.remote_loaded = False
        self.remote_nodes = {}

        self.local_download_dir = self.get_local_download_dir()

        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if self.local_download_dir is None:
            self.root.after(100, self.show_missing_environment_error)

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------
    def build_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        self.upload_tab = ttk.Frame(self.notebook, padding=10)
        self.download_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.upload_tab, text="Windows -> VPS")
        self.notebook.add(self.download_tab, text="VPS -> Windows")

        self.build_upload_tab()
        self.build_download_tab()

        progress_frame = ttk.LabelFrame(self.root, text="Progression", padding=10)
        progress_frame.pack(fill="x", padx=10, pady=5)

        self.current_label = ttk.Label(progress_frame, text="Aucun transfert en cours")
        self.current_label.pack(fill="x")
        self.current_progress = ttk.Progressbar(progress_frame, maximum=100)
        self.current_progress.pack(fill="x", pady=(4, 8))

        self.total_label = ttk.Label(progress_frame, text="Progression globale")
        self.total_label.pack(fill="x")
        self.total_progress = ttk.Progressbar(progress_frame, maximum=100)
        self.total_progress.pack(fill="x", pady=(4, 0))

        log_frame = ttk.LabelFrame(self.root, text="Journal", padding=5)
        log_frame.pack(fill="both", expand=False, padx=10, pady=(5, 10))
        self.log_text = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

    def build_upload_tab(self):
        toolbar = ttk.Frame(self.upload_tab)
        toolbar.pack(fill="x")

        self.select_upload_button = ttk.Button(
            toolbar, text="Sélectionner les fichiers", command=self.select_upload_files
        )
        self.select_upload_button.pack(side="left")

        self.start_upload_button = ttk.Button(
            toolbar, text="Transférer vers le VPS", command=self.start_upload, state="disabled"
        )
        self.start_upload_button.pack(side="left", padx=8)

        self.cancel_upload_button = ttk.Button(
            toolbar, text="Annuler", command=self.cancel, state="disabled"
        )
        self.cancel_upload_button.pack(side="left")

        ttk.Label(
            self.upload_tab,
            text=f"Répertoire distant : {UPLOAD_REMOTE_DIR}",
            padding=(0, 10, 0, 4),
        ).pack(fill="x")

        list_frame = ttk.Frame(self.upload_tab)
        list_frame.pack(fill="both", expand=True)
        self.upload_list = tk.Listbox(list_frame, selectmode="extended")
        upload_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.upload_list.yview)
        self.upload_list.configure(yscrollcommand=upload_scroll.set)
        self.upload_list.pack(side="left", fill="both", expand=True)
        upload_scroll.pack(side="right", fill="y")

    def build_download_tab(self):
        toolbar = ttk.Frame(self.download_tab)
        toolbar.pack(fill="x")

        self.refresh_remote_button = ttk.Button(
            toolbar, text="Charger / actualiser l'arborescence", command=self.start_remote_refresh
        )
        self.refresh_remote_button.pack(side="left")

        self.start_download_button = ttk.Button(
            toolbar, text="Télécharger la sélection", command=self.start_download, state="disabled"
        )
        self.start_download_button.pack(side="left", padx=8)

        self.cancel_download_button = ttk.Button(
            toolbar, text="Annuler", command=self.cancel, state="disabled"
        )
        self.cancel_download_button.pack(side="left")

        destination = str(self.local_download_dir) if self.local_download_dir else "variable absente"
        self.download_destination_label = ttk.Label(
            self.download_tab,
            text=f"Destination : %{LOCAL_DOWNLOAD_ENV}% = {destination}",
            padding=(0, 10, 0, 4),
        )
        self.download_destination_label.pack(fill="x")

        ttk.Label(
            self.download_tab,
            text=(
                "Sélectionnez un ou plusieurs fichiers. L'arborescence située sous "
                f"{DOWNLOAD_REMOTE_ROOT} sera conservée dans le répertoire Windows."
            ),
            padding=(0, 0, 0, 6),
        ).pack(fill="x")

        tree_frame = ttk.Frame(self.download_tab)
        tree_frame.pack(fill="both", expand=True)

        self.remote_tree = ttk.Treeview(
            tree_frame,
            columns=("type", "size"),
            show="tree headings",
            selectmode="extended",
        )
        self.remote_tree.heading("#0", text="Nom")
        self.remote_tree.heading("type", text="Type")
        self.remote_tree.heading("size", text="Taille")
        self.remote_tree.column("#0", width=560, minwidth=250)
        self.remote_tree.column("type", width=100, anchor="center")
        self.remote_tree.column("size", width=130, anchor="e")

        tree_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.remote_tree.yview)
        tree_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.remote_tree.xview)
        self.remote_tree.configure(yscrollcommand=tree_y.set, xscrollcommand=tree_x.set)

        self.remote_tree.grid(row=0, column=0, sticky="nsew")
        tree_y.grid(row=0, column=1, sticky="ns")
        tree_x.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.remote_tree.bind("<<TreeviewSelect>>", self.on_remote_selection)
        self.remote_tree.bind("<Double-1>", self.on_remote_double_click)

    # ------------------------------------------------------------------
    # Utilitaires communs
    # ------------------------------------------------------------------
    def ui(self, callback, *args, **kwargs):
        self.root.after(0, lambda: callback(*args, **kwargs))

    def log(self, text):
        def append():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", text + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.ui(append)

    def set_progress(self, current_text, current_value, total_value):
        self.ui(self.current_label.configure, text=current_text)
        self.ui(self.current_progress.configure, value=current_value)
        self.ui(self.total_progress.configure, value=total_value)

    def set_running(self, running: bool):
        self.running = running
        normal = "disabled" if running else "normal"
        self.ui(self.select_upload_button.configure, state=normal)
        self.ui(self.refresh_remote_button.configure, state=normal)
        self.ui(self.start_upload_button.configure,
                state="disabled" if running or not self.upload_files else "normal")
        self.ui(self.start_download_button.configure,
                state="disabled" if running or not self.selected_remote_files() else "normal")
        self.ui(self.cancel_upload_button.configure, state="normal" if running else "disabled")
        self.ui(self.cancel_download_button.configure, state="normal" if running else "disabled")

    @staticmethod
    def get_local_download_dir():
        raw_value = os.environ.get(LOCAL_DOWNLOAD_ENV, "").strip().strip('"')
        if not raw_value:
            return None
        return Path(os.path.expandvars(os.path.expanduser(raw_value))).resolve()

    def show_missing_environment_error(self):
        messagebox.showerror(
            "Variable d'environnement absente",
            f"La variable {LOCAL_DOWNLOAD_ENV} n'est pas définie.\n\n"
            "Définissez-la sous Windows puis relancez l'application.\n"
            f'Exemple PowerShell :\n[Environment]::SetEnvironmentVariable("{LOCAL_DOWNLOAD_ENV}", '
            '"C:\\\\Users\\\\Ronan\\\\Documents\\\\cfdt", "User")'
        )

    def connect(self):
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        client.connect(
            SSH_HOST,
            port=SSH_PORT,
            username=SSH_USER,
            key_filename=str(SSH_KEY),
            timeout=20,
            banner_timeout=20,
            auth_timeout=20,
            look_for_keys=False,
            allow_agent=False,
        )
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(20)
        return client, client.open_sftp()

    def validate_prerequisites(self, require_local_dir=False):
        if not SSH_KEY.exists():
            messagebox.showerror("Clé SSH introuvable", f"Clé absente : {SSH_KEY}")
            return False
        if require_local_dir:
            self.local_download_dir = self.get_local_download_dir()
            if self.local_download_dir is None:
                self.show_missing_environment_error()
                return False
            try:
                self.local_download_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror(
                    "Destination inaccessible",
                    f"Impossible de créer ou d'utiliser {self.local_download_dir} :\n{exc}",
                )
                return False
            self.download_destination_label.configure(
                text=f"Destination : %{LOCAL_DOWNLOAD_ENV}% = {self.local_download_dir}"
            )
        return True

    def cancel(self):
        self.cancel_event.set()
        self.log("Annulation demandée. Le fichier partiel est conservé pour une reprise ultérieure.")

    @staticmethod
    def ensure_remote_directory(sftp):
        current = PurePosixPath("/")
        for part in UPLOAD_REMOTE_DIR.parts[1:]:
            current /= part
            try:
                sftp.stat(str(current))
            except FileNotFoundError:
                sftp.mkdir(str(current))

    @staticmethod
    def is_path_under_root(remote_path: PurePosixPath) -> bool:
        try:
            remote_path.relative_to(DOWNLOAD_REMOTE_ROOT)
            return True
        except ValueError:
            return False

    def verify_remote_real_path(self, sftp, remote_path: PurePosixPath):
        """Interdit tout téléchargement sortant de /opt/cfdt, y compris via lien symbolique."""
        if not self.is_path_under_root(remote_path):
            raise PermissionError(f"Chemin distant interdit : {remote_path}")
        normalized_root = PurePosixPath(sftp.normalize(str(DOWNLOAD_REMOTE_ROOT)))
        normalized_path = PurePosixPath(sftp.normalize(str(remote_path)))
        try:
            normalized_path.relative_to(normalized_root)
        except ValueError as exc:
            raise PermissionError(
                f"Le chemin {remote_path} pointe en dehors de {DOWNLOAD_REMOTE_ROOT}."
            ) from exc

    # ------------------------------------------------------------------
    # Envoi Windows -> VPS
    # ------------------------------------------------------------------
    def select_upload_files(self):
        selected = filedialog.askopenfilenames(title="Sélectionner un ou plusieurs fichiers")
        if not selected:
            return
        self.upload_files = [Path(p) for p in selected]
        self.upload_list.delete(0, "end")
        for path in self.upload_files:
            self.upload_list.insert("end", f"{path}  ->  {safe_filename(path.name)}")
        self.start_upload_button.configure(state="normal")
        self.log(f"{len(self.upload_files)} fichier(s) sélectionné(s) pour l'envoi.")

    def start_upload(self):
        if self.running or not self.upload_files:
            return
        if not self.validate_prerequisites():
            return
        self.cancel_event.clear()
        self.current_progress.configure(value=0)
        self.total_progress.configure(value=0)
        self.set_running(True)
        threading.Thread(target=self.upload_all, daemon=True).start()

    def upload_with_resume(self, local_path: Path, file_index: int, total_files: int):
        remote_name = safe_filename(local_path.name)
        final_path = UPLOAD_REMOTE_DIR / remote_name
        partial_path = UPLOAD_REMOTE_DIR / f".{remote_name}.part"
        local_size = local_path.stat().st_size

        for attempt in range(1, MAX_RETRIES + 1):
            client = sftp = None
            try:
                if self.cancel_event.is_set():
                    raise TransferCancelled()
                self.log(f"Connexion au VPS, tentative {attempt}/{MAX_RETRIES}...")
                client, sftp = self.connect()
                self.ensure_remote_directory(sftp)
                try:
                    remote_size = sftp.stat(str(partial_path)).st_size
                except FileNotFoundError:
                    remote_size = 0
                if remote_size > local_size:
                    sftp.remove(str(partial_path))
                    remote_size = 0
                if remote_size:
                    self.log(f"Reprise de l'envoi de {remote_name} à {format_size(remote_size)}.")

                with local_path.open("rb") as source:
                    source.seek(remote_size)
                    mode = "ab" if remote_size else "wb"
                    with sftp.file(str(partial_path), mode) as target:
                        sent = remote_size
                        while sent < local_size:
                            if self.cancel_event.is_set():
                                raise TransferCancelled()
                            data = source.read(CHUNK_SIZE)
                            if not data:
                                break
                            target.write(data)
                            sent += len(data)
                            pct = sent * 100 / local_size if local_size else 100
                            total_pct = ((file_index - 1) + pct / 100) * 100 / total_files
                            self.set_progress(
                                f"Envoi {file_index}/{total_files} : {remote_name} - "
                                f"{format_size(sent)}/{format_size(local_size)} ({pct:.1f} %)",
                                pct,
                                total_pct,
                            )
                        target.flush()

                remote_final_size = sftp.stat(str(partial_path)).st_size
                if remote_final_size != local_size:
                    raise IOError(
                        f"Taille distante incorrecte : {remote_final_size} au lieu de {local_size}"
                    )
                try:
                    sftp.remove(str(final_path))
                except FileNotFoundError:
                    pass
                sftp.rename(str(partial_path), str(final_path))
                self.log(f"OK envoi : {local_path.name} -> {final_path} ({format_size(local_size)})")
                return
            except TransferCancelled:
                raise
            except (OSError, EOFError, socket.error, paramiko.SSHException) as exc:
                self.log(f"Envoi interrompu : {exc}")
                if attempt >= MAX_RETRIES:
                    raise
                self.wait_before_retry()
            finally:
                self.close_connection(sftp, client)

    def upload_all(self):
        try:
            total = len(self.upload_files)
            for index, path in enumerate(self.upload_files, start=1):
                self.upload_with_resume(path, index, total)
            self.set_progress("Envoi terminé", 100, 100)
            self.log("Tous les fichiers ont été envoyés et vérifiés.")
            self.ui(messagebox.showinfo, "Transfert terminé", "Tous les fichiers ont été envoyés.")
        except TransferCancelled:
            self.log("Envoi annulé. Relancez le même fichier pour reprendre.")
        except Exception as exc:
            self.log(f"ÉCHEC ENVOI : {type(exc).__name__}: {exc}")
            self.ui(messagebox.showerror, "Échec de l'envoi", str(exc))
        finally:
            self.set_running(False)

    # ------------------------------------------------------------------
    # Exploration et téléchargement VPS -> Windows
    # ------------------------------------------------------------------
    def start_remote_refresh(self):
        if self.running:
            return
        if not self.validate_prerequisites(require_local_dir=True):
            return
        self.cancel_event.clear()
        self.set_running(True)
        self.ui(self.current_label.configure, text="Chargement de l'arborescence distante...")
        threading.Thread(target=self.load_remote_tree, daemon=True).start()

    def load_remote_tree(self):
        client = sftp = None
        try:
            client, sftp = self.connect()
            self.verify_remote_real_path(sftp, DOWNLOAD_REMOTE_ROOT)
            entries = self.collect_remote_entries(sftp, DOWNLOAD_REMOTE_ROOT)
            if self.cancel_event.is_set():
                raise TransferCancelled()
            self.ui(self.populate_remote_tree, entries)
            self.log(f"Arborescence chargée depuis {DOWNLOAD_REMOTE_ROOT}.")
            self.ui(self.current_label.configure, text="Arborescence distante chargée")
        except TransferCancelled:
            self.log("Chargement de l'arborescence annulé.")
        except Exception as exc:
            self.log(f"ÉCHEC LECTURE VPS : {type(exc).__name__}: {exc}")
            self.ui(messagebox.showerror, "Lecture du VPS impossible", str(exc))
        finally:
            self.close_connection(sftp, client)
            self.set_running(False)

    def collect_remote_entries(self, sftp, root_path: PurePosixPath):
        """Retourne une liste plate (chemin, dossier, taille), sans suivre les liens symboliques."""
        result = []
        stack = [root_path]
        while stack:
            if self.cancel_event.is_set():
                raise TransferCancelled()
            current = stack.pop()
            try:
                attrs = sorted(sftp.listdir_attr(str(current)), key=lambda a: a.filename.lower())
            except PermissionError:
                result.append((current / "[accès refusé]", False, -1, True))
                continue

            directories = []
            for attr in attrs:
                path = current / attr.filename
                mode = attr.st_mode
                if stat.S_ISLNK(mode):
                    result.append((path, False, attr.st_size, True))
                elif stat.S_ISDIR(mode):
                    result.append((path, True, 0, False))
                    directories.append(path)
                elif stat.S_ISREG(mode):
                    result.append((path, False, attr.st_size, False))
            stack.extend(reversed(directories))
        return result

    def populate_remote_tree(self, entries):
        self.remote_tree.delete(*self.remote_tree.get_children())
        self.remote_nodes.clear()

        root_id = self.remote_tree.insert(
            "", "end", text=str(DOWNLOAD_REMOTE_ROOT), values=("Dossier", ""), open=True
        )
        self.remote_nodes[DOWNLOAD_REMOTE_ROOT] = root_id

        for path, is_dir, size, unavailable in entries:
            parent_path = path.parent
            parent_id = self.remote_nodes.get(parent_path, root_id)
            if unavailable and path.name == "[accès refusé]":
                item_id = self.remote_tree.insert(
                    parent_id, "end", text=path.name, values=("Indisponible", "")
                )
                self.remote_tree.item(item_id, tags=("unavailable",))
                continue

            item_type = "Dossier" if is_dir else ("Lien ignoré" if unavailable else "Fichier")
            item_size = "" if is_dir else format_size(size)
            item_id = self.remote_tree.insert(
                parent_id, "end", text=path.name, values=(item_type, item_size), open=False
            )
            self.remote_nodes[path] = item_id
            self.remote_tree.set(item_id, "type", item_type)
            if unavailable:
                self.remote_tree.item(item_id, tags=("unavailable",))

        self.remote_tree.tag_configure("unavailable", foreground="#888888")
        self.remote_loaded = True
        self.on_remote_selection()

    def remote_path_for_item(self, item_id):
        for path, node_id in self.remote_nodes.items():
            if node_id == item_id:
                return path
        return None

    def selected_remote_files(self):
        if not hasattr(self, "remote_tree"):
            return []
        selected = []
        for item_id in self.remote_tree.selection():
            path = self.remote_path_for_item(item_id)
            if path is None or path == DOWNLOAD_REMOTE_ROOT:
                continue
            if self.remote_tree.set(item_id, "type") == "Fichier":
                selected.append(path)
        return selected

    def on_remote_selection(self, _event=None):
        if self.running:
            return
        state = "normal" if self.selected_remote_files() else "disabled"
        self.start_download_button.configure(state=state)

    def on_remote_double_click(self, event):
        item_id = self.remote_tree.identify_row(event.y)
        if not item_id:
            return
        item_type = self.remote_tree.set(item_id, "type")
        if item_type == "Dossier":
            self.remote_tree.item(item_id, open=not self.remote_tree.item(item_id, "open"))

    def start_download(self):
        if self.running:
            return
        remote_files = self.selected_remote_files()
        if not remote_files:
            messagebox.showwarning("Aucun fichier", "Sélectionnez au moins un fichier distant.")
            return
        if not self.validate_prerequisites(require_local_dir=True):
            return
        self.cancel_event.clear()
        self.current_progress.configure(value=0)
        self.total_progress.configure(value=0)
        self.set_running(True)
        threading.Thread(target=self.download_all, args=(remote_files,), daemon=True).start()

    def local_path_for_remote(self, remote_path: PurePosixPath) -> Path:
        relative = remote_path.relative_to(DOWNLOAD_REMOTE_ROOT)
        if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
            raise ValueError(f"Chemin distant invalide : {remote_path}")
        local_path = self.local_download_dir.joinpath(*relative.parts)
        local_root = self.local_download_dir.resolve()
        resolved_parent = local_path.parent.resolve()
        try:
            resolved_parent.relative_to(local_root)
        except ValueError as exc:
            raise PermissionError(f"Destination locale interdite : {local_path}") from exc
        return local_path

    def download_with_resume(self, remote_path, file_index, total_files):
        local_path = self.local_path_for_remote(remote_path)
        partial_path = local_path.with_name(local_path.name + ".part")
        local_path.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, MAX_RETRIES + 1):
            client = sftp = None
            try:
                if self.cancel_event.is_set():
                    raise TransferCancelled()
                self.log(f"Connexion au VPS, tentative {attempt}/{MAX_RETRIES}...")
                client, sftp = self.connect()
                self.verify_remote_real_path(sftp, remote_path)
                remote_attr = sftp.lstat(str(remote_path))
                if not stat.S_ISREG(remote_attr.st_mode):
                    raise ValueError(f"Le chemin distant n'est pas un fichier régulier : {remote_path}")
                remote_size = remote_attr.st_size
                local_partial_size = partial_path.stat().st_size if partial_path.exists() else 0
                if local_partial_size > remote_size:
                    partial_path.unlink()
                    local_partial_size = 0
                if local_partial_size:
                    self.log(
                        f"Reprise du téléchargement de {remote_path.name} à "
                        f"{format_size(local_partial_size)}."
                    )

                with sftp.file(str(remote_path), "rb") as source:
                    source.seek(local_partial_size)
                    mode = "ab" if local_partial_size else "wb"
                    with partial_path.open(mode) as target:
                        received = local_partial_size
                        while received < remote_size:
                            if self.cancel_event.is_set():
                                raise TransferCancelled()
                            data = source.read(CHUNK_SIZE)
                            if not data:
                                break
                            target.write(data)
                            received += len(data)
                            pct = received * 100 / remote_size if remote_size else 100
                            total_pct = ((file_index - 1) + pct / 100) * 100 / total_files
                            self.set_progress(
                                f"Téléchargement {file_index}/{total_files} : {remote_path.name} - "
                                f"{format_size(received)}/{format_size(remote_size)} ({pct:.1f} %)",
                                pct,
                                total_pct,
                            )
                        target.flush()
                        os.fsync(target.fileno())

                downloaded_size = partial_path.stat().st_size
                if downloaded_size != remote_size:
                    raise IOError(
                        f"Taille locale incorrecte : {downloaded_size} au lieu de {remote_size}"
                    )
                partial_path.replace(local_path)
                self.log(
                    f"OK téléchargement : {remote_path} -> {local_path} "
                    f"({format_size(remote_size)})"
                )
                return
            except TransferCancelled:
                raise
            except (OSError, EOFError, socket.error, paramiko.SSHException) as exc:
                self.log(f"Téléchargement interrompu : {exc}")
                if attempt >= MAX_RETRIES:
                    raise
                self.wait_before_retry()
            finally:
                self.close_connection(sftp, client)

    def download_all(self, remote_files):
        try:
            total = len(remote_files)
            for index, remote_path in enumerate(remote_files, start=1):
                self.download_with_resume(remote_path, index, total)
            self.set_progress("Téléchargement terminé", 100, 100)
            self.log(f"{total} fichier(s) téléchargé(s) et vérifié(s).")
            self.ui(
                messagebox.showinfo,
                "Téléchargement terminé",
                f"{total} fichier(s) téléchargé(s) dans :\n{self.local_download_dir}",
            )
        except TransferCancelled:
            self.log("Téléchargement annulé. Relancez le même fichier pour reprendre.")
        except Exception as exc:
            self.log(f"ÉCHEC TÉLÉCHARGEMENT : {type(exc).__name__}: {exc}")
            self.ui(messagebox.showerror, "Échec du téléchargement", str(exc))
        finally:
            self.set_running(False)

    # ------------------------------------------------------------------
    # Fermeture, attente et nettoyage
    # ------------------------------------------------------------------
    def wait_before_retry(self):
        self.log(
            f"Nouvelle tentative dans {RETRY_DELAY_SECONDS} secondes. "
            "Le transfert reprendra automatiquement."
        )
        for _ in range(RETRY_DELAY_SECONDS * 10):
            if self.cancel_event.is_set():
                raise TransferCancelled()
            time.sleep(0.1)

    @staticmethod
    def close_connection(sftp, client):
        if sftp:
            try:
                sftp.close()
            except Exception:
                pass
        if client:
            try:
                client.close()
            except Exception:
                pass

    def on_close(self):
        if self.running:
            if not messagebox.askyesno("Transfert en cours", "Annuler l'opération et fermer ?"):
                return
            self.cancel_event.set()
        self.root.destroy()


if __name__ == "__main__":
    app_root = tk.Tk()
    ScpTransferApp(app_root)
    app_root.mainloop()
