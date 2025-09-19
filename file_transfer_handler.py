# file_transfer_handler.py
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
import os

file_transfer_bp = Blueprint('file_transfer_bp', __name__)

@file_transfer_bp.route('/transfer/host-to-client', methods=['POST'])
def host_to_client_transfer():
    recipient_ids = request.form.getlist('recipients')
    if not recipient_ids:
        return jsonify({"status": "error", "message": "No recipients specified"}), 400

    uploaded_files = request.files.getlist('files[]')
    if not uploaded_files or uploaded_files[0].filename == '':
        return jsonify({"status": "error", "message": "No files selected"}), 400
    
    command_queue = current_app.config['COMMAND_QUEUE']
    upload_folder = current_app.config['UPLOAD_FOLDER']
    host_uploads_path = os.path.join(upload_folder, 'host_uploads')
    os.makedirs(host_uploads_path, exist_ok=True)
    
    for file in uploaded_files:
        filename = secure_filename(file.filename)
        file.save(os.path.join(host_uploads_path, filename))
        
        for agent_id in recipient_ids:
            if agent_id not in command_queue:
                command_queue[agent_id] = []
            command = {"task": "download_from_host", "filename": filename}
            command_queue[agent_id].append(command)
    
    return jsonify({"status": "success", "message": f"Download queued for {len(uploaded_files)} files to {len(recipient_ids)} agents."})