#!/usr/bin/env python3
import hmac
import json
import os
import re
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = os.environ.get("COMPOSE_AGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("COMPOSE_AGENT_PORT", "8320"))
CONFIG_PATH = Path(os.environ.get("COMPOSE_AGENT_CONFIG", "/config/stacks.json"))
TOKEN = os.environ.get("COMPOSE_AGENT_TOKEN", "")
COMMAND_TIMEOUT = int(os.environ.get("COMPOSE_AGENT_COMMAND_TIMEOUT", "600"))
MAX_OUTPUT = int(os.environ.get("COMPOSE_AGENT_MAX_OUTPUT", "32768"))
STACK_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SHA_TAG_RE = re.compile(r"^sha-[0-9a-f]{7,40}$")
VARIABLE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
LOCKS = {}
LOCKS_GUARD = threading.Lock()


class AgentError(Exception):
    pass


def load_stacks():
    if not TOKEN or len(TOKEN) < 32:
        raise AgentError("COMPOSE_AGENT_TOKEN must contain at least 32 characters")
    try:
        document = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentError(f"Cannot load Compose stack configuration: {exc}") from exc
    stacks = document.get("stacks")
    if not isinstance(stacks, dict) or not stacks:
        raise AgentError("The Compose stack configuration must contain a non-empty stacks object")
    return stacks


def safe_stack(name, stacks):
    if not STACK_RE.fullmatch(name):
        raise AgentError("Invalid stack name")
    raw = stacks.get(name)
    if not isinstance(raw, dict):
        raise AgentError("Stack is not allowlisted")

    required = (
        "directory",
        "compose_file",
        "env_file",
        "image_variable",
        "image_repository",
        "project_name",
    )
    if any(not isinstance(raw.get(key), str) or not raw[key] for key in required):
        raise AgentError("Allowlisted stack configuration is incomplete")
    if not VARIABLE_RE.fullmatch(raw["image_variable"]):
        raise AgentError("Invalid managed image variable")
    if not STACK_RE.fullmatch(raw["project_name"]):
        raise AgentError("Invalid Compose project name")

    directory = Path(raw["directory"]).resolve(strict=True)
    if not directory.is_dir():
        raise AgentError("Stack directory is not a directory")

    compose_path = directory / raw["compose_file"]
    env_path = directory / raw["env_file"]
    if compose_path.is_symlink() or env_path.is_symlink():
        raise AgentError("Configured stack files must not be symbolic links")
    compose_file = compose_path.resolve(strict=True)
    env_file = env_path.resolve(strict=True)
    for candidate in (compose_file, env_file):
        if directory not in candidate.parents or not candidate.is_file():
            raise AgentError("Configured stack file escapes the allowlisted directory")

    return {
        **raw,
        "directory": directory,
        "compose_file": compose_file,
        "env_file": env_file,
    }


def read_managed_image(stack):
    variable = stack["image_variable"]
    pattern = re.compile(rf"^{re.escape(variable)}=(.*)$")
    matches = [pattern.match(line) for line in stack["env_file"].read_text(encoding="utf-8").splitlines()]
    values = [match.group(1).strip() for match in matches if match]
    if len(values) != 1:
        raise AgentError(f"{variable} must appear exactly once in the env file")
    return values[0]


def validate_image(stack, image):
    repository = stack["image_repository"]
    prefix = f"{repository}:"
    if not image.startswith(prefix) or not SHA_TAG_RE.fullmatch(image[len(prefix) :]):
        raise AgentError(f"Image must use repository {repository} with an immutable sha-* tag")


def write_env_content(env_file, content):
    stat = env_file.stat()
    fd, temporary = tempfile.mkstemp(prefix=".mcp-env-", dir=env_file.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, stat.st_mode)
        os.chown(temporary, stat.st_uid, stat.st_gid)
        os.replace(temporary, env_file)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def replace_managed_image(stack, image):
    env_file = stack["env_file"]
    variable = stack["image_variable"]
    original = env_file.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(variable)}=.*$", re.MULTILINE)
    if len(pattern.findall(original)) != 1:
        raise AgentError(f"{variable} must appear exactly once in the env file")
    updated = pattern.sub(f"{variable}={image}", original)
    write_env_content(env_file, updated)
    return original


def restore_env(stack, original):
    write_env_content(stack["env_file"], original)


def compose_args(stack, command):
    return [
        "docker",
        "compose",
        "--env-file",
        str(stack["env_file"]),
        "-f",
        str(stack["compose_file"]),
        "-p",
        stack["project_name"],
        *command,
    ]


def run_command(args):
    try:
        completed = subprocess.run(
            args,
            cwd=None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=COMMAND_TIMEOUT,
            check=False,
            env={**os.environ, "DOCKER_HOST": "unix:///var/run/docker.sock"},
        )
    except subprocess.TimeoutExpired as exc:
        raise AgentError("Compose operation timed out") from exc
    output = completed.stdout[-MAX_OUTPUT:]
    if completed.returncode != 0:
        raise AgentError(output.strip() or f"Compose exited with code {completed.returncode}")
    return output.strip()


def update_stack(name, image, stacks):
    stack = safe_stack(name, stacks)
    validate_image(stack, image)
    previous = read_managed_image(stack)
    if previous == image:
        return {"stack": name, "image": image, "previousImage": previous, "changed": False}

    original = replace_managed_image(stack, image)
    try:
        pull_output = run_command(compose_args(stack, ["pull"]))
        up_output = run_command(
            compose_args(stack, ["up", "-d", "--wait", "--wait-timeout", "180"])
        )
        status = run_command(compose_args(stack, ["ps", "--format", "json"]))
    except AgentError as update_error:
        restore_env(stack, original)
        try:
            rollback = run_command(
                compose_args(stack, ["up", "-d", "--wait", "--wait-timeout", "180"])
            )
            rollback_message = "Previous image restored and stack recreated."
            if rollback:
                rollback_message += f" {rollback[-1000:]}"
        except AgentError as rollback_error:
            rollback_message = f"Rollback also failed: {rollback_error}"
        raise AgentError(f"Compose update failed: {update_error}. {rollback_message}") from update_error

    return {
        "stack": name,
        "image": image,
        "previousImage": previous,
        "changed": True,
        "pull": pull_output[-2000:],
        "recreate": up_output[-2000:],
        "status": status[-8000:],
    }


def stack_lock(name):
    with LOCKS_GUARD:
        return LOCKS.setdefault(name, threading.Lock())


class Handler(BaseHTTPRequestHandler):
    server_version = "unraid-compose-agent/1"

    def log_message(self, fmt, *args):
        print(f"[compose-agent] {self.address_string()} {fmt % args}", flush=True)

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authenticated(self):
        supplied = self.headers.get("authorization", "")
        expected = f"Bearer {TOKEN}"
        return hmac.compare_digest(supplied, expected)

    def read_json(self):
        try:
            length = int(self.headers.get("content-length", "0"))
        except ValueError as exc:
            raise AgentError("Invalid content length") from exc
        if length < 1 or length > 4096:
            raise AgentError("Request body must be between 1 and 4096 bytes")
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise AgentError("Invalid JSON body") from exc

    def do_GET(self):
        if self.path == "/health":
            try:
                load_stacks()
                self.send_json(200, {"status": "ok"})
            except AgentError as exc:
                self.send_json(503, {"status": "error", "error": str(exc)})
            return
        if not self.authenticated():
            self.send_json(401, {"error": "Unauthorized"})
            return
        if self.path != "/v1/stacks":
            self.send_json(404, {"error": "Not found"})
            return
        try:
            stacks = load_stacks()
            items = []
            for name in sorted(stacks):
                stack = safe_stack(name, stacks)
                items.append(
                    {
                        "name": name,
                        "projectName": stack["project_name"],
                        "imageRepository": stack["image_repository"],
                        "image": read_managed_image(stack),
                    }
                )
            self.send_json(200, {"stacks": items})
        except AgentError as exc:
            self.send_json(500, {"error": str(exc)})

    def do_POST(self):
        if not self.authenticated():
            self.send_json(401, {"error": "Unauthorized"})
            return
        if self.path != "/v1/stacks/update":
            self.send_json(404, {"error": "Not found"})
            return
        try:
            body = self.read_json()
            if body.get("confirmation") != "UPDATE_COMPOSE_STACK":
                raise AgentError("confirmation=UPDATE_COMPOSE_STACK is required")
            name = body.get("stack")
            image = body.get("image")
            if not isinstance(name, str) or not isinstance(image, str):
                raise AgentError("stack and image are required strings")
            with stack_lock(name):
                response = update_stack(name, image, load_stacks())
            self.send_json(200, response)
        except AgentError as exc:
            self.send_json(400, {"error": str(exc)})


def main():
    load_stacks()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[compose-agent] listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
