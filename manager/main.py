import asyncio
import os
import threading
from typing import Optional
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

import uvloop
from py4web import action, request, response, abort, redirect, URL
from py4web.core import app, Fixture
import structlog

from orchestrator.cluster_manager import ClusterManager
from orchestrator.client_registry import ClientRegistry
from api.routes import setup_routes
from web.routes import setup_web_routes
from certs.certificate_manager import CertificateManager
from auth.jwt_manager import JWTManager
from auth.user_manager import UserManager
from metrics.prometheus import manager_metrics

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

logger = structlog.get_logger()

cluster_manager: Optional[ClusterManager] = None
client_registry: Optional[ClientRegistry] = None
cert_manager: Optional[CertificateManager] = None
jwt_manager: Optional[JWTManager] = None
user_manager: Optional[UserManager] = None

# Thread pool for CPU-intensive operations
thread_pool = ThreadPoolExecutor(max_workers=int(os.getenv("THREAD_POOL_SIZE", 10)))

@asynccontextmanager
async def lifespan(app):
    global cluster_manager, client_registry, cert_manager, jwt_manager, user_manager
    
    logger.info("Starting SASEWaddle Manager Service with async/threading support")
    
    # Initialize core services with async/threading
    cluster_manager = ClusterManager()
    client_registry = ClientRegistry()
    cert_manager = CertificateManager()
    jwt_manager = JWTManager(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        token_expiry_hours=int(os.getenv("TOKEN_EXPIRY_HOURS", "24")),
        refresh_expiry_days=int(os.getenv("REFRESH_EXPIRY_DAYS", "7"))
    )
    user_manager = UserManager()
    
    # Initialize all services concurrently
    await asyncio.gather(
        cluster_manager.initialize(),
        client_registry.initialize(), 
        cert_manager.initialize(),
        jwt_manager.initialize()
    )
    
    # Start background tasks
    background_tasks = [
        asyncio.create_task(cluster_manager.monitor_health()),
        asyncio.create_task(client_registry.cleanup_expired()),
        asyncio.create_task(jwt_manager.cleanup_expired_tokens()),
        asyncio.create_task(user_manager.cleanup_expired_sessions()),
        asyncio.create_task(_periodic_health_check()),
        asyncio.create_task(_periodic_metrics_update())
    ]
    
    logger.info("SASEWaddle Manager Service started successfully")
    
    yield
    
    logger.info("Shutting down SASEWaddle Manager Service")
    
    # Cancel background tasks
    for task in background_tasks:
        task.cancel()
    
    # Shutdown services concurrently
    await asyncio.gather(
        cluster_manager.shutdown(),
        client_registry.shutdown(),
        cert_manager.shutdown(),
        jwt_manager.close(),
        return_exceptions=True
    )
    
    # Shutdown thread pool
    thread_pool.shutdown(wait=True)
    
    logger.info("SASEWaddle Manager Service shutdown complete")

app.on_startup.append(lifespan)

@action("index", method=["GET"])
@action.uses("json")
async def index():
    return {
        "service": "SASEWaddle Manager",
        "version": open(".version").read().strip(),
        "status": "healthy",
        "clusters": await cluster_manager.get_cluster_count() if cluster_manager else 0,
        "clients": await client_registry.get_client_count() if client_registry else 0
    }

@action("health", method=["GET"])
@action.uses("json")
async def health():
    health_status = {
        "manager": "healthy",
        "cluster_manager": "healthy" if cluster_manager and await cluster_manager.is_healthy() else "unhealthy",
        "client_registry": "healthy" if client_registry and await client_registry.is_healthy() else "unhealthy", 
        "certificate_manager": "healthy" if cert_manager and await cert_manager.is_healthy() else "unhealthy",
        "jwt_manager": "healthy" if jwt_manager else "unhealthy"
    }
    
    overall_health = all(v == "healthy" for v in health_status.values())
    
    if not overall_health:
        response.status = 503
    
    return health_status

@action("healthz", method=["GET"])
@action.uses("json")
async def healthz():
    """Kubernetes-style health endpoint"""
    health_status = await health()
    if isinstance(health_status, dict) and all(v == "healthy" for v in health_status.values()):
        return {"status": "ok"}
    else:
        response.status = 503
        return {"status": "error"}

@action("metrics", method=["GET"])
async def metrics():
    """Prometheus metrics endpoint with authentication"""
    # Check for basic auth or API key
    auth_header = request.headers.get('Authorization', '')
    
    # Allow access for Prometheus scraping with bearer token
    if auth_header.startswith('Bearer '):
        # In production, validate this token against a metrics-specific secret
        metrics_token = os.getenv('METRICS_TOKEN', 'prometheus-scraper-token')
        provided_token = auth_header[7:]
        
        if provided_token != metrics_token:
            response.status = 401
            return "Unauthorized"
    else:
        # Check for session-based auth (web portal users)
        from web.auth import get_current_user, user_manager
        user = get_current_user()
        if not user or not user_manager.has_permission(user, 'view_metrics'):
            response.status = 401
            return "Unauthorized"
    
    # Return metrics
    response.headers['Content-Type'] = manager_metrics.get_content_type()
    return manager_metrics.get_metrics()

async def _periodic_health_check():
    """Background task for periodic health monitoring"""
    while True:
        try:
            await asyncio.sleep(30)  # Check every 30 seconds
            
            # Log health status periodically
            if cluster_manager and client_registry and cert_manager and jwt_manager:
                active_clusters = await cluster_manager.get_cluster_count()
                active_clients = await client_registry.get_client_count() 
                
                logger.info("Health check", 
                           clusters=active_clusters,
                           clients=active_clients,
                           threads_active=threading.active_count())
            
        except asyncio.CancelledError:
            logger.info("Health check task cancelled")
            break
        except Exception as e:
            logger.error("Health check failed", error=str(e))

async def _periodic_metrics_update():
    """Background task for updating Prometheus metrics"""
    while True:
        try:
            await asyncio.sleep(60)  # Update every minute
            
            # Update metrics with current stats
            if cluster_manager and client_registry:
                # Cluster stats
                clusters = await cluster_manager.get_all_clusters()
                cluster_count = len(clusters)
                cluster_status_counts = {}
                for cluster in clusters:
                    status = cluster.status
                    cluster_status_counts[status] = cluster_status_counts.get(status, 0) + 1
                
                manager_metrics.update_cluster_stats(cluster_count, cluster_status_counts)
                
                # Client stats  
                clients = await client_registry.get_all_clients()
                client_count = len(clients)
                client_type_counts = {}
                client_status_counts = {}
                for client in clients:
                    client_type = client.type
                    client_status = client.status
                    client_type_counts[client_type] = client_type_counts.get(client_type, 0) + 1
                    client_status_counts[client_status] = client_status_counts.get(client_status, 0) + 1
                
                manager_metrics.update_client_stats(client_count, client_type_counts, client_status_counts)
            
            # Update system resources
            try:
                import psutil
                memory = psutil.virtual_memory()
                cpu_percent = psutil.cpu_percent(interval=1)
                manager_metrics.update_system_resources(memory.used, cpu_percent)
            except ImportError:
                # psutil not available
                pass
            
        except asyncio.CancelledError:
            logger.info("Metrics update task cancelled")
            break
        except Exception as e:
            logger.error("Metrics update failed", error=str(e))

# Utility function for CPU-intensive operations
async def run_in_thread(func, *args, **kwargs):
    """Run CPU-intensive operations in thread pool"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(thread_pool, func, *args, **kwargs)

setup_routes(app, cluster_manager, client_registry, cert_manager, jwt_manager)
setup_web_routes(app, cluster_manager, client_registry, cert_manager, jwt_manager)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        workers=int(os.getenv("WORKERS", 4)),
        loop="uvloop",
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        access_log=True
    )