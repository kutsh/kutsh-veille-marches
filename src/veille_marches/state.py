"""state.py — état idempotent persistant (seen_ids / posted_ids / last_run).

Deux backends :
  - S3 (S3_BUCKET + creds) : objet JSON unique (compatible Hetzner/DECI via
    endpoint S3) — appel REST signé SigV4 en stdlib (pas de boto3).
  - Fichier local (def /data/veille-marches-state.json) : volume Coolify persistant.

Sémantique (cf. spec) :
  - seen_ids   : toutes les références déjà rencontrées (purge > 3 mois).
  - posted_ids : références déjà postées sur Basecamp — PERMANENT, jamais purgé,
                 jamais reposté.
  - last_run   : date ISO du dernier passage.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .config import Config


@dataclass
class State:
    seen_ids: list[str] = field(default_factory=list)
    posted_ids: list[str] = field(default_factory=list)
    last_run: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> State:
        return cls(
            seen_ids=list(d.get("seen_ids") or []),
            posted_ids=list(d.get("posted_ids") or []),
            last_run=d.get("last_run"),
        )

    def to_dict(self) -> dict:
        return {
            "seen_ids": sorted(set(self.seen_ids)),
            "posted_ids": sorted(set(self.posted_ids)),
            "last_run": self.last_run,
        }

    def is_new(self, stable_id: str) -> bool:
        """NOUVEAU = jamais posté (la présence dans seen_ids n'empêche pas le post)."""
        return stable_id not in set(self.posted_ids)

    def mark_seen(self, stable_id: str) -> None:
        if stable_id not in self.seen_ids:
            self.seen_ids.append(stable_id)

    def mark_posted(self, stable_id: str) -> None:
        if stable_id not in self.posted_ids:
            self.posted_ids.append(stable_id)

    def finalize(self) -> None:
        self.last_run = dt.date.today().isoformat()
        # purge seen_ids des entrées anciennes : on ne stocke pas de date par id,
        # donc on borne simplement la taille pour éviter l'accumulation infinie.
        if len(self.seen_ids) > 2000:
            self.seen_ids = self.seen_ids[-2000:]


# --------------------------------------------------------------------------- #
# Backends
# --------------------------------------------------------------------------- #
class StateStore:
    def load(self) -> State:  # pragma: no cover - interface
        raise NotImplementedError

    def save(self, state: State) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class FileStateStore(StateStore):
    def __init__(self, path: str):
        self.path = path

    def load(self) -> State:
        if not os.path.exists(self.path):
            return State()
        with open(self.path, encoding="utf-8") as f:
            return State.from_dict(json.load(f))

    def save(self, state: State) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)  # écriture atomique


class S3StateStore(StateStore):
    """Stockage S3 via REST SigV4 (stdlib, sans boto3)."""

    def __init__(self, cfg: Config):
        self.bucket = cfg.s3_bucket
        self.key = cfg.s3_key
        self.region = cfg.s3_region
        self.access = cfg.s3_access_key
        self.secret = cfg.s3_secret_key
        # endpoint type Hetzner : https://<region>.your-objectstorage.com ou custom
        self.endpoint = (cfg.s3_endpoint or f"https://s3.{self.region}.amazonaws.com").rstrip("/")
        self.timeout = cfg.request_timeout

    # --- SigV4 minimal ---
    def _sign(self, method: str, payload: bytes) -> tuple[str, dict]:
        host = self.endpoint.split("://", 1)[1]
        now = dt.datetime.now(dt.UTC)
        amzdate = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")
        canonical_uri = f"/{self.bucket}/{self.key}"
        payload_hash = hashlib.sha256(payload).hexdigest()
        canonical_headers = (
            f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amzdate}\n"
        )
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical_request = (
            f"{method}\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        )
        scope = f"{datestamp}/{self.region}/s3/aws4_request"
        string_to_sign = (
            "AWS4-HMAC-SHA256\n"
            f"{amzdate}\n{scope}\n"
            f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
        )

        def _hmac(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode(), hashlib.sha256).digest()

        kdate = _hmac(("AWS4" + self.secret).encode(), datestamp)
        kregion = _hmac(kdate, self.region)
        kservice = _hmac(kregion, "s3")
        ksigning = _hmac(kservice, "aws4_request")
        signature = hmac.new(ksigning, string_to_sign.encode(), hashlib.sha256).hexdigest()
        auth = (
            f"AWS4-HMAC-SHA256 Credential={self.access}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        headers = {
            "Authorization": auth,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amzdate,
            "Host": host,
        }
        return canonical_uri, headers

    def _url(self) -> str:
        return f"{self.endpoint}/{self.bucket}/{self.key}"

    def load(self) -> State:
        _, headers = self._sign("GET", b"")
        req = urllib.request.Request(self._url(), method="GET", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310
                return State.from_dict(json.loads(r.read()))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return State()
            raise

    def save(self, state: State) -> None:
        payload = json.dumps(state.to_dict(), indent=2, ensure_ascii=False).encode()
        _, headers = self._sign("PUT", payload)
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self._url(), data=payload, method="PUT", headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout):  # noqa: S310
            pass


def make_store(cfg: Config) -> StateStore:
    return S3StateStore(cfg) if cfg.use_s3 else FileStateStore(cfg.state_file)
