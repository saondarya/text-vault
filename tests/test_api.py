import os
import sys
import unittest
import json

# Setup test environment
os.environ["SQLITE_PATH"] = "data/test_vault.db"
os.environ["JWT_SECRET"] = "test-secret-at-least-32-characters-long-key-for-tests!"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from index import app, init_app_db


class TextVaultApiTests(unittest.TestCase):
    def setUp(self):
        # Remove old test db
        if os.path.exists("data/test_vault.db"):
            os.remove("data/test_vault.db")
        init_app_db()
        self.client = app.test_client()
        self.token = None

    def tearDown(self):
        if os.path.exists("data/test_vault.db"):
            os.remove("data/test_vault.db")

    def register_and_login(self, username="testuser", password="password123"):
        res = self.client.post("/api/auth/register", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 201)
        data = json.loads(res.data)
        self.token = data["token"]
        return self.token

    def auth_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_auth_workflow(self):
        # Register
        token = self.register_and_login("alice", "mypassword")
        self.assertTrue(token)

        # Me endpoint
        res = self.client.get("/api/auth/me", headers=self.auth_headers())
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data["user"]["username"], "alice")

        # Duplicate register fails
        res = self.client.post("/api/auth/register", json={"username": "alice", "password": "mypassword"})
        self.assertEqual(res.status_code, 409)

        # Test both /api/auth/login and /auth/login (for Vercel serverless prefix independence)
        res = self.client.post("/api/auth/login", json={"username": "alice", "password": "mypassword"})
        self.assertEqual(res.status_code, 200)

        res = self.client.post("/auth/login", json={"username": "alice", "password": "mypassword"})
        self.assertEqual(res.status_code, 200)

        # Invalid login
        res = self.client.post("/api/auth/login", json={"username": "alice", "password": "wrongpassword"})
        self.assertEqual(res.status_code, 401)

    def test_folder_hierarchy_and_files(self):
        self.register_and_login()

        # Create root folder
        res = self.client.post("/api/folders", json={"name": "Projects"}, headers=self.auth_headers())
        self.assertEqual(res.status_code, 201)
        root_folder = json.loads(res.data)["folder"]
        root_id = root_folder["id"]

        # Create nested subfolder
        res = self.client.post("/api/folders", json={"name": "Frontend", "parent_folder_id": root_id}, headers=self.auth_headers())
        self.assertEqual(res.status_code, 201)
        sub_folder = json.loads(res.data)["folder"]
        sub_id = sub_folder["id"]

        # Create file in subfolder
        res = self.client.post(
            "/api/files",
            json={"folder_id": sub_id, "name": "App.jsx", "content": "export default function App() { return <div>Hello</div>; }"},
            headers=self.auth_headers()
        )
        self.assertEqual(res.status_code, 201)
        file_obj = json.loads(res.data)["file"]
        file_id = file_obj["id"]

        # Read file
        res = self.client.get(f"/api/files/{file_id}", headers=self.auth_headers())
        self.assertEqual(res.status_code, 200)
        self.assertIn("Hello", json.loads(res.data)["file"]["content"])

        # Update file
        res = self.client.patch(
            f"/api/files/{file_id}",
            json={"content": "Updated content with secret notes"},
            headers=self.auth_headers()
        )
        self.assertEqual(res.status_code, 200)

        # Duplicate file
        res = self.client.post(f"/api/files/{file_id}/duplicate", headers=self.auth_headers())
        self.assertEqual(res.status_code, 201)
        dup = json.loads(res.data)["file"]
        self.assertEqual(dup["name"], "App (Copy).jsx")

        # Search
        res = self.client.get("/api/search?q=secret", headers=self.auth_headers())
        self.assertEqual(res.status_code, 200)
        search_res = json.loads(res.data)
        self.assertTrue(len(search_res["files"]) >= 1)

    def test_batch_hierarchy_import(self):
        self.register_and_login()

        # Batch import a simulated folder structure
        items = [
            {"path": "Codebase/src/index.js", "content": "console.log('App started');"},
            {"path": "Codebase/src/utils/math.js", "content": "export const add = (a,b) => a+b;"},
            {"path": "Codebase/docs/README.md", "content": "# Documentation\nWelcome to our project."},
            {"path": "Notes.txt", "content": "Quick reminder notes."},
        ]

        res = self.client.post("/api/import/batch", json={"items": items}, headers=self.auth_headers())
        self.assertEqual(res.status_code, 201)
        data = json.loads(res.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["created_files"], 4)

        # Verify folders exist
        res = self.client.get("/api/folders", headers=self.auth_headers())
        folders = json.loads(res.data)["folders"]
        folder_names = [f["name"] for f in folders]
        self.assertIn("Codebase", folder_names)
        self.assertIn("src", folder_names)
        self.assertIn("utils", folder_names)
        self.assertIn("docs", folder_names)

        # Export test
        res = self.client.get("/api/export", headers=self.auth_headers())
        self.assertEqual(res.status_code, 200)
        export_data = json.loads(res.data)
        self.assertEqual(len(export_data["files"]), 4)

    def test_folder_zip_and_text_bundle_and_duplication(self):
        self.register_and_login()

        # Create folder
        res = self.client.post("/api/folders", json={"name": "MyProject"}, headers=self.auth_headers())
        folder_id = json.loads(res.data)["folder"]["id"]

        # Create files inside
        self.client.post("/api/files", json={"folder_id": folder_id, "name": "main.py", "content": "print('hello world')"}, headers=self.auth_headers())
        self.client.post("/api/files", json={"folder_id": folder_id, "name": "config.json", "content": "{\"debug\": true}"}, headers=self.auth_headers())

        # Test ZIP Download
        res = self.client.get(f"/api/folders/{folder_id}/download", headers=self.auth_headers())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "application/zip")
        self.assertTrue(len(res.data) > 50)  # Contains zip bytes

        # Test Text Bundle (Copy Folder)
        res = self.client.get(f"/api/folders/{folder_id}/text-bundle", headers=self.auth_headers())
        self.assertEqual(res.status_code, 200)
        bundle = json.loads(res.data)
        self.assertEqual(bundle["file_count"], 2)
        self.assertIn("--- MyProject/main.py ---", bundle["bundle_text"])
        self.assertIn("print('hello world')", bundle["bundle_text"])

        # Test Folder Duplication
        res = self.client.post(f"/api/folders/{folder_id}/duplicate", headers=self.auth_headers())
        self.assertEqual(res.status_code, 201)
        cloned = json.loads(res.data)["folder"]
        self.assertEqual(cloned["name"], "MyProject (Copy)")

        # Verify cloned folder has files
        res = self.client.get(f"/api/files?folder_id={cloned['id']}", headers=self.auth_headers())
        cloned_files = json.loads(res.data)["files"]
        self.assertEqual(len(cloned_files), 2)


if __name__ == "__main__":
    unittest.main()
