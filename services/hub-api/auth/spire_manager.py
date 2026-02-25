"""SPIRE registration entry manager for Tobogganing hub-api.

Manages SPIFFE workload entries — creates/deletes entries via SPIRE Server
Registration API and stores metadata in the local DB (spiffe_entries table).

This module is only active when SPIRE is deployed (on-prem/bare-metal fallback).
Cloud-native workload identity (EKS Pod Identity, GCP WI, Azure WI) takes
precedence when available.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

from .scopes import expand_role_to_scopes

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SPIFFE identity DTOs
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SpiffeIdentity:
    """Structured representation of a SPIFFE workload identity URI.

    The canonical SPIFFE ID for Tobogganing follows the path convention:
        spiffe://<trust_domain>/<cluster>/<namespace>/<service>
    """

    trust_domain: str
    cluster: str
    namespace: str
    service: str

    @property
    def spiffe_id(self) -> str:
        """Return the full SPIFFE URI for this identity."""
        return (
            f"spiffe://{self.trust_domain}"
            f"/{self.cluster}/{self.namespace}/{self.service}"
        )


@dataclass(slots=True)
class RegistrationEntry:
    """A SPIRE registration entry to be created or returned from the DB.

    Attributes:
        spiffe_id:  Full SPIFFE URI for the workload.
        parent_id:  SPIFFE URI of the parent node/agent entry.
        selectors:  List of selector dicts, e.g.
                    ``[{"type": "k8s:pod-label", "value": "app:api"}]``.
        ttl:        X.509-SVID TTL in seconds; 0 means use the server default.
        dns_names:  Optional DNS SANs to include in the X.509-SVID.
        tenant_id:  Tobogganing tenant this entry belongs to.
    """

    spiffe_id: str
    parent_id: str
    selectors: list[dict]
    ttl: int
    dns_names: list[str]
    tenant_id: str


# ---------------------------------------------------------------------------
# Module-level parse helper
# ---------------------------------------------------------------------------


def parse_spiffe_id(spiffe_id: str) -> SpiffeIdentity | None:
    """Parse a SPIFFE URI into a :class:`SpiffeIdentity` dataclass.

    Expected format::

        spiffe://<trust_domain>/<cluster>/<namespace>/<service>

    Args:
        spiffe_id: A string such as
            ``"spiffe://acme.tobogganing.io/aws-us-east-1/backend/api-server"``.

    Returns:
        A :class:`SpiffeIdentity` on success, or ``None`` if the URI does not
        match the expected four-segment path format.
    """
    if not spiffe_id or not spiffe_id.startswith("spiffe://"):
        log.debug("parse_spiffe_id.invalid_scheme", spiffe_id=spiffe_id)
        return None

    # Strip the scheme prefix and split on "/"
    # e.g. "acme.tobogganing.io/aws-us-east-1/backend/api-server"
    remainder = spiffe_id[len("spiffe://"):]
    parts = remainder.split("/")

    if len(parts) != 4:  # noqa: PLR2004
        log.debug(
            "parse_spiffe_id.wrong_segment_count",
            spiffe_id=spiffe_id,
            segment_count=len(parts),
        )
        return None

    trust_domain, cluster, namespace, service = parts

    if not all([trust_domain, cluster, namespace, service]):
        log.debug("parse_spiffe_id.empty_segment", spiffe_id=spiffe_id)
        return None

    return SpiffeIdentity(
        trust_domain=trust_domain,
        cluster=cluster,
        namespace=namespace,
        service=service,
    )


# ---------------------------------------------------------------------------
# SpireManager
# ---------------------------------------------------------------------------


class SpireManager:
    """Manages SPIRE registration entries for Tobogganing workloads.

    Calls the SPIRE Server Registration API (gRPC) to create and delete
    entries, and persists metadata to the ``spiffe_entries`` PyDAL table for
    tenant-scoped listing and scope mapping.

    Note:
        gRPC transport is stubbed with TODO markers.  Actual wire calls
        require the ``spiffe-api`` Python package and generated proto stubs
        (``github.com/spiffe/spire-api-sdk``).  HTTP placeholders document
        the equivalent REST surface for reference.
    """

    def __init__(self, spire_server_url: str, db: Any = None) -> None:
        """Initialise the manager.

        Args:
            spire_server_url: Base URL / gRPC address of the SPIRE Server, e.g.
                ``"https://spire-server.spire.svc.cluster.local:8081"`` or
                ``"spire-server.spire.svc.cluster.local:443"``.
            db: Optional PyDAL ``DAL`` instance.  When provided, all entry
                metadata is persisted to ``spiffe_entries``.  When ``None``,
                only the SPIRE Server API is called (no local state).
        """
        self._url = spire_server_url.rstrip("/")
        self._db = db
        self._log = log.bind(component="SpireManager", spire_server=self._url)

    # ------------------------------------------------------------------
    # Public async interface
    # ------------------------------------------------------------------

    async def create_registration_entry(self, entry: RegistrationEntry) -> str:
        """Create a SPIRE registration entry and persist it to the DB.

        Calls the SPIRE Server Registration API to register the workload
        identity, then writes the entry metadata to the ``spiffe_entries``
        table so it can be listed and managed within Tobogganing.

        Args:
            entry: The :class:`RegistrationEntry` to create.

        Returns:
            The SPIRE entry ID string returned by the server (UUID format).

        Raises:
            RuntimeError: If the SPIRE Server returns a non-success response.
            ValueError: If *entry* contains invalid or missing fields.
        """
        if not entry.spiffe_id:
            raise ValueError("RegistrationEntry.spiffe_id must not be empty")
        if not entry.parent_id:
            raise ValueError("RegistrationEntry.parent_id must not be empty")
        if not entry.tenant_id:
            raise ValueError("RegistrationEntry.tenant_id must not be empty")

        bound = self._log.bind(
            spiffe_id=entry.spiffe_id, tenant_id=entry.tenant_id
        )
        bound.info("create_registration_entry.start")

        # TODO: Replace HTTP stub with gRPC call via spiffe-api SDK.
        #
        # gRPC endpoint:
        #   service Registration (spire/api/registration/v1/registration.proto)
        #   rpc CreateEntry(CreateEntryRequest) -> CreateEntryResponse
        #
        # HTTP equivalent (SPIRE Server API v1):
        #   POST {spire_server_url}/spiffe/v1/entries
        #   Body: {
        #       "spiffe_id": {"trust_domain": "...", "path": "/cluster/ns/svc"},
        #       "parent_id": {"trust_domain": "...", "path": "..."},
        #       "selectors": [{"type": "...", "value": "..."}],
        #       "ttl": <int>,
        #       "dns_names": ["..."],
        #   }
        #   Response: {"id": "<entry-uuid>"}
        #
        # Example (aiohttp):
        #   async with aiohttp.ClientSession() as session:
        #       resp = await session.post(
        #           f"{self._url}/spiffe/v1/entries",
        #           json=payload,
        #           ssl=tls_context,
        #       )
        #       resp.raise_for_status()
        #       data = await resp.json()
        #       spire_entry_id = data["id"]

        # Stub: generate a deterministic placeholder entry ID for non-wired env.
        spire_entry_id = str(uuid.uuid4())
        bound.info(
            "create_registration_entry.spire_response",
            entry_id=spire_entry_id,
        )

        # Persist to DB if a DAL instance was provided.
        if self._db is not None:
            self._upsert_db_entry(entry, spire_entry_id)

        bound.info("create_registration_entry.done", entry_id=spire_entry_id)
        return spire_entry_id

    async def delete_registration_entry(self, spiffe_id: str) -> bool:
        """Delete a SPIRE registration entry by SPIFFE ID.

        Removes the entry from SPIRE Server and from the local ``spiffe_entries``
        table.  If no matching entry exists in the DB the deletion is still
        attempted against SPIRE (the remote state is authoritative).

        Args:
            spiffe_id: Full SPIFFE URI of the entry to delete.

        Returns:
            ``True`` if the entry was successfully removed, ``False`` if no
            matching entry was found in the DB (SPIRE call is still attempted).
        """
        if not spiffe_id:
            raise ValueError("spiffe_id must not be empty")

        bound = self._log.bind(spiffe_id=spiffe_id)
        bound.info("delete_registration_entry.start")

        # Resolve local DB record first so we have the SPIRE entry ID.
        spire_entry_id: str | None = None
        found_in_db = False

        if self._db is not None:
            row = self._db(
                self._db.spiffe_entries.spiffe_id == spiffe_id
            ).select(
                self._db.spiffe_entries.id,
                self._db.spiffe_entries.spiffe_id,
            ).first()

            if row is not None:
                found_in_db = True
                # The SPIRE server-side entry ID is not stored separately;
                # we use the SPIFFE ID as the stable identifier for the
                # lookup when calling gRPC.
                spire_entry_id = spiffe_id

        # TODO: Replace stub with gRPC call via spiffe-api SDK.
        #
        # gRPC endpoint:
        #   service Registration (spire/api/registration/v1/registration.proto)
        #   rpc DeleteEntry(DeleteEntryRequest) -> DeleteEntryResponse
        #
        # HTTP equivalent:
        #   DELETE {spire_server_url}/spiffe/v1/entries/<entry_id>
        #
        # Example (aiohttp):
        #   async with aiohttp.ClientSession() as session:
        #       resp = await session.delete(
        #           f"{self._url}/spiffe/v1/entries/{spire_entry_id}",
        #           ssl=tls_context,
        #       )
        #       resp.raise_for_status()

        bound.info(
            "delete_registration_entry.spire_call_stub",
            spire_entry_id=spire_entry_id,
        )

        # Remove from local DB.
        if self._db is not None and found_in_db:
            self._db(
                self._db.spiffe_entries.spiffe_id == spiffe_id
            ).delete()
            self._db.commit()
            bound.info("delete_registration_entry.db_deleted")

        bound.info("delete_registration_entry.done", found_in_db=found_in_db)
        return found_in_db

    async def list_entries(self, tenant_id: str) -> list[RegistrationEntry]:
        """Return all SPIFFE entries belonging to *tenant_id* from the DB.

        This is a local-DB query; it does not round-trip to the SPIRE Server.
        Use the SPIRE Server Admin API directly for the authoritative list.

        Args:
            tenant_id: Tobogganing tenant identifier to filter by.

        Returns:
            A list of :class:`RegistrationEntry` objects (may be empty).
        """
        if not tenant_id:
            raise ValueError("tenant_id must not be empty")

        bound = self._log.bind(tenant_id=tenant_id)
        bound.debug("list_entries.start")

        if self._db is None:
            bound.warning("list_entries.no_db")
            return []

        rows = self._db(
            self._db.spiffe_entries.tenant_id == tenant_id
        ).select(
            self._db.spiffe_entries.ALL,
        )

        entries: list[RegistrationEntry] = []
        for row in rows:
            entries.append(
                RegistrationEntry(
                    spiffe_id=row.spiffe_id,
                    parent_id=row.parent_id or "",
                    selectors=row.selectors or [],
                    ttl=row.ttl or 0,
                    dns_names=row.dns_names or [],
                    tenant_id=row.tenant_id,
                )
            )

        bound.debug("list_entries.done", count=len(entries))
        return entries

    async def get_entry(self, spiffe_id: str) -> RegistrationEntry | None:
        """Look up a single SPIFFE entry by its full SPIFFE URI.

        Performs a local-DB lookup only.  Returns ``None`` if the entry is not
        recorded in the local ``spiffe_entries`` table.

        Args:
            spiffe_id: Full SPIFFE URI to look up.

        Returns:
            A :class:`RegistrationEntry` on success, or ``None``.
        """
        if not spiffe_id:
            raise ValueError("spiffe_id must not be empty")

        bound = self._log.bind(spiffe_id=spiffe_id)
        bound.debug("get_entry.start")

        if self._db is None:
            bound.warning("get_entry.no_db")
            return None

        row = self._db(
            self._db.spiffe_entries.spiffe_id == spiffe_id
        ).select(self._db.spiffe_entries.ALL).first()

        if row is None:
            bound.debug("get_entry.not_found")
            return None

        entry = RegistrationEntry(
            spiffe_id=row.spiffe_id,
            parent_id=row.parent_id or "",
            selectors=row.selectors or [],
            ttl=row.ttl or 0,
            dns_names=row.dns_names or [],
            tenant_id=row.tenant_id,
        )
        bound.debug("get_entry.found")
        return entry

    def map_spiffe_to_scopes(
        self,
        spiffe_id: str,
        db: Any = None,
    ) -> list[str]:
        """Map a SPIFFE ID to Tobogganing scopes via the identity_mappings table.

        Resolution order:

        1. Parse the SPIFFE URI into path segments
           (trust_domain / cluster / namespace / service).
        2. Query ``identity_mappings`` where ``provider_type = 'spiffe'``
           and ``external_id = spiffe_id``.
        3. If a direct mapping row is found, return its ``scopes`` list.
        4. If the mapping row references a ``team_id``, also call
           :func:`~auth.scopes.expand_role_to_scopes` for the team-layer
           scopes and merge them.
        5. If no mapping row exists, return an empty list — SPIFFE identity
           alone does not grant scopes without an explicit mapping.

        Args:
            spiffe_id: Full SPIFFE URI of the workload.
            db:        Optional PyDAL ``DAL`` instance.  When ``None`` the
                       instance-level ``self._db`` is used.

        Returns:
            A deduplicated list of scope strings, e.g.
            ``["policies:read", "clusters:read"]``.
        """
        effective_db = db if db is not None else self._db
        bound = self._log.bind(spiffe_id=spiffe_id)

        identity = parse_spiffe_id(spiffe_id)
        if identity is None:
            bound.warning("map_spiffe_to_scopes.parse_failed")
            return []

        bound = bound.bind(
            trust_domain=identity.trust_domain,
            cluster=identity.cluster,
            namespace=identity.namespace,
            service=identity.service,
        )

        if effective_db is None:
            bound.warning("map_spiffe_to_scopes.no_db")
            return []

        # Query identity_mappings for a SPIFFE provider row.
        row = effective_db(
            (effective_db.identity_mappings.provider_type == "spiffe")
            & (effective_db.identity_mappings.external_id == spiffe_id)
        ).select(effective_db.identity_mappings.ALL).first()

        if row is None:
            bound.debug("map_spiffe_to_scopes.no_mapping_found")
            return []

        # Collect direct scopes from the mapping row.
        raw_scopes = row.scopes
        if isinstance(raw_scopes, list):
            direct_scopes: list[str] = list(raw_scopes)
        elif isinstance(raw_scopes, str):
            direct_scopes = [s for s in raw_scopes.split(" ") if s]
        else:
            direct_scopes = []

        # If the mapping is team-scoped, merge team-layer role scopes.
        team_scopes: list[str] = []
        team_id = getattr(row, "team_id", None)
        if team_id:
            team_row = effective_db(
                effective_db.teams.team_id == team_id
            ).select(effective_db.teams.ALL).first()

            if team_row is not None:
                # Use the team name as the "role" key for expand_role_to_scopes.
                # Teams without an explicit role default to "viewer" at team layer.
                team_role = getattr(team_row, "role", "viewer")
                team_scopes = expand_role_to_scopes(
                    role=team_role,
                    layer="team",
                    db=effective_db,
                )
                bound.debug(
                    "map_spiffe_to_scopes.team_scopes_merged",
                    team_id=team_id,
                    team_role=team_role,
                    count=len(team_scopes),
                )

        # Deduplicate while preserving insertion order.
        seen: set[str] = set()
        merged: list[str] = []
        for scope in direct_scopes + team_scopes:
            if scope not in seen:
                seen.add(scope)
                merged.append(scope)

        bound.debug("map_spiffe_to_scopes.done", scope_count=len(merged))
        return merged

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _upsert_db_entry(
        self, entry: RegistrationEntry, _spire_entry_id: str
    ) -> None:
        """Insert or update a ``spiffe_entries`` row for *entry*.

        Uses PyDAL's ``update_or_insert`` pattern: update if an existing row
        matches on ``spiffe_id``, otherwise insert a new row.

        Args:
            entry:           The registration entry to persist.
            _spire_entry_id: SPIRE server-assigned entry ID (logged only;
                             stored implicitly via the unique ``spiffe_id``).
        """
        db = self._db
        existing = db(
            db.spiffe_entries.spiffe_id == entry.spiffe_id
        ).select(db.spiffe_entries.id).first()

        fields: dict[str, Any] = {
            "parent_id": entry.parent_id,
            "selectors": entry.selectors,
            "ttl": entry.ttl,
            "dns_names": entry.dns_names,
            "tenant_id": entry.tenant_id,
        }

        if existing is not None:
            db(db.spiffe_entries.id == existing.id).update(**fields)
            self._log.debug(
                "spiffe_entries.updated",
                spiffe_id=entry.spiffe_id,
                row_id=existing.id,
            )
        else:
            row_id = db.spiffe_entries.insert(
                spiffe_id=entry.spiffe_id,
                **fields,
            )
            self._log.debug(
                "spiffe_entries.inserted",
                spiffe_id=entry.spiffe_id,
                row_id=row_id,
            )

        db.commit()
