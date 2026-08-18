import os
import sys
import urllib.parse
from functools import wraps

# Ensure local imports work in both standalone and Vercel serverless environments
sys.path.insert(0, os.path.dirname(__file__))

import jwt
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

from db import execute, fetchall, fetchone, get_db, init_db, USE_PG

init_app_db = init_db

app = Flask(__name__)
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me-in-production-text-vault-super-secure-key-32bytes")
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB limit per file
MAX_BATCH_FILES = 200  # Max files in a single batch upload

PUBLIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "public"))


def extract_real_path(environ):
    # 1. Check RAW_URI / REQUEST_URI
    for key in ("RAW_URI", "REQUEST_URI", "HTTP_X_ORIGINAL_URL", "HTTP_X_FORWARDED_URI", "HTTP_X_VERCEL_FORWARDED_URI"):
        val = environ.get(key)
        if val:
            path_part = val.split("?")[0]
            if path_part and path_part not in ("/api/index.py", "/api/index", "/index.py", "/index", "/api"):
                return path_part

    # 2. Check X-Matched-Path (only if not pointing to index.py)
    for key in ("HTTP_X_MATCHED_PATH", "HTTP_X_VERCEL_MATCHED_PATH", "HTTP_X_FORWARDED_PATH"):
        val = environ.get(key)
        if val:
            path_part = val.split("?")[0]
            if path_part and path_part not in ("/api/index.py", "/api/index", "/index.py", "/index", "/api"):
                return path_part

    # 3. Check X-Now-Route-Matches e.g. "1=auth/login" or "1=%2Fauth%2Flogin"
    route_matches = environ.get("HTTP_X_NOW_ROUTE_MATCHES", "")
    if route_matches:
        for part in route_matches.split("&"):
            if part.startswith("1="):
                sub = urllib.parse.unquote(part[2:]).lstrip("/")
                if sub:
                    return f"/api/{sub}"

    # 4. Check query string param e.g. ?path=auth/login
    query = environ.get("QUERY_STRING", "")
    if query:
        params = urllib.parse.parse_qs(query)
        if "path" in params and params["path"][0]:
            sub = params["path"][0].lstrip("/")
            if sub:
                return f"/api/{sub}"

    return None


# WSGI Middleware to extract the real request path from Vercel's proxy headers
class VercelPathFixMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path in ("/api/index.py", "/api/index", "/index.py", "/index", "/api", ""):
            real_path = extract_real_path(environ)
            if real_path:
                environ["PATH_INFO"] = real_path

        return self.wsgi_app(environ, start_response)


app.wsgi_app = VercelPathFixMiddleware(app.wsgi_app)


# Route registration helper that registers both /api/<path> and /<path>
def api_route(rule, **options):
    def decorator(f):
        endpoint = options.pop("endpoint", None)
        clean = rule if not rule.startswith("/api") else rule[4:]
        if not clean.startswith("/"):
            clean = "/" + clean
        api_path = "/api" + clean

        ep1 = endpoint or f.__name__
        ep2 = f"{ep1}_raw"

        app.add_url_rule(api_path, ep1, f, **options)
        if clean != "/":
            app.add_url_rule(clean, ep2, f, **options)
        return f
    return decorator


# --- Middleware & CORS ---

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


@app.errorhandler(404)
def not_found(e):
    path = request.path
    if path.startswith("/api/") or any(path.startswith(p) for p in ["/auth/", "/folders", "/files", "/search", "/import", "/export"]):
        return jsonify({"error": f"API route '{path}' not found"}), 404
    if os.path.exists(os.path.join(PUBLIC_DIR, "index.html")):
        return send_from_directory(PUBLIC_DIR, "index.html")
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500


def validate_name(name, field="Name"):
    if not isinstance(name, str):
        return f"{field} is required"
    trimmed = name.strip()
    if not trimmed:
        return f"{field} cannot be empty"
    if len(trimmed) > 255:
        return f"{field} must be under 255 characters"
    return None


def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == "OPTIONS":
            return jsonify({}), 200

        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "Authentication required"}), 401
        token = header[7:].strip()
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request.user = payload
        except jwt.PyJWTError:
            return jsonify({"error": "Invalid or expired session. Please log in again."}), 401
        return f(*args, **kwargs)

    return decorated


def get_folder(user_id, folder_id):
    with get_db() as conn:
        return fetchone(conn, "SELECT * FROM folders WHERE id = ? AND user_id = ?", (folder_id, user_id))


def is_descendant(folder_id, ancestor_id, user_id):
    current = get_folder(user_id, folder_id)
    visited = set()
    while current and current.get("parent_folder_id"):
        parent_id = current["parent_folder_id"]
        if parent_id == ancestor_id:
            return True
        if parent_id in visited:
            break
        visited.add(parent_id)
        current = get_folder(user_id, parent_id)
    return False


# --- Static Files (Local Dev / Standalone) ---

@app.route("/")
def serve_index():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.route("/css/<path:filename>")
def serve_css(filename):
    return send_from_directory(os.path.join(PUBLIC_DIR, "css"), filename)


@app.route("/js/<path:filename>")
def serve_js(filename):
    return send_from_directory(os.path.join(PUBLIC_DIR, "js"), filename)


@app.route("/favicon.ico")
def serve_favicon():
    return ("", 204)


# --- Fallback Dispatcher for Vercel Entrypoint ---

@app.route("/api/index.py", methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"])
@app.route("/api/index", methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"])
@app.route("/api", methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"])
def vercel_entrypoint_catchall():
    real_path = extract_real_path(request.environ)
    if real_path:
        adapter = app.url_map.bind_to_environ(request.environ, server_name=request.host)
        try:
            endpoint, args = adapter.match(real_path, method=request.method)
            return app.view_functions[endpoint](**args)
        except Exception as err:
            print(f"Fallback dispatch error for '{real_path}': {err}", file=sys.stderr)

    return jsonify({"error": f"API route '{real_path or request.path}' not found"}), 404


# --- Health ---

@api_route("/api/health")
def health():
    return jsonify({
        "status": "healthy",
        "database": "postgresql" if USE_PG else "sqlite",
        "version": "1.0.0"
    })


# --- Auth Routes ---

@api_route("/api/auth/register", methods=["POST", "OPTIONS"])
def register():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")

    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify({"error": "Username and password are required"}), 400

    username = username.strip()
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if len(username) > 32:
        return jsonify({"error": "Username must be 32 characters or fewer"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    with get_db() as conn:
        if fetchone(conn, "SELECT id FROM users WHERE username = ?", (username,)):
            return jsonify({"error": "Username is already taken"}), 409

        pw_hash = generate_password_hash(password)
        user_id = execute(conn, "INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, pw_hash))

    token = jwt.encode({"userId": user_id, "username": username}, JWT_SECRET, algorithm="HS256")
    return jsonify({"token": token, "user": {"id": user_id, "username": username}}), 201


@api_route("/api/auth/login", methods=["POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")

    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify({"error": "Username and password are required"}), 400

    username = username.strip()
    with get_db() as conn:
        user = fetchone(conn, "SELECT * FROM users WHERE username = ?", (username,))

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password"}), 401

    token = jwt.encode({"userId": user["id"], "username": user["username"]}, JWT_SECRET, algorithm="HS256")
    return jsonify({"token": token, "user": {"id": user["id"], "username": user["username"]}})


@api_route("/api/auth/me", methods=["GET", "OPTIONS"])
@auth_required
def me():
    return jsonify({"user": {"id": request.user["userId"], "username": request.user["username"]}})


@api_route("/api/auth/change-password", methods=["POST", "OPTIONS"])
@auth_required
def change_password():
    user_id = request.user["userId"]
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")

    if not current_password or not new_password:
        return jsonify({"error": "Current and new password are required"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters"}), 400

    with get_db() as conn:
        user = fetchone(conn, "SELECT * FROM users WHERE id = ?", (user_id,))
        if not user or not check_password_hash(user["password_hash"], current_password):
            return jsonify({"error": "Current password is incorrect"}), 401

        new_hash = generate_password_hash(new_password)
        execute(conn, "UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))

    return jsonify({"message": "Password changed successfully"})


# --- Folders ---

@api_route("/api/folders", methods=["GET", "POST", "OPTIONS"])
@auth_required
def folders():
    user_id = request.user["userId"]

    if request.method == "GET":
        with get_db() as conn:
            order = "ORDER BY name" if USE_PG else "ORDER BY name COLLATE NOCASE"
            folders_list = fetchall(
                conn,
                f"""
                SELECT f.id, f.user_id, f.parent_folder_id, f.name, f.created_at,
                       (SELECT COUNT(*) FROM files WHERE files.folder_id = f.id) AS file_count
                FROM folders f
                WHERE f.user_id = ? {order}
                """,
                (user_id,),
            )
        return jsonify({"folders": folders_list})

    # POST create folder
    data = request.get_json(silent=True) or {}
    err = validate_name(data.get("name"), "Folder name")
    if err:
        return jsonify({"error": err}), 400

    name = data["name"].strip()
    parent_id = data.get("parent_folder_id")

    if parent_id is not None:
        try:
            parent_id = int(parent_id)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid parent_folder_id"}), 400

        parent = get_folder(user_id, parent_id)
        if not parent:
            return jsonify({"error": "Parent folder not found"}), 404

    with get_db() as conn:
        folder_id = execute(
            conn,
            "INSERT INTO folders (user_id, parent_folder_id, name) VALUES (?, ?, ?)",
            (user_id, parent_id, name),
        )
        folder = fetchone(conn, "SELECT id, user_id, parent_folder_id, name, created_at, 0 as file_count FROM folders WHERE id = ?", (folder_id,))

    return jsonify({"folder": folder}), 201


@api_route("/api/folders/<int:folder_id>", methods=["PATCH", "DELETE", "OPTIONS"])
@auth_required
def single_folder(folder_id):
    user_id = request.user["userId"]
    folder = get_folder(user_id, folder_id)
    if not folder:
        return jsonify({"error": "Folder not found"}), 404

    if request.method == "DELETE":
        with get_db() as conn:
            def delete_subtree(fid):
                subfolders = fetchall(conn, "SELECT id FROM folders WHERE parent_folder_id = ? AND user_id = ?", (fid, user_id))
                for sub in subfolders:
                    delete_subtree(sub["id"])
                execute(conn, "DELETE FROM files WHERE folder_id = ? AND user_id = ?", (fid, user_id))
                execute(conn, "DELETE FROM folders WHERE id = ? AND user_id = ?", (fid, user_id))

            delete_subtree(folder_id)

        return jsonify({"success": True})

    # PATCH
    data = request.get_json(silent=True) or {}
    updates = []
    params = []

    if "name" in data:
        err = validate_name(data["name"], "Folder name")
        if err:
            return jsonify({"error": err}), 400
        updates.append("name = ?")
        params.append(data["name"].strip())

    if "parent_folder_id" in data:
        parent_id = data["parent_folder_id"]
        if parent_id is not None:
            try:
                parent_id = int(parent_id)
            except (ValueError, TypeError):
                return jsonify({"error": "Invalid parent_folder_id"}), 400

            if parent_id == folder_id:
                return jsonify({"error": "A folder cannot be inside itself"}), 400
            if not get_folder(user_id, parent_id):
                return jsonify({"error": "Target parent folder not found"}), 404
            if is_descendant(parent_id, folder_id, user_id):
                return jsonify({"error": "Cannot move a folder into one of its own subfolders"}), 400
        updates.append("parent_folder_id = ?")
        params.append(parent_id)

    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    params.extend([folder_id, user_id])
    with get_db() as conn:
        execute(conn, f"UPDATE folders SET {', '.join(updates)} WHERE id = ? AND user_id = ?", params)
        updated = fetchone(
            conn,
            """
            SELECT f.id, f.user_id, f.parent_folder_id, f.name, f.created_at,
                   (SELECT COUNT(*) FROM files WHERE files.folder_id = f.id) AS file_count
            FROM folders f WHERE f.id = ?
            """,
            (folder_id,),
        )

    return jsonify({"folder": updated})


# --- Folder Download, Duplicate & Text Bundle ---

@api_route("/api/folders/<int:folder_id>/download", methods=["GET", "OPTIONS"])
@auth_required
def download_folder_zip(folder_id):
    import io
    import zipfile
    from flask import send_file

    user_id = request.user["userId"]
    folder = get_folder(user_id, folder_id)
    if not folder:
        return jsonify({"error": "Folder not found"}), 404

    with get_db() as conn:
        all_folders = fetchall(conn, "SELECT id, parent_folder_id, name FROM folders WHERE user_id = ?", (user_id,))
        all_files = fetchall(conn, "SELECT id, folder_id, name, content FROM files WHERE user_id = ?", (user_id,))

    subfolders_map = {}
    for f in all_folders:
        subfolders_map.setdefault(f["parent_folder_id"], []).append(f)

    files_by_folder = {}
    for fl in all_files:
        files_by_folder.setdefault(fl["folder_id"], []).append(fl)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        def add_folder_to_zip(fid, current_path):
            for fl in files_by_folder.get(fid, []):
                file_zip_path = os.path.join(current_path, fl["name"]).replace("\\", "/")
                zf.writestr(file_zip_path, fl["content"] or "")

            children = subfolders_map.get(fid, [])
            if not children and not files_by_folder.get(fid):
                zf.writestr(current_path + "/", "")

            for child in children:
                child_path = os.path.join(current_path, child["name"]).replace("\\", "/")
                add_folder_to_zip(child["id"], child_path)

        add_folder_to_zip(folder_id, folder["name"])

    zip_buffer.seek(0)
    safe_name = "".join(c for c in folder["name"] if c.isalnum() or c in " ._-").strip() or "folder"
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{safe_name}.zip"
    )


@api_route("/api/folders/<int:folder_id>/duplicate", methods=["POST", "OPTIONS"])
@auth_required
def duplicate_folder(folder_id):
    user_id = request.user["userId"]
    folder = get_folder(user_id, folder_id)
    if not folder:
        return jsonify({"error": "Folder not found"}), 404

    with get_db() as conn:
        all_folders = fetchall(conn, "SELECT id, parent_folder_id, name FROM folders WHERE user_id = ?", (user_id,))
        all_files = fetchall(conn, "SELECT id, folder_id, name, content FROM files WHERE user_id = ?", (user_id,))

        subfolders_map = {}
        for f in all_folders:
            subfolders_map.setdefault(f["parent_folder_id"], []).append(f)

        files_by_folder = {}
        for fl in all_files:
            files_by_folder.setdefault(fl["folder_id"], []).append(fl)

        def clone_folder_recursive(src_fid, new_parent_id, new_name):
            new_fid = execute(
                conn,
                "INSERT INTO folders (user_id, parent_folder_id, name) VALUES (?, ?, ?)",
                (user_id, new_parent_id, new_name),
            )
            for fl in files_by_folder.get(src_fid, []):
                execute(
                    conn,
                    "INSERT INTO files (user_id, folder_id, name, content) VALUES (?, ?, ?, ?)",
                    (user_id, new_fid, fl["name"], fl["content"]),
                )
            for child in subfolders_map.get(src_fid, []):
                clone_folder_recursive(child["id"], new_fid, child["name"])
            return new_fid

        cloned_root_id = clone_folder_recursive(folder_id, folder["parent_folder_id"], f"{folder['name']} (Copy)")
        cloned_folder = fetchone(conn, "SELECT * FROM folders WHERE id = ?", (cloned_root_id,))

    return jsonify({"folder": cloned_folder}), 201


@api_route("/api/folders/<int:folder_id>/text-bundle", methods=["GET", "OPTIONS"])
@auth_required
def get_folder_text_bundle(folder_id):
    user_id = request.user["userId"]
    folder = get_folder(user_id, folder_id)
    if not folder:
        return jsonify({"error": "Folder not found"}), 404

    with get_db() as conn:
        all_folders = fetchall(conn, "SELECT id, parent_folder_id, name FROM folders WHERE user_id = ?", (user_id,))
        all_files = fetchall(conn, "SELECT id, folder_id, name, content FROM files WHERE user_id = ?", (user_id,))

    subfolders_map = {}
    for f in all_folders:
        subfolders_map.setdefault(f["parent_folder_id"], []).append(f)

    files_by_folder = {}
    for fl in all_files:
        files_by_folder.setdefault(fl["folder_id"], []).append(fl)

    bundle_parts = []

    def collect_folder_text(fid, current_path):
        for fl in files_by_folder.get(fid, []):
            rel_path = os.path.join(current_path, fl["name"]).replace("\\", "/")
            bundle_parts.append(f"--- {rel_path} ---\n{fl['content'] or ''}\n")

        for child in subfolders_map.get(fid, []):
            child_path = os.path.join(current_path, child["name"]).replace("\\", "/")
            collect_folder_text(child["id"], child_path)

    collect_folder_text(folder_id, folder["name"])
    full_text = "\n".join(bundle_parts)

    return jsonify({
        "folder_name": folder["name"],
        "bundle_text": full_text,
        "file_count": len(bundle_parts)
    })


# --- Files ---

@api_route("/api/files", methods=["GET", "POST", "OPTIONS"])
@auth_required
def files():
    user_id = request.user["userId"]

    if request.method == "GET":
        folder_id = request.args.get("folder_id", type=int)
        if not folder_id:
            return jsonify({"error": "folder_id query parameter is required"}), 400
        if not get_folder(user_id, folder_id):
            return jsonify({"error": "Folder not found"}), 404

        with get_db() as conn:
            files_list = fetchall(
                conn,
                """
                SELECT id, user_id, folder_id, name, updated_at, LENGTH(content) AS size
                FROM files
                WHERE user_id = ? AND folder_id = ?
                ORDER BY name COLLATE NOCASE
                """ if not USE_PG else """
                SELECT id, user_id, folder_id, name, updated_at, LENGTH(content) AS size
                FROM files
                WHERE user_id = ? AND folder_id = ?
                ORDER BY name
                """,
                (user_id, folder_id),
            )
        return jsonify({"files": files_list})

    # POST create file
    data = request.get_json(silent=True) or {}
    err = validate_name(data.get("name"), "File name")
    if err:
        return jsonify({"error": err}), 400

    folder_id = data.get("folder_id")
    if not folder_id:
        return jsonify({"error": "folder_id is required"}), 400

    try:
        folder_id = int(folder_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid folder_id"}), 400

    if not get_folder(user_id, folder_id):
        return jsonify({"error": "Target folder not found"}), 404

    content = data.get("content", "")
    if not isinstance(content, str):
        return jsonify({"error": "Content must be a string"}), 400
    if len(content.encode("utf-8")) > MAX_FILE_SIZE:
        return jsonify({"error": "File content exceeds 5 MB limit"}), 400

    with get_db() as conn:
        file_id = execute(
            conn,
            "INSERT INTO files (user_id, folder_id, name, content) VALUES (?, ?, ?, ?)",
            (user_id, folder_id, data["name"].strip(), content),
        )
        file_obj = fetchone(conn, "SELECT * FROM files WHERE id = ?", (file_id,))

    return jsonify({"file": file_obj}), 201


@api_route("/api/files/<int:file_id>", methods=["GET", "PATCH", "DELETE", "OPTIONS"])
@auth_required
def single_file(file_id):
    user_id = request.user["userId"]

    with get_db() as conn:
        file_obj = fetchone(conn, "SELECT * FROM files WHERE id = ? AND user_id = ?", (file_id, user_id))

    if not file_obj:
        return jsonify({"error": "File not found"}), 404

    if request.method == "GET":
        return jsonify({"file": file_obj})

    if request.method == "DELETE":
        with get_db() as conn:
            execute(conn, "DELETE FROM files WHERE id = ? AND user_id = ?", (file_id, user_id))
        return jsonify({"success": True})

    # PATCH
    data = request.get_json(silent=True) or {}
    updates = []
    params = []

    if "name" in data:
        err = validate_name(data["name"], "File name")
        if err:
            return jsonify({"error": err}), 400
        updates.append("name = ?")
        params.append(data["name"].strip())

    if "content" in data:
        if not isinstance(data["content"], str):
            return jsonify({"error": "Content must be a string"}), 400
        if len(data["content"].encode("utf-8")) > MAX_FILE_SIZE:
            return jsonify({"error": "File content exceeds 5 MB limit"}), 400
        updates.append("content = ?")
        params.append(data["content"])

    if "folder_id" in data:
        target_folder_id = data["folder_id"]
        try:
            target_folder_id = int(target_folder_id)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid folder_id"}), 400

        if not get_folder(user_id, target_folder_id):
            return jsonify({"error": "Target folder not found"}), 404
        updates.append("folder_id = ?")
        params.append(target_folder_id)

    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    if USE_PG:
        updates.append("updated_at = NOW()")
    else:
        updates.append("updated_at = datetime('now')")

    params.extend([file_id, user_id])
    with get_db() as conn:
        execute(conn, f"UPDATE files SET {', '.join(updates)} WHERE id = ? AND user_id = ?", params)
        updated = fetchone(conn, "SELECT * FROM files WHERE id = ?", (file_id,))

    return jsonify({"file": updated})


@api_route("/api/files/<int:file_id>/duplicate", methods=["POST", "OPTIONS"])
@auth_required
def duplicate_file(file_id):
    user_id = request.user["userId"]
    with get_db() as conn:
        file_obj = fetchone(conn, "SELECT * FROM files WHERE id = ? AND user_id = ?", (file_id, user_id))
        if not file_obj:
            return jsonify({"error": "File not found"}), 404

        name = file_obj["name"]
        if "." in name:
            base, ext = name.rsplit(".", 1)
            new_name = f"{base} (Copy).{ext}"
        else:
            new_name = f"{name} (Copy)"

        new_id = execute(
            conn,
            "INSERT INTO files (user_id, folder_id, name, content) VALUES (?, ?, ?, ?)",
            (user_id, file_obj["folder_id"], new_name, file_obj["content"]),
        )
        new_file = fetchone(conn, "SELECT * FROM files WHERE id = ?", (new_id,))

    return jsonify({"file": new_file}), 201


# --- Search ---

@api_route("/api/search", methods=["GET", "OPTIONS"])
@auth_required
def search():
    user_id = request.user["userId"]
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"files": [], "folders": []})

    search_param = f"%{query}%"

    with get_db() as conn:
        matched_folders = fetchall(
            conn,
            """
            SELECT id, name, parent_folder_id, created_at
            FROM folders
            WHERE user_id = ? AND name LIKE ?
            LIMIT 20
            """,
            (user_id, search_param),
        )

        matched_files = fetchall(
            conn,
            """
            SELECT f.id, f.folder_id, f.name, f.updated_at, LENGTH(f.content) as size,
                   fold.name as folder_name,
                   SUBSTR(f.content, 1, 150) as snippet
            FROM files f
            JOIN folders fold ON f.folder_id = fold.id
            WHERE f.user_id = ? AND (f.name LIKE ? OR f.content LIKE ?)
            LIMIT 40
            """,
            (user_id, search_param, search_param),
        )

    return jsonify({
        "query": query,
        "folders": matched_folders,
        "files": matched_files,
    })


# --- Hierarchy Batch Import (Local Folder Upload / Tree Paste) ---

@api_route("/api/import/batch", methods=["POST", "OPTIONS"])
@auth_required
def import_batch():
    user_id = request.user["userId"]
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    root_folder_id = data.get("target_folder_id")

    if root_folder_id is not None:
        try:
            root_folder_id = int(root_folder_id)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid target_folder_id"}), 400
        if not get_folder(user_id, root_folder_id):
            return jsonify({"error": "Target folder not found"}), 404

    if not isinstance(items, list) or not items:
        return jsonify({"error": "Items list is required"}), 400

    if len(items) > MAX_BATCH_FILES:
        return jsonify({"error": f"Maximum {MAX_BATCH_FILES} files allowed per import"}), 400

    created_folders_count = 0
    created_files_count = 0

    with get_db() as conn:
        existing_folders = fetchall(conn, "SELECT id, parent_folder_id, name FROM folders WHERE user_id = ?", (user_id,))
        folder_cache = {
            (f["parent_folder_id"], f["name"].strip().lower()): f["id"]
            for f in existing_folders
        }

        def get_or_create_folder(parent_id, folder_name):
            nonlocal created_folders_count
            norm_name = folder_name.strip()
            cache_key = (parent_id, norm_name.lower())
            if cache_key in folder_cache:
                return folder_cache[cache_key]

            new_fid = execute(
                conn,
                "INSERT INTO folders (user_id, parent_folder_id, name) VALUES (?, ?, ?)",
                (user_id, parent_id, norm_name),
            )
            folder_cache[cache_key] = new_fid
            created_folders_count += 1
            return new_fid

        for item in items:
            raw_path = item.get("path", "").strip()
            content = item.get("content", "")
            if not isinstance(content, str):
                content = str(content)

            if not raw_path:
                continue

            parts = [p.strip() for p in raw_path.replace("\\", "/").split("/") if p.strip() and p.strip() != "."]
            if not parts:
                continue

            file_name = parts[-1]
            folder_parts = parts[:-1]

            current_parent = root_folder_id
            for folder_part in folder_parts:
                current_parent = get_or_create_folder(current_parent, folder_part)

            if current_parent is None:
                current_parent = get_or_create_folder(None, "Imported")

            execute(
                conn,
                "INSERT INTO files (user_id, folder_id, name, content) VALUES (?, ?, ?, ?)",
                (user_id, current_parent, file_name, content),
            )
            created_files_count += 1

    return jsonify({
        "success": True,
        "created_folders": created_folders_count,
        "created_files": created_files_count,
    }), 201


# --- Export Vault ---

@api_route("/api/export", methods=["GET", "OPTIONS"])
@auth_required
def export_vault():
    user_id = request.user["userId"]
    with get_db() as conn:
        all_folders = fetchall(conn, "SELECT id, parent_folder_id, name, created_at FROM folders WHERE user_id = ?", (user_id,))
        all_files = fetchall(conn, "SELECT id, folder_id, name, content, updated_at FROM files WHERE user_id = ?", (user_id,))

    return jsonify({
        "username": request.user["username"],
        "exported_at": "now",
        "folders": all_folders,
        "files": all_files,
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
