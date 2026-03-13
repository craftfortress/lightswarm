#!/usr/bin/env python3
"""LIGHTSWARM dashboard server. Serves project status, TODO lists, and logs."""
import http.server
import json
import os
import time

PORT = int(os.environ.get("LIGHTSWARM_PORT", 7777))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.environ.get(
    "LIGHTSWARM_PROJECTS_DIR", os.path.join(SCRIPT_DIR, "projects")
)
LOGS_DIR = os.path.join(SCRIPT_DIR, "logs")
DASHBOARD = os.path.join(SCRIPT_DIR, "dashboard.html")


def discover_projects():
    """Auto-discover project directories (any dir with a TODO.md)."""
    projects = []
    if not os.path.isdir(PROJECTS_DIR):
        return projects
    for name in sorted(os.listdir(PROJECTS_DIR)):
        full = os.path.join(PROJECTS_DIR, name)
        if os.path.isdir(full) and not name.startswith("."):
            projects.append(name)
    return projects


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silence request logs

    def do_GET(self):
        if self.path == "/" or self.path == "/dashboard":
            self._serve_file(DASHBOARD, "text/html")
        elif self.path == "/projects":
            self._serve_json(discover_projects())
        elif self.path.startswith("/todo/"):
            proj = self.path.split("/todo/")[1].split("?")[0]
            todo_path = os.path.join(PROJECTS_DIR, proj, "TODO.md")
            self._serve_file(todo_path, "text/plain")
        elif self.path.startswith("/log/"):
            parts = self.path.split("/log/")[1]
            proj = parts.split("?")[0]
            date = ""
            if "date=" in self.path:
                date = self.path.split("date=")[1].split("&")[0]
            self._serve_project_log(proj, date)
        else:
            self.send_error(404)

    def _serve_file(self, path, content_type):
        try:
            with open(path, "r") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data.encode())
        except FileNotFoundError:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"")

    def _serve_json(self, obj):
        data = json.dumps(obj)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data.encode())

    def _serve_project_log(self, project, date):
        all_lines = []

        # 1. Read per-stage logs for the date
        if date:
            for stage in ["architect", "builder", "janitor"]:
                stage_log = os.path.join(
                    LOGS_DIR, f"{project}_{stage}_{date}.log"
                )
                try:
                    with open(stage_log, "r") as f:
                        content = f.read().strip()
                        if content:
                            all_lines.append(
                                f"[{date}] [{project}] {stage} output available\n"
                            )
                except FileNotFoundError:
                    pass

        # 2. Check .swarm/build_report.md for latest status
        report = os.path.join(PROJECTS_DIR, project, ".swarm", "build_report.md")
        try:
            mtime = os.path.getmtime(report)
            from datetime import datetime

            report_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            if report_date == date:
                with open(report, "r") as f:
                    content = f.read()
                if "CLEAN" in content or "DONE" in content:
                    all_lines.append(f"[{date}] [{project}] Pipeline complete\n")
                elif "SKIPPED" in content:
                    all_lines.append(f"[{date}] [{project}] Pipeline complete\n")
        except (FileNotFoundError, OSError):
            pass

        # 3. Check .swarm/current_task.md mtime for "running" detection
        task_file = os.path.join(PROJECTS_DIR, project, ".swarm", "current_task.md")
        try:
            mtime = os.path.getmtime(task_file)
            age = time.time() - mtime
            if age < 600:  # modified in last 10 minutes = likely running
                from datetime import datetime

                task_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                if task_date == date:
                    all_lines.append(
                        f"[{date}] [{project}] Running builder...\n"
                    )
        except (FileNotFoundError, OSError):
            pass

        data = "".join(all_lines[-50:])
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data.encode())


if __name__ == "__main__":
    print(f"LIGHTSWARM dashboard: http://localhost:{PORT}")
    http.server.HTTPServer(("", PORT), Handler).serve_forever()
