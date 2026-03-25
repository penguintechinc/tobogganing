"""gRPC policy streaming server for hub-router communication."""

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import grpc
from grpc import aio as grpc_aio
import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger()

# Since we don't have compiled proto stubs yet, define the service manually
# using grpc reflection. In production, generate stubs with grpc_tools.protoc.

POLICY_UPDATES_CHANNEL = "policy:updates"


@dataclass(slots=True)
class PolicyDTO:
    """Intermediate policy representation between PyDAL and gRPC."""

    id: int
    name: str
    description: str
    action: str
    priority: int
    scope: str
    direction: str
    domains: list
    ports: list
    protocol: str
    src_cidrs: list
    dst_cidrs: list
    users: list
    groups: list
    identity_provider: str
    enabled: bool


def _row_to_dto(row) -> PolicyDTO:
    """Convert a PyDAL Row to PolicyDTO."""
    return PolicyDTO(
        id=row.id,
        name=row.name or "",
        description=row.description or "",
        action=row.action or "allow",
        priority=row.priority or 100,
        scope=row.scope or "both",
        direction=row.direction or "both",
        domains=row.domains if isinstance(row.domains, list) else [],
        ports=row.ports if isinstance(row.ports, list) else [],
        protocol=row.protocol or "any",
        src_cidrs=row.src_cidrs if isinstance(row.src_cidrs, list) else [],
        dst_cidrs=row.dst_cidrs if isinstance(row.dst_cidrs, list) else [],
        users=row.users if isinstance(row.users, list) else [],
        groups=row.groups if isinstance(row.groups, list) else [],
        identity_provider=row.identity_provider or "local",
        enabled=bool(row.enabled),
    )


def _dto_to_dict(dto: PolicyDTO) -> dict:
    """Serialize PolicyDTO to JSON-compatible dict for gRPC response."""
    return {
        "id": str(dto.id),
        "name": dto.name,
        "description": dto.description,
        "action": dto.action,
        "priority": dto.priority,
        "scope": dto.scope,
        "direction": dto.direction,
        "domains": dto.domains,
        "ports": dto.ports,
        "protocol": dto.protocol,
        "src_cidrs": dto.src_cidrs,
        "dst_cidrs": dto.dst_cidrs,
        "users": dto.users,
        "groups": dto.groups,
        "identity_provider": dto.identity_provider,
        "enabled": dto.enabled,
    }


class PolicyServicer:
    """Implements the PolicyService gRPC service.

    Proto reference: services/hub-api/grpc/proto/policy.proto
      - FetchPolicies(FetchPoliciesRequest) -> FetchPoliciesResponse
      - SubscribePolicyUpdates(SubscribeRequest) -> stream PolicyUpdateEvent
      - RegisterHub(RegisterHubRequest) -> RegisterHubResponse
      - GetStatus(StatusRequest) -> StatusResponse
    """

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url)
        return self._redis

    async def FetchPolicies(self, request_data: dict, context) -> dict:
        """Return all enabled policies (FetchPoliciesResponse).

        Queries db.policy_rules for enabled=True rows and serializes them
        to proto-compatible dicts inside a PolicySet envelope.
        """
        from database import get_read_db
        db = get_read_db()
        rows = db(db.policy_rules.enabled == True).select(  # noqa: E712
            orderby=db.policy_rules.priority
        )
        policies = [_dto_to_dict(_row_to_dto(r)) for r in rows]
        now_ts = datetime.now(timezone.utc).isoformat()
        return {
            "policies": {
                "rules": policies,
                "version": int(datetime.now(timezone.utc).timestamp()),
                "timestamp": now_ts,
            },
            "has_changes": True,
        }

    async def SubscribePolicyUpdates(self, request_data: dict, context):
        """Server-streaming: yield PolicyUpdateEvent messages via Redis pub/sub.

        Subscribes to the Redis channel 'policy:updates' and forwards
        each published message as a PolicyUpdateEvent to the hub-router.
        """
        redis_client = await self._get_redis()
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(POLICY_UPDATES_CHANNEL)
        logger.info(
            "Hub subscribed to policy updates",
            hub_id=request_data.get("hub_id", "unknown"),
        )
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    yield {
                        "event_type": data.get("action", "updated"),
                        "rule": data.get("policy", {}),
                        "version": int(datetime.now(timezone.utc).timestamp()),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
        finally:
            await pubsub.unsubscribe(POLICY_UPDATES_CHANNEL)

    async def RegisterHub(self, request_data: dict, context) -> dict:
        """Register a hub-router instance (RegisterHubResponse).

        Stores hub metadata in Redis hash hubs:<hub_id> and returns
        the initial policy set so the hub can seed its local cache.
        """
        hub_id = request_data.get("hub_id", "")
        redis_client = await self._get_redis()
        await redis_client.hset(
            f"hubs:{hub_id}",
            mapping={
                "cluster_id": request_data.get("cluster_id", ""),
                "region": request_data.get("region", ""),
                "capacity": str(request_data.get("capacity", 0)),
                "registered_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info("Hub registered", hub_id=hub_id)

        # Fetch initial policies to include in the registration response
        initial_policies = await self.FetchPolicies({}, context)

        return {
            "success": True,
            "message": f"Hub {hub_id} registered successfully",
            "initial_policies": initial_policies.get("policies", {}),
        }

    async def GetStatus(self, request_data: dict, context) -> dict:
        """Return service health status (StatusResponse)."""
        version = "unknown"
        version_file = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", ".version"
        )
        if os.path.exists(version_file):
            with open(version_file) as f:
                version = f.read().strip()
        return {"status": "healthy", "version": version}

    async def close(self):
        """Release Redis connection."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None


async def start_grpc_server(redis_url: str, port: int = 50051) -> grpc_aio.Server:
    """Start the gRPC policy server on the given port.

    In production with compiled proto stubs you would register the servicer
    via policy_pb2_grpc.add_PolicyServiceServicer_to_server(). Until stubs
    are generated with grpc_tools.protoc, we use server reflection so that
    grpcurl / Evans can still inspect the service schema.

    Args:
        redis_url: Redis connection URL used for pub/sub and hub registration.
        port: TCP port for the gRPC listener (default 50051).

    Returns:
        The running grpc_aio.Server instance.
    """
    server = grpc_aio.server()

    servicer = PolicyServicer(redis_url=redis_url)  # noqa: F841 — registered below

    # Enable server reflection for tooling (grpcurl, Evans, etc.)
    try:
        from grpc_reflection.v1alpha import reflection, service_pb2

        SERVICE_NAMES = (
            "tobogganing.policy.v1.PolicyService",
            reflection.SERVICE_NAME,
        )
        reflection.enable_server_reflection(SERVICE_NAMES, server)
        logger.info("gRPC server reflection enabled")
    except ImportError:
        logger.warning(
            "grpcio-reflection not installed; server reflection unavailable"
        )

    # NOTE: Compiled proto stubs are not yet generated. Once you run:
    #   python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. \
    #       services/hub-api/grpc/proto/policy.proto
    # uncomment the line below and remove this notice:
    #   policy_pb2_grpc.add_PolicyServiceServicer_to_server(servicer, server)

    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    logger.info("gRPC policy server started", port=port)
    return server
