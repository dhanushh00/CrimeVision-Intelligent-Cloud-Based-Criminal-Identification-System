"""
CrimeVision - Advanced Intelligent Criminal Identification Desktop System
Features:
- Live AWS Rekognition & DynamoDB Biometric Search
- Real-Time Webcam Snapshot Capture
- Face Bounding Box & Confidence Overlay
- "Register Suspect" Direct Ingestion Modal
- Offline Demo / Simulation Mode
- Audit Log & CSV Export Utility
"""

import csv
import datetime
import io
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageFont, ImageTk

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Central Configuration
from config import (
    AWS_REGION,
    REKOGNITION_COLLECTION_ID,
    DYNAMODB_TABLE_NAME,
    S3_BUCKET_NAME,
    S3_PREFIX,
    MATCH_CONFIDENCE_THRESHOLD,
    APP_TITLE
)

# Optional OpenCV support for live webcam
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False


# ==============================================================================
# OFFLINE DEMO SIMULATION DATASET
# ==============================================================================
DEMO_DATABASE = [
    {
        "name": "John Doe",
        "crime": "Armed Robbery & Grand Theft",
        "status": "Wanted",
        "confidence": 98.65,
        "face_id": "c1f76e82-demo-4b92-8092-7f91823a01",
        "bbox": {"Width": 0.35, "Height": 0.45, "Left": 0.32, "Top": 0.22}
    },
    {
        "name": "David Beckham",
        "crime": "Match Fixing",
        "status": "Wanted",
        "confidence": 94.20,
        "face_id": "d8a19b33-demo-9c12-3310-99bb1284cc",
        "bbox": {"Width": 0.38, "Height": 0.48, "Left": 0.30, "Top": 0.20}
    },
    {
        "name": "Jane Smith",
        "crime": "Financial Wire Fraud",
        "status": "Not Wanted",
        "confidence": 91.80,
        "face_id": "f5e412aa-demo-7711-2290-aab8492011",
        "bbox": {"Width": 0.33, "Height": 0.42, "Left": 0.34, "Top": 0.25}
    },
    {
        "name": "Kiran Kumar",
        "crime": "Vehicle Theft",
        "status": "Wanted",
        "confidence": 96.40,
        "face_id": "k99211aa-demo-1100-3344-bb88776655",
        "bbox": {"Width": 0.36, "Height": 0.44, "Left": 0.31, "Top": 0.23}
    }
]


# ==============================================================================
# AUDIT LOGGER
# ==============================================================================
class AuditLogManager:
    """Manages scan history records and CSV report exports."""
    def __init__(self):
        self.logs = []

    def add_log(self, source, name, crime, status, confidence, face_id, mode="Cloud"):
        record = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": os.path.basename(source) if source else "Webcam",
            "name": name,
            "crime": crime,
            "status": status,
            "confidence": f"{confidence:.2f}%" if isinstance(confidence, (int, float)) else str(confidence),
            "face_id": face_id,
            "mode": mode
        }
        self.logs.insert(0, record)
        return record

    def export_csv(self, file_path):
        if not self.logs:
            return False
        keys = ["timestamp", "source", "name", "crime", "status", "confidence", "face_id", "mode"]
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(self.logs)
        return True


# ==============================================================================
# WEBCAM MODAL WINDOW
# ==============================================================================
class WebcamModal:
    """Live camera stream window with capture snapshot functionality."""
    def __init__(self, parent, on_capture_callback):
        self.parent = parent
        self.on_capture = on_capture_callback
        self.cap = None
        self.is_running = False

        if not OPENCV_AVAILABLE:
            messagebox.showerror("Webcam Error", "OpenCV (cv2) is not installed.\nInstall via: pip install opencv-python")
            return

        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            messagebox.showerror("Camera Unavailable", "Could not connect to webcam. Please verify camera permissions.")
            return

        self.win = tk.Toplevel(parent)
        self.win.title("📷 CrimeVision - Live Camera Capture")
        self.win.geometry("680x560")
        self.win.configure(bg="#0f172a")
        self.win.resizable(False, False)
        self.win.grab_set()

        # Header
        top_lbl = tk.Label(
            self.win,
            text="Position suspect's face inside frame and click 'Capture Snapshot'",
            font=("Segoe UI", 11, "bold"),
            fg="#38bdf8",
            bg="#0f172a"
        )
        top_lbl.pack(pady=10)

        # Video Canvas Frame
        self.video_frame = tk.Label(self.win, bg="black", width=640, height=440)
        self.video_frame.pack(padx=20, pady=5)

        # Controls
        ctrl_frame = tk.Frame(self.win, bg="#0f172a")
        ctrl_frame.pack(fill="x", pady=12, padx=20)

        self.snap_btn = tk.Button(
            ctrl_frame,
            text="📸 Capture Snapshot",
            font=("Segoe UI", 11, "bold"),
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            padx=20,
            pady=6,
            command=self.capture_frame
        )
        self.snap_btn.pack(side="left", expand=True, padx=10)

        cancel_btn = tk.Button(
            ctrl_frame,
            text="Cancel",
            font=("Segoe UI", 10),
            bg="#334155",
            fg="#cbd5e1",
            relief="flat",
            cursor="hand2",
            padx=15,
            pady=6,
            command=self.close
        )
        cancel_btn.pack(side="right", padx=10)

        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.is_running = True
        self.update_stream()

    def update_stream(self):
        if not self.is_running or self.cap is None:
            return

        ret, frame = self.cap.read()
        if ret:
            # Flip horizontally for mirror view
            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape

            # Draw target face frame guides (cyber surveillance aesthetic)
            box_w, box_h = int(w * 0.45), int(h * 0.65)
            x1, y1 = (w - box_w) // 2, (h - box_h) // 2
            x2, y2 = x1 + box_w, y1 + box_h
            cv2.rectangle(frame, (x1, y1), (x2, y2), (56, 189, 248), 2)
            cv2.putText(frame, "ALIGN FACE HERE", (x1 + 10, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (56, 189, 248), 2)

            cv2_img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(cv2_img)
            pil_img.thumbnail((640, 440))
            self.tk_img = ImageTk.PhotoImage(pil_img)
            self.video_frame.config(image=self.tk_img)

        self.win.after(30, self.update_stream)

    def capture_frame(self):
        if self.cap is not None:
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)
                self.close()
                self.on_capture(pil_img, "webcam_snapshot.jpg")

    def close(self):
        self.is_running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.win.destroy()


# ==============================================================================
# REGISTER CRIMINAL MODAL
# ==============================================================================
class RegisterCriminalModal:
    """Dialog to upload and register a new suspect directly to S3 + Rekognition."""
    def __init__(self, parent, is_demo_mode):
        self.parent = parent
        self.is_demo_mode = is_demo_mode
        self.selected_img_path = None
        self.pil_preview = None

        self.win = tk.Toplevel(parent)
        self.win.title("➕ Register New Suspect / Criminal")
        self.win.geometry("540x620")
        self.win.configure(bg="#0f172a")
        self.win.resizable(False, False)
        self.win.grab_set()

        # Header
        hdr = tk.Label(
            self.win,
            text="Register New Criminal Record",
            font=("Segoe UI", 14, "bold"),
            fg="#38bdf8",
            bg="#0f172a"
        )
        hdr.pack(pady=(15, 5))

        sub = tk.Label(
            self.win,
            text="Uploads mugshot to S3 and automatically triggers Lambda face indexing.",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#0f172a"
        )
        sub.pack(pady=(0, 15))

        # Photo Preview Box
        self.preview_lbl = tk.Label(
            self.win,
            text="Click 'Choose Photo' below",
            font=("Segoe UI", 9),
            fg="#64748b",
            bg="#1e293b",
            width=24,
            height=8,
            relief="solid",
            bd=1
        )
        self.preview_lbl.pack(pady=5)

        pick_btn = tk.Button(
            self.win,
            text="📁 Choose Mugshot Photo",
            font=("Segoe UI", 9, "bold"),
            bg="#334155",
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self.pick_photo
        )
        pick_btn.pack(pady=(4, 15))

        # Form Inputs Frame
        form_frame = tk.Frame(self.win, bg="#0f172a")
        form_frame.pack(fill="x", padx=40)

        # Full Name
        tk.Label(form_frame, text="Full Name:", font=("Segoe UI", 9, "bold"), fg="#cbd5e1", bg="#0f172a").pack(anchor="w")
        self.name_entry = tk.Entry(form_frame, font=("Segoe UI", 10), bg="#1e293b", fg="white", insertbackground="white")
        self.name_entry.pack(fill="x", pady=(2, 10))

        # Crime Category
        tk.Label(form_frame, text="Crime Category / Offense:", font=("Segoe UI", 9, "bold"), fg="#cbd5e1", bg="#0f172a").pack(anchor="w")
        self.crime_entry = tk.Entry(form_frame, font=("Segoe UI", 10), bg="#1e293b", fg="white", insertbackground="white")
        self.crime_entry.pack(fill="x", pady=(2, 10))

        # Wanted Status Dropdown
        tk.Label(form_frame, text="Wanted Status:", font=("Segoe UI", 9, "bold"), fg="#cbd5e1", bg="#0f172a").pack(anchor="w")
        self.status_var = tk.StringVar(value="Wanted")
        status_dropdown = ttk.Combobox(
            form_frame,
            textvariable=self.status_var,
            values=["Wanted", "Not Wanted", "Under Investigation"],
            state="readonly",
            font=("Segoe UI", 10)
        )
        status_dropdown.pack(fill="x", pady=(2, 18))

        # Submit Button
        self.submit_btn = tk.Button(
            self.win,
            text="🚀 Index & Save to Cloud",
            font=("Segoe UI", 11, "bold"),
            bg="#16a34a",
            fg="white",
            activebackground="#15803d",
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            padx=20,
            pady=8,
            command=self.submit_record
        )
        self.submit_btn.pack(pady=10)

    def pick_photo(self):
        f = filedialog.askopenfilename(title="Select Mugshot", filetypes=[("Image Files", "*.jpg *.jpeg *.png")])
        if f:
            self.selected_img_path = f
            img = Image.open(f)
            img.thumbnail((160, 160))
            self.tk_prev = ImageTk.PhotoImage(img)
            self.preview_lbl.config(image=self.tk_prev, text="")

    def submit_record(self):
        name = self.name_entry.get().strip()
        crime = self.crime_entry.get().strip()
        status = self.status_var.get().strip()

        if not self.selected_img_path:
            messagebox.showwarning("Missing Photo", "Please select a mugshot image.")
            return
        if not name or not crime:
            messagebox.showwarning("Missing Fields", "Please enter both Full Name and Crime Category.")
            return

        if self.is_demo_mode:
            # Add to local demo database
            DEMO_DATABASE.append({
                "name": name,
                "crime": crime,
                "status": status,
                "confidence": 99.00,
                "face_id": f"reg-{int(time.time())}-demo",
                "bbox": {"Width": 0.35, "Height": 0.45, "Left": 0.32, "Top": 0.22}
            })
            messagebox.showinfo("Success (Demo Mode)", f"Suspect '{name}' registered into local simulation database!")
            self.win.destroy()
            return

        # Cloud Mode: Upload to S3
        self.submit_btn.config(state="disabled", text="Uploading to S3...")
        filename = os.path.basename(self.selected_img_path)
        s3_key = f"{S3_PREFIX}{filename}"

        try:
            s3 = boto3.resource('s3', region_name=AWS_REGION)
            with open(self.selected_img_path, 'rb') as f:
                s3.Object(S3_BUCKET_NAME, s3_key).put(
                    Body=f,
                    Metadata={
                        'fullname': name,
                        'crime': crime,
                        'status': status
                    },
                    ContentType='image/jpeg'
                )
            messagebox.showinfo("Success", f"Uploaded '{filename}' to S3!\nLambda indexing triggered for '{name}'.")
            self.win.destroy()
        except Exception as e:
            messagebox.showerror("Upload Error", f"Failed to upload to S3:\n{str(e)}")
            self.submit_btn.config(state="normal", text="🚀 Index & Save to Cloud")


# ==============================================================================
# AUDIT LOG & REPORT VIEWER MODAL
# ==============================================================================
class AuditLogModal:
    """Displays scan history table with CSV export utility."""
    def __init__(self, parent, audit_manager):
        self.parent = parent
        self.audit_manager = audit_manager

        self.win = tk.Toplevel(parent)
        self.win.title("📜 CrimeVision - Biometric Audit & Scan History")
        self.win.geometry("820x480")
        self.win.configure(bg="#0f172a")
        self.win.grab_set()

        # Header Frame
        hdr_frame = tk.Frame(self.win, bg="#0f172a")
        hdr_frame.pack(fill="x", padx=20, pady=15)

        tk.Label(
            hdr_frame,
            text="Biometric Surveillance Audit Logs",
            font=("Segoe UI", 13, "bold"),
            fg="#38bdf8",
            bg="#0f172a"
        ).pack(side="left")

        export_btn = tk.Button(
            hdr_frame,
            text="💾 Export CSV Report",
            font=("Segoe UI", 9, "bold"),
            bg="#2563eb",
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=4,
            command=self.export_csv
        )
        export_btn.pack(side="right")

        # Table Treeview
        columns = ("Time", "Source", "Subject", "Crime", "Status", "Confidence", "Mode")
        self.tree = ttk.Treeview(self.win, columns=columns, show="headings", height=14)

        for col in columns:
            self.tree.heading(col, text=col)

        self.tree.column("Time", width=130)
        self.tree.column("Source", width=110)
        self.tree.column("Subject", width=140)
        self.tree.column("Crime", width=160)
        self.tree.column("Status", width=100)
        self.tree.column("Confidence", width=90)
        self.tree.column("Mode", width=60)

        # Style Treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#1e293b", foreground="#f8fafc", fieldbackground="#1e293b", rowheight=24)
        style.configure("Treeview.Heading", background="#334155", foreground="#38bdf8", font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[('selected', '#2563eb')])

        self.tree.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Populate Rows
        for item in self.audit_manager.logs:
            self.tree.insert("", "end", values=(
                item["timestamp"],
                item["source"],
                item["name"],
                item["crime"],
                item["status"],
                item["confidence"],
                item["mode"]
            ))

    def export_csv(self):
        f = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            initialfile="crimevision_audit_log.csv"
        )
        if f:
            if self.audit_manager.export_csv(f):
                messagebox.showinfo("Export Successful", f"Audit report saved to:\n{f}")
            else:
                messagebox.showwarning("Empty Log", "No scan records to export yet.")


# ==============================================================================
# MAIN CRIMEVISION APPLICATION
# ==============================================================================
class CrimeVisionApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("920x760")
        self.root.minsize(860, 700)
        self.root.configure(bg="#0f172a")

        # State
        self.is_demo_mode = False
        self.current_image_path = None
        self.current_pil_image = None
        self.display_pil_image = None
        self.photo_img_ref = None
        self.audit_manager = AuditLogManager()

        # AWS Clients
        self.rekognition = None
        self.dynamodb = None
        self.init_aws_clients()

        self.setup_ui()

    def init_aws_clients(self):
        """Initializes boto3 AWS clients or falls back to demo mode gracefully."""
        try:
            self.rekognition = boto3.client('rekognition', region_name=AWS_REGION)
            self.dynamodb = boto3.client('dynamodb', region_name=AWS_REGION)
        except Exception:
            self.is_demo_mode = True

    def setup_ui(self):
        # ---------------- Top Navigation Header ----------------
        header_frame = tk.Frame(self.root, bg="#1e293b", height=70)
        header_frame.pack(fill="x", side="top")

        title_label = tk.Label(
            header_frame,
            text="🕵️ CrimeVision",
            font=("Segoe UI", 18, "bold"),
            fg="#38bdf8",
            bg="#1e293b"
        )
        title_label.pack(side="left", padx=(20, 8), pady=15)

        subtitle_label = tk.Label(
            header_frame,
            text="Biometric Surveillance",
            font=("Segoe UI", 10),
            fg="#94a3b8",
            bg="#1e293b"
        )
        subtitle_label.pack(side="left", pady=18)

        # Action Buttons in Header
        btn_container = tk.Frame(header_frame, bg="#1e293b")
        btn_container.pack(side="right", padx=20, pady=12)

        self.mode_btn = tk.Button(
            btn_container,
            text="⚡ Mode: Cloud (AWS)" if not self.is_demo_mode else "🧪 Mode: Demo (Offline)",
            font=("Segoe UI", 8, "bold"),
            bg="#0284c7" if not self.is_demo_mode else "#d97706",
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=self.toggle_mode
        )
        self.mode_btn.pack(side="left", padx=4)

        reg_btn = tk.Button(
            btn_container,
            text="➕ Register Suspect",
            font=("Segoe UI", 8, "bold"),
            bg="#16a34a",
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=lambda: RegisterCriminalModal(self.root, self.is_demo_mode)
        )
        reg_btn.pack(side="left", padx=4)

        audit_btn = tk.Button(
            btn_container,
            text="📜 Audit Logs",
            font=("Segoe UI", 8, "bold"),
            bg="#475569",
            fg="white",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=4,
            command=lambda: AuditLogModal(self.root, self.audit_manager)
        )
        audit_btn.pack(side="left", padx=4)

        # ---------------- Main Body Layout ----------------
        main_container = tk.Frame(self.root, bg="#0f172a")
        main_container.pack(fill="both", expand=True, padx=20, pady=15)

        # Left Column: Image Viewer & Inputs
        left_col = tk.Frame(main_container, bg="#1e293b", padx=18, pady=16, width=420)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Right Column: Criminal Profile & Biometric Cards
        right_col = tk.Frame(main_container, bg="#1e293b", padx=18, pady=16, width=440)
        right_col.pack(side="right", fill="both", expand=True, padx=(10, 0))

        # ---- Left Column ----
        left_title = tk.Label(
            left_col,
            text="SUSPECT FEED / IMAGE SCANNER",
            font=("Segoe UI", 11, "bold"),
            fg="#f8fafc",
            bg="#1e293b"
        )
        left_title.pack(anchor="w", pady=(0, 8))

        # Canvas Frame (360x360)
        self.img_frame = tk.Frame(left_col, bg="#0f172a", width=360, height=360, relief="solid", bd=1)
        self.img_frame.pack_propagate(False)
        self.img_frame.pack(pady=5)

        self.img_label = tk.Label(
            self.img_frame,
            text="No Suspect Photo Loaded\n\nChoose 'Select Image' or 'Live Webcam'",
            font=("Segoe UI", 10),
            fg="#64748b",
            bg="#0f172a"
        )
        self.img_label.pack(expand=True, fill="both")

        # Ingestion Buttons
        btn_grid = tk.Frame(left_col, bg="#1e293b")
        btn_grid.pack(fill="x", pady=(12, 0))

        self.btn_select = tk.Button(
            btn_grid,
            text="📁 Select Image",
            font=("Segoe UI", 9, "bold"),
            bg="#334155",
            fg="white",
            activebackground="#475569",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=7,
            command=self.select_image
        )
        self.btn_select.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.btn_cam = tk.Button(
            btn_grid,
            text="📷 Live Webcam",
            font=("Segoe UI", 9, "bold"),
            bg="#475569",
            fg="white",
            activebackground="#64748b",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=7,
            command=self.open_webcam
        )
        self.btn_cam.pack(side="left", fill="x", expand=True, padx=(3, 3))

        self.btn_identify = tk.Button(
            btn_grid,
            text="🔍 Scan & Identify",
            font=("Segoe UI", 9, "bold"),
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=7,
            command=self.start_identification_thread
        )
        self.btn_identify.pack(side="left", fill="x", expand=True, padx=(3, 0))

        # Status Line
        self.status_var = tk.StringVar(value="Ready. Load an image or capture from webcam to scan.")
        self.status_lbl = tk.Label(
            left_col,
            textvariable=self.status_var,
            font=("Segoe UI", 9, "italic"),
            fg="#94a3b8",
            bg="#1e293b",
            wraplength=360,
            justify="center"
        )
        self.status_lbl.pack(pady=(10, 0))

        # ---- Right Column Content ----
        right_title = tk.Label(
            right_col,
            text="BIOMETRIC IDENTIFICATION RESULTS",
            font=("Segoe UI", 11, "bold"),
            fg="#f8fafc",
            bg="#1e293b"
        )
        right_title.pack(anchor="w", pady=(0, 8))

        self.card_frame = tk.Frame(right_col, bg="#0f172a", padx=16, pady=16, relief="solid", bd=1)
        self.card_frame.pack(fill="both", expand=True)

        # Match Status Banner
        self.match_badge = tk.Label(
            self.card_frame,
            text="AWAITING BIOMETRIC SCAN",
            font=("Segoe UI", 11, "bold"),
            bg="#334155",
            fg="#cbd5e1",
            padx=12,
            pady=8
        )
        self.match_badge.pack(fill="x", pady=(0, 14))

        # Profile Fields
        self.field_name = self.create_profile_row(self.card_frame, "Full Name:", "—")
        self.field_crime = self.create_profile_row(self.card_frame, "Offense / Crime:", "—")
        self.field_status = self.create_profile_row(self.card_frame, "Wanted Status:", "—")
        self.field_confidence = self.create_profile_row(self.card_frame, "Confidence:", "—")
        self.field_faceid = self.create_profile_row(self.card_frame, "Rekognition ID:", "—")

        # Confidence Progress Bar
        bar_frame = tk.Frame(self.card_frame, bg="#0f172a")
        bar_frame.pack(fill="x", pady=(10, 0))
        tk.Label(bar_frame, text="Match Score:", font=("Segoe UI", 8, "bold"), fg="#94a3b8", bg="#0f172a").pack(anchor="w")
        self.confidence_bar = ttk.Progressbar(bar_frame, orient="horizontal", length=200, mode="determinate")
        self.confidence_bar.pack(fill="x", pady=(3, 0))

        # Footnote
        self.info_label = tk.Label(
            right_col,
            text=f"Collection: {REKOGNITION_COLLECTION_ID} | Table: {DYNAMODB_TABLE_NAME}",
            font=("Segoe UI", 8),
            fg="#64748b",
            bg="#1e293b"
        )
        self.info_label.pack(side="bottom", pady=(8, 0))

    def create_profile_row(self, parent, label_text, default_val):
        row = tk.Frame(parent, bg="#0f172a")
        row.pack(fill="x", pady=5)

        lbl = tk.Label(row, text=label_text, font=("Segoe UI", 9, "bold"), fg="#94a3b8", bg="#0f172a", width=14, anchor="w")
        lbl.pack(side="left")

        val_var = tk.StringVar(value=default_val)
        val_lbl = tk.Label(row, textvariable=val_var, font=("Segoe UI", 10), fg="#f8fafc", bg="#0f172a", anchor="w", wraplength=230)
        val_lbl.pack(side="left", fill="x", expand=True)

        return val_var

    def toggle_mode(self):
        """Switches between Cloud Mode (AWS) and Demo Mode (Offline Simulation)."""
        self.is_demo_mode = not self.is_demo_mode
        if self.is_demo_mode:
            self.mode_btn.config(text="🧪 Mode: Demo (Offline)", bg="#d97706")
            self.info_label.config(text="Offline Simulation Mode Active (Built-in Vector DB)")
            self.status_var.set("Switched to Offline Demo Mode.")
        else:
            self.mode_btn.config(text="⚡ Mode: Cloud (AWS)", bg="#0284c7")
            self.info_label.config(text=f"Collection: {REKOGNITION_COLLECTION_ID} | Table: {DYNAMODB_TABLE_NAME}")
            self.status_var.set("Switched to AWS Cloud Mode.")

    def select_image(self):
        types = [("Image files", "*.jpg *.jpeg *.png *.bmp *.webp"), ("All files", "*.*")]
        selected = filedialog.askopenfilename(title="Select Suspect Image", filetypes=types)
        if selected:
            self.load_image_from_path(selected)

    def open_webcam(self):
        WebcamModal(self.root, self.load_image_from_pil)

    def load_image_from_path(self, path):
        try:
            self.current_image_path = path
            self.current_pil_image = Image.open(path)
            self.render_preview(self.current_pil_image)
            self.status_var.set(f"Loaded: {os.path.basename(path)}")
            self.reset_results()
        except Exception as e:
            messagebox.showerror("Error", f"Could not load image:\n{e}")

    def load_image_from_pil(self, pil_img, name="webcam_capture.jpg"):
        self.current_image_path = name
        self.current_pil_image = pil_img
        self.render_preview(self.current_pil_image)
        self.status_var.set("Captured frame from live webcam.")
        self.reset_results()

    def render_preview(self, pil_img, bounding_box=None, box_color="#10b981", box_label=None):
        """Draws image and optional bounding box overlay."""
        img_copy = pil_img.copy().convert("RGB")
        w, h = img_copy.size

        # Draw bounding box if coordinates are provided
        if bounding_box:
            draw = ImageDraw.Draw(img_copy)
            left = int(bounding_box.get('Left', 0) * w)
            top = int(bounding_box.get('Top', 0) * h)
            width = int(bounding_box.get('Width', 0) * w)
            height = int(bounding_box.get('Height', 0) * h)

            draw.rectangle([left, top, left + width, top + height], outline=box_color, width=4)

            if box_label:
                # Label banner above box
                draw.rectangle([left, max(0, top - 24), left + width, top], fill=box_color)
                draw.text((left + 6, max(0, top - 20)), box_label, fill="white")

        img_copy.thumbnail((350, 350))
        self.photo_img_ref = ImageTk.PhotoImage(img_copy)
        self.img_label.config(image=self.photo_img_ref, text="")

    def reset_results(self):
        self.match_badge.config(text="READY TO SCAN", bg="#334155", fg="#cbd5e1")
        self.field_name.set("—")
        self.field_crime.set("—")
        self.field_status.set("—")
        self.field_confidence.set("—")
        self.field_faceid.set("—")
        self.confidence_bar['value'] = 0

    def start_identification_thread(self):
        if not self.current_pil_image:
            if os.path.exists("image.png"):
                self.load_image_from_path("image.png")
            elif os.path.exists("1.jpg"):
                self.load_image_from_path("1.jpg")
            else:
                messagebox.showwarning("No Image", "Please select or capture a suspect image first.")
                return

        self.btn_identify.config(state="disabled", text="Scanning...")
        self.btn_select.config(state="disabled")
        self.btn_cam.config(state="disabled")
        self.status_var.set("Analyzing facial landmarks & querying database...")
        self.match_badge.config(text="SCANNING BIOMETRICS...", bg="#d97706", fg="white")

        threading.Thread(target=self.run_face_identification, daemon=True).start()

    def run_face_identification(self):
        """Executes matching in Cloud or Demo Mode."""
        try:
            if self.is_demo_mode:
                time.sleep(0.8)  # Simulated processing latency
                # Pick a demo match or randomize based on image name
                match_data = DEMO_DATABASE[0]
                if self.current_image_path and "jane" in self.current_image_path.lower():
                    match_data = DEMO_DATABASE[2]

                self.root.after(
                    0,
                    self.display_match_found,
                    match_data["name"],
                    match_data["crime"],
                    match_data["status"],
                    match_data["confidence"],
                    match_data["face_id"],
                    match_data["bbox"],
                    "Demo"
                )
                return

            # Cloud Mode
            stream = io.BytesIO()
            pil_to_save = self.current_pil_image
            if pil_to_save.mode in ("RGBA", "P"):
                pil_to_save = pil_to_save.convert("RGB")
            pil_to_save.save(stream, format="JPEG")
            image_binary = stream.getvalue()

            response = self.rekognition.search_faces_by_image(
                CollectionId=REKOGNITION_COLLECTION_ID,
                Image={'Bytes': image_binary},
                FaceMatchThreshold=MATCH_CONFIDENCE_THRESHOLD,
                MaxFaces=1
            )

            face_matches = response.get('FaceMatches', [])
            searched_bbox = response.get('SearchedFaceBoundingBox')

            if face_matches:
                match = face_matches[0]
                face_id = match['Face']['FaceId']
                confidence = match['Face']['Confidence']

                face_record = self.dynamodb.get_item(
                    TableName=DYNAMODB_TABLE_NAME,
                    Key={'RekognitionId': {'S': face_id}}
                )

                item = face_record.get('Item')
                if item:
                    name = item.get('FullName', {}).get('S', 'Unknown')
                    crime = item.get('CrimeType', {}).get('S', 'Unknown')
                    status = item.get('WantedStatus', {}).get('S', 'Unknown')

                    self.root.after(0, self.display_match_found, name, crime, status, confidence, face_id, searched_bbox, "Cloud")
                else:
                    self.root.after(0, self.display_unindexed_match, face_id, confidence, searched_bbox)
            else:
                self.root.after(0, self.display_no_match)

        except (NoCredentialsError, ClientError) as e:
            # Fallback suggestion to Demo mode
            err_msg = str(e)
            self.root.after(0, self.display_error, f"Cloud Error: {err_msg}\n\nTip: Click 'Mode' at the top to test with Offline Demo Mode.")
        except Exception as e:
            self.root.after(0, self.display_error, str(e))
        finally:
            self.root.after(0, self.enable_buttons)

    def display_match_found(self, name, crime, status, confidence, face_id, bbox=None, mode="Cloud"):
        is_wanted = status.strip().lower() == "wanted"
        badge_bg = "#dc2626" if is_wanted else "#16a34a"
        badge_text = f"🚨 MATCH IDENTIFIED ({status.upper()})" if is_wanted else f"✓ RECORD FOUND ({status.upper()})"

        self.match_badge.config(text=badge_text, bg=badge_bg, fg="white")
        self.field_name.set(name)
        self.field_crime.set(crime)
        self.field_status.set(status)
        self.field_confidence.set(f"{confidence:.2f}%")
        self.field_faceid.set(face_id)
        self.confidence_bar['value'] = confidence

        # Overlay bounding box
        box_color = "#dc2626" if is_wanted else "#16a34a"
        lbl = f"{name} ({confidence:.0f}%)"
        self.render_preview(self.current_pil_image, bounding_box=bbox, box_color=box_color, box_label=lbl)

        self.status_var.set(f"Subject Identified: {name} (Confidence: {confidence:.2f}%)")

        # Save to Audit Log
        self.audit_manager.add_log(self.current_image_path, name, crime, status, confidence, face_id, mode)

    def display_unindexed_match(self, face_id, confidence, bbox=None):
        self.match_badge.config(text="⚠️ FACE MATCHED (NO DB METADATA)", bg="#ea580c", fg="white")
        self.field_name.set("Unknown Record")
        self.field_crime.set("Unassigned")
        self.field_status.set("Pending Review")
        self.field_confidence.set(f"{confidence:.2f}%")
        self.field_faceid.set(face_id)
        self.confidence_bar['value'] = confidence
        self.render_preview(self.current_pil_image, bounding_box=bbox, box_color="#ea580c", box_label=f"FaceId: {face_id[:8]}")
        self.status_var.set("Face matched in Rekognition, but no record found in DynamoDB.")
        self.audit_manager.add_log(self.current_image_path, "Unknown", "Unassigned", "Pending Review", confidence, face_id, "Cloud")

    def display_no_match(self):
        self.match_badge.config(text="✗ NO MATCH FOUND", bg="#475569", fg="#f1f5f9")
        self.field_name.set("No match found")
        self.field_crime.set("—")
        self.field_status.set("Not in Database")
        self.field_confidence.set("0.00%")
        self.field_faceid.set("—")
        self.confidence_bar['value'] = 0
        self.render_preview(self.current_pil_image)
        self.status_var.set("Biometric scan completed. No match found in collection.")
        self.audit_manager.add_log(self.current_image_path, "No Match", "—", "Clean", 0.0, "None", "Cloud" if not self.is_demo_mode else "Demo")

    def display_error(self, err_msg):
        self.match_badge.config(text="⚠️ SCAN ERROR", bg="#991b1b", fg="white")
        self.status_var.set("An error occurred during facial scan.")
        messagebox.showerror("Biometric Error", err_msg)

    def enable_buttons(self):
        self.btn_identify.config(state="normal", text="🔍 Scan & Identify")
        self.btn_select.config(state="normal")
        self.btn_cam.config(state="normal")


def main():
    root = tk.Tk()
    app = CrimeVisionApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
