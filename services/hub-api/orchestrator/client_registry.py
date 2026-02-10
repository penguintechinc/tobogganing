import asyncio
import json
import secrets
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
import structlog
from dataclasses import dataclass, asdict
import aioredis
import hashlib

logger = structlog.get_logger()

@dataclass
class Client:
    id: str
    name: str
    type: str  # 'docker' or 'native'
    cluster_id: str
    api_key_hash: str
    public_key: str
    ip_address: str
    status: str
    created_at: datetime
    last_seen: datetime
    metadata: Dict

class ClientRegistry:
    def __init__(self):
        self.clients: Dict[str, Client] = {}
        self.api_keys: Dict[str, str] = {}  # api_key_hash -> client_id
        self.redis: Optional[aioredis.Redis] = None
        self.cleanup_interval = 300  # 5 minutes
        self._lock = asyncio.Lock()
        
    async def initialize(self):
        try:
            self.redis = await aioredis.from_url(
                "redis://localhost",
                encoding="utf-8",
                decode_responses=True
            )
            await self._load_clients()
            logger.info("ClientRegistry initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ClientRegistry: {e}")
            raise
    
    async def shutdown(self):
        if self.redis:
            await self.redis.close()
        logger.info("ClientRegistry shutdown complete")
    
    async def register_client(self, client_data: Dict) -> tuple[Client, str]:
        api_key = secrets.token_urlsafe(32)
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        async with self._lock:
            client = Client(
                id=client_data['id'],
                name=client_data['name'],
                type=client_data['type'],
                cluster_id=client_data['cluster_id'],
                api_key_hash=api_key_hash,
                public_key=client_data['public_key'],
                ip_address=client_data.get('ip_address', ''),
                status='pending',
                created_at=datetime.now(),
                last_seen=datetime.now(),
                metadata=client_data.get('metadata', {})
            )
            
            self.clients[client.id] = client
            self.api_keys[api_key_hash] = client.id
            
            if self.redis:
                await self.redis.hset(
                    "clients",
                    client.id,
                    json.dumps(asdict(client), default=str)
                )
                await self.redis.setex(
                    f"api_key:{api_key_hash}",
                    3600,  # 1 hour expiry for initial setup
                    client.id
                )
            
            logger.info(f"Registered client: {client.id} type: {client.type}")
            return client, api_key
    
    async def authenticate_client(self, api_key: str) -> Optional[Client]:
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        client_id = self.api_keys.get(api_key_hash)
        if not client_id and self.redis:
            client_id = await self.redis.get(f"api_key:{api_key_hash}")
        
        if client_id and client_id in self.clients:
            client = self.clients[client_id]
            client.last_seen = datetime.now()
            client.status = 'active'
            
            if self.redis:
                await self.redis.hset(
                    "clients",
                    client.id,
                    json.dumps(asdict(client), default=str)
                )
            
            return client
        
        return None
    
    async def update_client_status(self, client_id: str, status: str, metadata: Dict = None):
        async with self._lock:
            if client_id in self.clients:
                client = self.clients[client_id]
                client.status = status
                client.last_seen = datetime.now()
                
                if metadata:
                    client.metadata.update(metadata)
                
                if self.redis:
                    await self.redis.hset(
                        "clients",
                        client_id,
                        json.dumps(asdict(client), default=str)
                    )
                
                return True
            return False
    
    async def get_client(self, client_id: str) -> Optional[Client]:
        return self.clients.get(client_id)
    
    async def get_all_clients(self) -> List[Client]:
        return list(self.clients.values())
    
    async def get_clients_by_cluster(self, cluster_id: str) -> List[Client]:
        return [c for c in self.clients.values() if c.cluster_id == cluster_id]
    
    async def get_clients_by_type(self, client_type: str) -> List[Client]:
        return [c for c in self.clients.values() if c.type == client_type]
    
    async def remove_client(self, client_id: str) -> bool:
        async with self._lock:
            if client_id in self.clients:
                client = self.clients[client_id]
                
                # Remove API key mapping
                self.api_keys = {k: v for k, v in self.api_keys.items() if v != client_id}
                
                del self.clients[client_id]
                
                if self.redis:
                    await self.redis.hdel("clients", client_id)
                    # Clean up any remaining API keys
                    api_keys = await self.redis.keys(f"api_key:*")
                    for key in api_keys:
                        if await self.redis.get(key) == client_id:
                            await self.redis.delete(key)
                
                logger.info(f"Removed client: {client_id}")
                return True
            return False
    
    async def cleanup_expired(self):
        while True:
            try:
                await self._cleanup_stale_clients()
                await asyncio.sleep(self.cleanup_interval)
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                await asyncio.sleep(30)
    
    async def _cleanup_stale_clients(self):
        stale_threshold = datetime.now() - timedelta(hours=24)
        
        async with self._lock:
            stale_clients = [
                client_id for client_id, client in self.clients.items()
                if client.last_seen < stale_threshold and client.status != 'active'
            ]
            
            for client_id in stale_clients:
                await self.remove_client(client_id)
                logger.info(f"Cleaned up stale client: {client_id}")
    
    async def _load_clients(self):
        if not self.redis:
            return
        
        clients_data = await self.redis.hgetall("clients")
        for client_id, client_json in clients_data.items():
            client_dict = json.loads(client_json)
            client_dict['created_at'] = datetime.fromisoformat(client_dict['created_at'])
            client_dict['last_seen'] = datetime.fromisoformat(client_dict['last_seen'])
            
            client = Client(**client_dict)
            self.clients[client_id] = client
            self.api_keys[client.api_key_hash] = client_id
        
        logger.info(f"Loaded {len(self.clients)} clients from Redis")
    
    async def get_client_count(self) -> int:
        return len(self.clients)
    
    async def is_healthy(self) -> bool:
        try:
            if self.redis:
                await self.redis.ping()
            return True
        except:
            return False
    
    async def rotate_api_key(self, client_id: str) -> Optional[str]:
        if client_id not in self.clients:
            return None
        
        new_api_key = secrets.token_urlsafe(32)
        new_api_key_hash = hashlib.sha256(new_api_key.encode()).hexdigest()
        
        async with self._lock:
            client = self.clients[client_id]
            
            # Remove old API key
            self.api_keys = {k: v for k, v in self.api_keys.items() if v != client_id}
            
            # Set new API key
            client.api_key_hash = new_api_key_hash
            self.api_keys[new_api_key_hash] = client_id
            
            if self.redis:
                await self.redis.hset(
                    "clients",
                    client_id,
                    json.dumps(asdict(client), default=str)
                )
                # Set temporary key for rotation
                await self.redis.setex(
                    f"api_key:{new_api_key_hash}",
                    3600,  # 1 hour to complete rotation
                    client_id
                )
            
            logger.info(f"Rotated API key for client: {client_id}")
            return new_api_key