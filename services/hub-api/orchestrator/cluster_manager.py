import asyncio
import json
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
import structlog
from dataclasses import dataclass, asdict
import aioredis

logger = structlog.get_logger()

@dataclass
class Cluster:
    id: str
    name: str
    region: str
    datacenter: str
    headend_url: str
    status: str
    last_heartbeat: datetime
    client_count: int
    metadata: Dict

class ClusterManager:
    def __init__(self):
        self.clusters: Dict[str, Cluster] = {}
        self.redis: Optional[aioredis.Redis] = None
        self.health_check_interval = 30
        self._lock = asyncio.Lock()
        
    async def initialize(self):
        try:
            self.redis = await aioredis.from_url(
                "redis://localhost",
                encoding="utf-8",
                decode_responses=True
            )
            await self._load_clusters()
            logger.info("ClusterManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ClusterManager: {e}")
            raise
    
    async def shutdown(self):
        if self.redis:
            await self.redis.close()
        logger.info("ClusterManager shutdown complete")
    
    async def register_cluster(self, cluster_data: Dict) -> Cluster:
        async with self._lock:
            cluster = Cluster(
                id=cluster_data['id'],
                name=cluster_data['name'],
                region=cluster_data['region'],
                datacenter=cluster_data['datacenter'],
                headend_url=cluster_data['headend_url'],
                status='active',
                last_heartbeat=datetime.now(),
                client_count=0,
                metadata=cluster_data.get('metadata', {})
            )
            
            self.clusters[cluster.id] = cluster
            
            if self.redis:
                await self.redis.hset(
                    "clusters",
                    cluster.id,
                    json.dumps(asdict(cluster), default=str)
                )
            
            logger.info(f"Registered cluster: {cluster.id} in {cluster.region}/{cluster.datacenter}")
            return cluster
    
    async def update_heartbeat(self, cluster_id: str, client_count: int = None):
        async with self._lock:
            if cluster_id in self.clusters:
                cluster = self.clusters[cluster_id]
                cluster.last_heartbeat = datetime.now()
                cluster.status = 'active'
                
                if client_count is not None:
                    cluster.client_count = client_count
                
                if self.redis:
                    await self.redis.hset(
                        "clusters",
                        cluster_id,
                        json.dumps(asdict(cluster), default=str)
                    )
                
                return True
            return False
    
    async def get_cluster(self, cluster_id: str) -> Optional[Cluster]:
        return self.clusters.get(cluster_id)
    
    async def get_all_clusters(self) -> List[Cluster]:
        return list(self.clusters.values())
    
    async def get_clusters_by_region(self, region: str) -> List[Cluster]:
        return [c for c in self.clusters.values() if c.region == region]
    
    async def get_clusters_by_datacenter(self, datacenter: str) -> List[Cluster]:
        return [c for c in self.clusters.values() if c.datacenter == datacenter]
    
    async def remove_cluster(self, cluster_id: str) -> bool:
        async with self._lock:
            if cluster_id in self.clusters:
                del self.clusters[cluster_id]
                
                if self.redis:
                    await self.redis.hdel("clusters", cluster_id)
                
                logger.info(f"Removed cluster: {cluster_id}")
                return True
            return False
    
    async def monitor_health(self):
        while True:
            try:
                await self._check_cluster_health()
                await asyncio.sleep(self.health_check_interval)
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(5)
    
    async def _check_cluster_health(self):
        stale_threshold = datetime.now() - timedelta(minutes=5)
        
        async with self._lock:
            for cluster_id, cluster in list(self.clusters.items()):
                if cluster.last_heartbeat < stale_threshold:
                    if cluster.status == 'active':
                        cluster.status = 'stale'
                        logger.warning(f"Cluster {cluster_id} marked as stale")
                        
                        if self.redis:
                            await self.redis.hset(
                                "clusters",
                                cluster_id,
                                json.dumps(asdict(cluster), default=str)
                            )
    
    async def _load_clusters(self):
        if not self.redis:
            return
        
        clusters_data = await self.redis.hgetall("clusters")
        for cluster_id, cluster_json in clusters_data.items():
            cluster_dict = json.loads(cluster_json)
            cluster_dict['last_heartbeat'] = datetime.fromisoformat(cluster_dict['last_heartbeat'])
            
            self.clusters[cluster_id] = Cluster(**cluster_dict)
        
        logger.info(f"Loaded {len(self.clusters)} clusters from Redis")
    
    async def get_cluster_count(self) -> int:
        return len(self.clusters)
    
    async def is_healthy(self) -> bool:
        try:
            if self.redis:
                await self.redis.ping()
            return True
        except:
            return False
    
    async def get_optimal_cluster(self, client_location: Dict) -> Optional[Cluster]:
        region = client_location.get('region')
        datacenter = client_location.get('datacenter')
        
        candidates = []
        
        if datacenter:
            candidates = await self.get_clusters_by_datacenter(datacenter)
        
        if not candidates and region:
            candidates = await self.get_clusters_by_region(region)
        
        if not candidates:
            candidates = await self.get_all_clusters()
        
        active_candidates = [c for c in candidates if c.status == 'active']
        
        if not active_candidates:
            return None
        
        return min(active_candidates, key=lambda c: c.client_count)