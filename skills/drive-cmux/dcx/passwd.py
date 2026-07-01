# dcx/passwd.py
"""Local, per-machine setup of the cmux socket-control password file.

The password is machine-specific and must match cmux Settings -> Socket Control
Mode -> Password. This writes it to the *configured* password_file path (so it
always lands where preflight looks), with 0600 perms, and optionally verifies.

Run it in YOUR OWN terminal so the password is typed hidden and never enters a
chat transcript. For automation use --from-stdin; for a fresh machine where you
want a strong password to paste INTO cmux, use --generate.
"""
import getpass, os, secrets, sys


def set_password(cfg, client, generate=False, from_stdin=False, verify=True):
    path = cfg["password_file"]  # already expanduser'd by load_config
    if generate:
        pw = secrets.token_urlsafe(24)
    elif from_stdin:
        pw = sys.stdin.readline().strip()
        if not pw:
            raise RuntimeError("no password received on stdin")
    else:
        if not sys.stdin.isatty():
            raise RuntimeError(
                "set-password needs an interactive terminal. Run it yourself in a "
                "terminal, or pass --from-stdin (pipe the password) or --generate."
            )
        pw = getpass.getpass("cmux socket password (hidden): ").strip()
        if not pw:
            raise RuntimeError("empty password; aborted")
        if getpass.getpass("confirm: ").strip() != pw:
            raise RuntimeError("passwords did not match; aborted")

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    # create/truncate with 0600 so the secret is never world/group readable
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, pw.encode())
    finally:
        os.close(fd)
    os.chmod(path, 0o600)

    result = {"ok": True, "password_file": path, "generated": bool(generate)}
    if generate:
        result["password"] = pw
        result["note"] = ("Paste this exact value into cmux Settings -> Socket Control "
                          "Mode -> Password, then run `dcx preflight` to confirm.")
        return result
    if verify:
        try:
            result["preflight_ok"] = bool(client.ping())
        except Exception as e:  # cmux not reachable yet / wrong password
            result["preflight_ok"] = False
            result["preflight_error"] = str(e)
    return result
