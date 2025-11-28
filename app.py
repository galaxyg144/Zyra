from flask import Flask, jsonify, send_file, request, render_template
from b2sdk.v1 import InMemoryAccountInfo, B2Api, DownloadDestBytes
import io
import os
import time
import platform
import random
import string
from datetime import datetime

app = Flask(__name__)

# === B2 Configuration ===
B2_KEY_ID = os.environ.get("B2_KEY_ID")       # Your KeyID
B2_APP_KEY = os.environ.get("B2_APP_KEY")     # Your Application Key
BUCKET_NAME = os.environ.get("BUCKET_NAME")   # Your bucket name

if not all([B2_KEY_ID, B2_APP_KEY, BUCKET_NAME]):
    raise ValueError("Please set B2_KEY_ID, B2_APP_KEY, and BUCKET_NAME as environment variables.")

# === Connect to B2 ===
info = InMemoryAccountInfo()
b2_api = B2Api(info)
b2_api.authorize_account("production", B2_KEY_ID, B2_APP_KEY)
bucket = b2_api.get_bucket_by_name(BUCKET_NAME)

# === Helper Functions ===
def file_exists(filename):
    """Check if a file already exists in the bucket"""
    try:
        for item, _ in bucket.ls():
            if item.file_name == filename:
                return True
        return False
    except Exception as e:
        print(f"Error checking file existence: {e}")
        return False

def gshift(filename):
    """
    Generate a unique filename by appending random alphanumeric characters.
    Example: test.txt -> test-q.txt -> test-q5.txt -> test-q5a.txt
    """
    if "." in filename:
        name, ext = filename.rsplit(".", 1)
        ext = "." + ext
    else:
        name = filename
        ext = ""
    
    current_name = filename
    
    while file_exists(current_name):
        random_char = random.choice(string.ascii_lowercase + string.digits)
        if "-" in name:
            name += random_char
        else:
            name += f"-{random_char}"
        current_name = name + ext
        print(f"Collision detected, trying: {current_name}")
    
    return current_name

# === Routes ===

@app.route("/", methods=["GET"])
def dashboard():
    return render_template("dashboard.html")

@app.route("/apps", methods=["GET"])
def list_apps():
    try:
        files = [item.file_name for item, _ in bucket.ls()]
        return jsonify(files)
    except Exception as e:
        print(f"Error listing apps: {e}")
        return jsonify({"error": "Could not list files"}), 500

@app.route("/apps/<filename>", methods=["GET"])
def get_app(filename):
    try:
        download_dest = DownloadDestBytes()
        bucket.download_file_by_name(filename, download_dest)
        data = download_dest.bytes_written
        return send_file(
            io.BytesIO(data),
            as_attachment=True,
            download_name=filename,
            mimetype="application/octet-stream"
        )
    except Exception as e:
        print(f"Download error for '{filename}': {e}")
        return jsonify({"error": "File not found"}), 404

@app.route("/upload", methods=["POST"])
def upload_app():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "File has no name"}), 400

    try:
        original_filename = file.filename
        unique_filename = gshift(original_filename)
        file_data = file.read()
        bucket.upload_bytes(file_data, unique_filename)

        if unique_filename != original_filename:
            print(f"Uploaded: {original_filename} -> {unique_filename} (gshifted)")
        else:
            print(f"Uploaded: {unique_filename}")

        return jsonify({
            "success": True,
            "filename": unique_filename,
            "original_filename": original_filename,
            "renamed": unique_filename != original_filename
        })
    except Exception as e:
        print(f"Upload error: {e}")
        return jsonify({"error": "Upload failed"}), 500

@app.route("/debug-files", methods=["GET"])
def debug_files():
    try:
        files = [item.file_name for item, _ in bucket.ls()]
        return jsonify(files)
    except Exception as e:
        print(f"Debug listing error: {e}")
        return jsonify({"error": "Could not list files"}), 500

SERVER_START_TIME = datetime.now()

@app.route("/ping", methods=["POST"])
def ping():
    try:
        start_time = time.time()
        try:
            _ = b2_api.account_info.get_account_id()
            b2_status = "connected"
        except Exception:
            b2_status = "disconnected"
        latency_ms = round((time.time() - start_time) * 1000, 2)
        uptime = str(datetime.now() - SERVER_START_TIME).split(".")[0]
        response = {
            "status": "online",
            "server": platform.node(),
            "latency_ms": latency_ms,
            "b2_status": b2_status,
            "uptime": uptime,
            "timestamp": datetime.now().isoformat()
        }
        return jsonify(response), 200
    except Exception as e:
        print(f"/ping error: {e}")
        return jsonify({"error": "Ping failed"}), 500

# === Main ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
