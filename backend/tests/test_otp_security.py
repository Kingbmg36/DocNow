"""Security regression tests for OTP code generation.

Locks in the fix from the iteration-7 code review: OTP codes must be generated
with the cryptographically-secure `secrets` module (PEP 506 / NIST SP 800-63B),
never with the predictable `random` module.

These tests are pure unit tests — they do not touch the DB or network — so they
run fast and can be executed standalone:

    cd /app/backend && python -m pytest tests/test_otp_security.py -v
"""
import ast
import inspect
import re
from pathlib import Path

import pytest


OTP_PATH = Path(__file__).resolve().parent.parent / "otp.py"


def _import_otp():
    """Import otp.py with MONGO_URL stubbed so it loads even outside the app env."""
    import os
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "medinest_test")
    import importlib
    import otp as _otp
    importlib.reload(_otp)
    return _otp


# ---------- Format guarantees ----------

def test_generate_code_returns_six_digit_string():
    otp = _import_otp()
    code = otp._generate_code()
    assert isinstance(code, str), "OTP code must be a string"
    assert len(code) == otp.OTP_LENGTH == 6, f"OTP must be 6 chars, got {len(code)}"
    assert code.isdigit(), f"OTP must be all digits, got: {code!r}"


def test_generate_code_full_digit_range():
    """Across many samples, every digit 0–9 should appear at least once."""
    otp = _import_otp()
    seen = set()
    for _ in range(2000):
        seen.update(otp._generate_code())
    assert seen == set("0123456789"), (
        f"Expected all digits 0–9 to appear, got: {sorted(seen)}"
    )


def test_generate_code_reasonable_uniqueness():
    """Two consecutive calls should rarely (effectively never) collide.

    Probability of two random 6-digit codes colliding = 1/1_000_000.
    Across 200 samples we'd expect at most ~0.02 collisions on average — so
    requiring >= 195 unique is a safe lower bound that won't flake.
    """
    otp = _import_otp()
    codes = {otp._generate_code() for _ in range(200)}
    assert len(codes) >= 195, f"Suspiciously low uniqueness: {len(codes)}/200"


# ---------- Security guarantees ----------

def test_otp_module_does_not_import_random():
    """`random` is predictable (Mersenne Twister) and must not be used for OTPs.

    We parse otp.py's AST instead of just checking source-string membership so
    that comments mentioning 'random' don't cause false positives.
    """
    source = OTP_PATH.read_text()
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module.split(".")[0])
    assert "random" not in imported_modules, (
        "otp.py must not import the `random` module — use `secrets` for "
        "cryptographically secure OTP generation."
    )


def test_otp_module_imports_secrets():
    otp = _import_otp()
    source = inspect.getsource(otp)
    assert re.search(r"^\s*import\s+secrets\b", source, re.MULTILINE), (
        "otp.py must import the `secrets` module."
    )


def test_generate_code_uses_secrets_randbelow():
    """The body of _generate_code() must call secrets.randbelow.

    Asserting on the AST (not the runtime output) is the right level — output
    looks identical to random.randint output, so we lock the implementation.
    """
    source = OTP_PATH.read_text()
    tree = ast.parse(source)
    target_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_generate_code":
            target_fn = node
            break
    assert target_fn is not None, "_generate_code function not found in otp.py"

    secrets_calls = []
    for sub in ast.walk(target_fn):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
            if (
                isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "secrets"
            ):
                secrets_calls.append(sub.func.attr)
    assert "randbelow" in secrets_calls, (
        f"_generate_code() must call secrets.randbelow; saw secrets.{secrets_calls!r}"
    )


# ---------- Constants sanity ----------

def test_otp_length_constant_is_six():
    otp = _import_otp()
    assert otp.OTP_LENGTH == 6


def test_otp_ttl_is_short_enough():
    """NIST SP 800-63B §5.1.3.2: OTPs SHOULD have a lifetime ≤ 10 minutes."""
    otp = _import_otp()
    assert 1 <= otp.OTP_TTL_MIN <= 10, (
        f"OTP TTL of {otp.OTP_TTL_MIN}m violates NIST SP 800-63B §5.1.3.2 (≤10m)"
    )
