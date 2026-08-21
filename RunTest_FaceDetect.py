"""
CrimeVision - Intelligent Criminal Identification System GUI
Modern desktop application to upload/inspect suspect photos, query Amazon Rekognition,
and retrieve matching criminal records from DynamoDB with real-time UI status updates.
"""

import io
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Configuration
from config import (
    AWS_REGION,
    REKOGNITION_COLLECTION_ID,
    DYNAMODB_TABLE_NAME,
    MATCH_CONFIDENCE_THRESHOLD,
    APP_TITLE
)

class CrimeVisionApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("880x740")
        self.root.minsize(800, 680)
        self.root.configure(bg="#0f172a")  # Slate-900 dark background

        # AWS Clients
        self.rekognition = None
        self.dynamodb = None
        self.init_aws_clients()

        # State Variables
        self.current_image_path = None
        self.current_pil_image = None
        self.photo_img_ref = None

        self.setup_ui()

    def init_aws_clients(self):
        """Initializes boto3 AWS clients."""
        try:
            self.rekognition = boto3.client('rekognition', region_name=AWS_REGION)
            self.dynamodb = boto3.client('dynamodb', region_name=AWS_REGION)
        except Exception as e:
            print(f"Warning: Could not initialize AWS clients: {e}")

    def setup_ui(self):
        # ---------------- Top Header Bar ----------------
        header_frame = tk.Frame(self.root, bg="#1e293b", height=70)
        header_frame.pack(fill="x", side="top")

        title_label = tk.Label(
            header_frame,
            text="🕵️ CrimeVision",
            font=("Segoe UI", 20, "bold"),
            fg="#38bdf8",  # Sky-400
            bg="#1e293b"
        )
        title_label.pack(side="left", padx=25, pady=15)

        subtitle_label = tk.Label(
            header_frame,
            text="Intelligent Cloud-Based Criminal Identification System",
            font=("Segoe UI", 11),
            fg="#94a3b8",  # Slate-400
            bg="#1e293b"
        )
        subtitle_label.pack(side="left", pady=18)

        region_badge = tk.Label(
            header_frame,
            text=f"AWS Region: {AWS_REGION}",
            font=("Segoe UI", 9, "bold"),
            fg="#38bdf8",
            bg="#0f172a",
            padx=10,
            pady=4
        )
        region_badge.pack(side="right", padx=25, pady=18)

        # ---------------- Main Body Layout ----------------
        main_container = tk.Frame(self.root, bg="#0f172a")
        main_container.pack(fill="both", expand=True, padx=25, pady=20)

        # Left Column: Image Viewer & Action Buttons
        left_col = tk.Frame(main_container, bg="#1e293b", padx=20, pady=20, width=400)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 12))

        # Right Column: Criminal Profile & Match Results
        right_col = tk.Frame(main_container, bg="#1e293b", padx=20, pady=20, width=440)
        right_col.pack(side="right", fill="both", expand=True, padx=(12, 0))

        # ---- Left Column Content ----
        left_title = tk.Label(
            left_col,
            text="SUSPECT IMAGE",
            font=("Segoe UI", 12, "bold"),
            fg="#f8fafc",
            bg="#1e293b"
        )
        left_title.pack(anchor="w", pady=(0, 10))

        # Image Canvas Frame
        self.img_frame = tk.Frame(left_col, bg="#0f172a", width=340, height=340, relief="solid", bd=1)
        self.img_frame.pack_propagate(False)
        self.img_frame.pack(pady=10)

        self.img_label = tk.Label(
            self.img_frame,
            text="No Suspect Image Loaded\n\nClick 'Select Image' below",
            font=("Segoe UI", 10),
            fg="#64748b",
            bg="#0f172a"
        )
        self.img_label.pack(expand=True, fill="both")

        # Buttons Frame
        btn_frame = tk.Frame(left_col, bg="#1e293b")
        btn_frame.pack(fill="x", pady=(15, 0))

        self.btn_select = tk.Button(
            btn_frame,
            text="📁 Select Image",
            font=("Segoe UI", 10, "bold"),
            bg="#334155",
            fg="white",
            activebackground="#475569",
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            padx=15,
            pady=8,
            command=self.select_image
        )
        self.btn_select.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_identify = tk.Button(
            btn_frame,
            text="🔍 Scan & Identify",
            font=("Segoe UI", 10, "bold"),
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            padx=15,
            pady=8,
            command=self.start_identification_thread
        )
        self.btn_identify.pack(side="right", fill="x", expand=True, padx=(5, 0))

        # Status Label below buttons
        self.status_var = tk.StringVar(value="Ready. Load an image to start.")
        self.status_lbl = tk.Label(
            left_col,
            textvariable=self.status_var,
            font=("Segoe UI", 9, "italic"),
            fg="#94a3b8",
            bg="#1e293b",
            wraplength=340,
            justify="center"
        )
        self.status_lbl.pack(pady=(12, 0))

        # ---- Right Column Content (Results Dashboard) ----
        right_title = tk.Label(
            right_col,
            text="IDENTIFICATION RESULTS",
            font=("Segoe UI", 12, "bold"),
            fg="#f8fafc",
            bg="#1e293b"
        )
        right_title.pack(anchor="w", pady=(0, 10))

        # Card Frame
        self.card_frame = tk.Frame(right_col, bg="#0f172a", padx=18, pady=18, relief="solid", bd=1)
        self.card_frame.pack(fill="both", expand=True)

        # Match Status Banner
        self.match_badge = tk.Label(
            self.card_frame,
            text="WAITING FOR SCAN",
            font=("Segoe UI", 11, "bold"),
            bg="#334155",
            fg="#cbd5e1",
            padx=12,
            pady=6
        )
        self.match_badge.pack(fill="x", pady=(0, 15))

        # Profile Fields
        self.field_name = self.create_profile_row(self.card_frame, "Full Name:", "—")
        self.field_crime = self.create_profile_row(self.card_frame, "Crime Category:", "—")
        self.field_status = self.create_profile_row(self.card_frame, "Wanted Status:", "—")
        self.field_confidence = self.create_profile_row(self.card_frame, "Confidence:", "—")
        self.field_faceid = self.create_profile_row(self.card_frame, "Rekognition ID:", "—")

        # Collection Info Footnote
        info_label = tk.Label(
            right_col,
            text=f"Collection: {REKOGNITION_COLLECTION_ID}  |  Table: {DYNAMODB_TABLE_NAME}",
            font=("Segoe UI", 8),
            fg="#64748b",
            bg="#1e293b"
        )
        info_label.pack(side="bottom", pady=(10, 0))

    def create_profile_row(self, parent, label_text, default_val):
        row = tk.Frame(parent, bg="#0f172a")
        row.pack(fill="x", pady=6)

        lbl = tk.Label(row, text=label_text, font=("Segoe UI", 9, "bold"), fg="#94a3b8", bg="#0f172a", width=14, anchor="w")
        lbl.pack(side="left")

        val_var = tk.StringVar(value=default_val)
        val_lbl = tk.Label(row, textvariable=val_var, font=("Segoe UI", 10), fg="#f8fafc", bg="#0f172a", anchor="w", wraplength=230)
        val_lbl.pack(side="left", fill="x", expand=True)

        return val_var

    def select_image(self):
        """Opens file dialog to choose a suspect image."""
        file_types = [("Image files", "*.jpg *.jpeg *.png *.bmp *.webp"), ("All files", "*.*")]
        selected = filedialog.askopenfilename(title="Select Suspect Photo", filetypes=file_types)
        if selected:
            self.load_image(selected)

    def load_image(self, file_path):
        """Loads and displays image in the GUI."""
        try:
            self.current_image_path = file_path
            self.current_pil_image = Image.open(file_path)

            # Resize to fit display maintaining aspect ratio
            display_img = self.current_pil_image.copy()
            display_img.thumbnail((330, 330))

            self.photo_img_ref = ImageTk.PhotoImage(display_img)
            self.img_label.config(image=self.photo_img_ref, text="")
            self.status_var.set(f"Loaded: {os.path.basename(file_path)}")
            self.reset_results()
        except Exception as e:
            messagebox.showerror("Image Load Error", f"Could not load image:\n{e}")

    def reset_results(self):
        """Resets the dashboard result fields."""
        self.match_badge.config(text="READY TO SCAN", bg="#334155", fg="#cbd5e1")
        self.field_name.set("—")
        self.field_crime.set("—")
        self.field_status.set("—")
        self.field_confidence.set("—")
        self.field_faceid.set("—")

    def start_identification_thread(self):
        """Runs the AWS search in a background thread to prevent UI freezing."""
        if not self.current_pil_image:
            # Check if default sample image exists
            if os.path.exists("criminal.jpg"):
                self.load_image("criminal.jpg")
            elif os.path.exists("1.jpg"):
                self.load_image("1.jpg")
            else:
                messagebox.showwarning("No Image Selected", "Please select a suspect image first.")
                return

        self.btn_identify.config(state="disabled", text="Scanning...")
        self.btn_select.config(state="disabled")
        self.status_var.set("Connecting to AWS Rekognition...")
        self.match_badge.config(text="SCANNING FACIAL DATABASE...", bg="#d97706", fg="white")

        threading.Thread(target=self.run_face_identification, daemon=True).start()

    def run_face_identification(self):
        """Performs Rekognition face search and DynamoDB lookup."""
        try:
            # Convert image to bytes
            stream = io.BytesIO()
            # Convert RGBA to RGB if needed
            pil_to_save = self.current_pil_image
            if pil_to_save.mode in ("RGBA", "P"):
                pil_to_save = pil_to_save.convert("RGB")
            pil_to_save.save(stream, format="JPEG")
            image_binary = stream.getvalue()

            # Search in Amazon Rekognition
            response = self.rekognition.search_faces_by_image(
                CollectionId=REKOGNITION_COLLECTION_ID,
                Image={'Bytes': image_binary},
                FaceMatchThreshold=MATCH_CONFIDENCE_THRESHOLD,
                MaxFaces=1
            )

            face_matches = response.get('FaceMatches', [])

            if face_matches:
                match = face_matches[0]
                face_id = match['Face']['FaceId']
                confidence = match['Face']['Confidence']

                # Query DynamoDB for metadata
                face_record = self.dynamodb.get_item(
                    TableName=DYNAMODB_TABLE_NAME,
                    Key={'RekognitionId': {'S': face_id}}
                )

                item = face_record.get('Item')
                if item:
                    person_name = item.get('FullName', {}).get('S', 'Unknown')
                    crime_type = item.get('CrimeType', {}).get('S', 'Unknown')
                    wanted_status = item.get('WantedStatus', {}).get('S', 'Unknown')

                    self.root.after(0, self.display_match_found, person_name, crime_type, wanted_status, confidence, face_id)
                else:
                    self.root.after(0, self.display_unindexed_match, face_id, confidence)
            else:
                self.root.after(0, self.display_no_match)

        except NoCredentialsError:
            self.root.after(0, self.display_error, "AWS Credentials not configured!\nRun 'aws configure' or check your .env file.")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_msg = e.response['Error']['Message']
            self.root.after(0, self.display_error, f"AWS Error ({error_code}):\n{error_msg}")
        except Exception as e:
            self.root.after(0, self.display_error, str(e))
        finally:
            self.root.after(0, self.enable_buttons)

    def display_match_found(self, name, crime, status, confidence, face_id):
        is_wanted = status.strip().lower() == "wanted"
        badge_bg = "#dc2626" if is_wanted else "#16a34a"  # Red for wanted, Green for clear/not wanted
        badge_text = f"🚨 MATCH IDENTIFIED ({status.upper()})" if is_wanted else f"✓ MATCH IDENTIFIED ({status.upper()})"

        self.match_badge.config(text=badge_text, bg=badge_bg, fg="white")
        self.field_name.set(name)
        self.field_crime.set(crime)
        self.field_status.set(status)
        self.field_confidence.set(f"{confidence:.2f}%")
        self.field_faceid.set(face_id)
        self.status_var.set(f"Subject successfully identified: {name}")

    def display_unindexed_match(self, face_id, confidence):
        self.match_badge.config(text="⚠️ FACE MATCHED (NO DB RECORD)", bg="#ea580c", fg="white")
        self.field_name.set("Unknown Record")
        self.field_crime.set("Not Documented")
        self.field_status.set("Pending Review")
        self.field_confidence.set(f"{confidence:.2f}%")
        self.field_faceid.set(face_id)
        self.status_var.set("Face matched in Rekognition collection, but record missing from DynamoDB.")

    def display_no_match(self):
        self.match_badge.config(text="✗ NO MATCH FOUND", bg="#475569", fg="#f1f5f9")
        self.field_name.set("No match found")
        self.field_crime.set("—")
        self.field_status.set("Not in Database")
        self.field_confidence.set("0.00%")
        self.field_faceid.set("—")
        self.status_var.set("No matching criminal records identified in the collection.")

    def display_error(self, err_msg):
        self.match_badge.config(text="⚠️ ERROR DETECTED", bg="#991b1b", fg="white")
        self.status_var.set("An error occurred during facial scan.")
        messagebox.showerror("Identification Error", err_msg)

    def enable_buttons(self):
        self.btn_identify.config(state="normal", text="🔍 Scan & Identify")
        self.btn_select.config(state="normal")


def main():
    root = tk.Tk()
    app = CrimeVisionApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
