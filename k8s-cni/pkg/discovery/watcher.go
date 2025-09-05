// Package discovery provides Kubernetes resource discovery and monitoring
// with comprehensive event handling and caching capabilities.
package discovery

import (
	"context"
	"fmt"
	"net"
	"sync"
	"time"

	"github.com/sirupsen/logrus"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/fields"
	"k8s.io/apimachinery/pkg/labels"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/watch"
	"k8s.io/client-go/informers"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/cache"
	"k8s.io/client-go/rest"
)

// Watcher provides comprehensive Kubernetes resource discovery and monitoring
type Watcher struct {
	logger *logrus.Entry
	config *WatcherConfiguration

	// Kubernetes clients
	clientset     kubernetes.Interface
	restClient    rest.Interface
	informerFactory informers.SharedInformerFactory

	// Informers for different resource types
	podInformer       cache.SharedIndexInformer
	namespaceInformer cache.SharedIndexInformer
	serviceInformer   cache.SharedIndexInformer
	endpointInformer  cache.SharedIndexInformer
	nodeInformer      cache.SharedIndexInformer

	// Event handling
	eventHandlers []EventHandler
	eventChannel  chan *ResourceEvent

	// Resource cache
	cache Cache
	stats *CacheStats

	// Synchronization
	mu      sync.RWMutex
	ctx     context.Context
	cancel  context.CancelFunc
	wg      sync.WaitGroup
	started bool
}

// NewWatcher creates a new Kubernetes resource watcher
func NewWatcher(config *WatcherConfiguration, kubeConfig *rest.Config, cache Cache) (*Watcher, error) {
	if config == nil {
		config = &WatcherConfiguration{
			ResyncPeriod:         30 * time.Second,
			BufferSize:           1000,
			WorkerCount:          4,
			RetryBackoff:         1 * time.Second,
			MaxRetries:           5,
			EnablePodWatch:       true,
			EnableNamespaceWatch: true,
			EnableServiceWatch:   true,
			EnableEndpointWatch:  true,
			EnableNodeWatch:      true,
			EventBufferSize:      10000,
			EventBatchSize:       100,
			EventProcessingDelay: 100 * time.Millisecond,
		}
	}

	// Create Kubernetes clientset
	clientset, err := kubernetes.NewForConfig(kubeConfig)
	if err != nil {
		return nil, fmt.Errorf("failed to create kubernetes clientset: %w", err)
	}

	// Create informer factory
	var informerFactory informers.SharedInformerFactory
	if len(config.Namespaces) > 0 {
		// Namespace-scoped informers for better performance
		informerFactory = informers.NewSharedInformerFactory(clientset, config.ResyncPeriod)
	} else {
		// Cluster-wide informers
		informerFactory = informers.NewSharedInformerFactory(clientset, config.ResyncPeriod)
	}

	logger := logrus.WithField("component", "discovery-watcher")
	ctx, cancel := context.WithCancel(context.Background())

	watcher := &Watcher{
		logger:          logger,
		config:          config,
		clientset:       clientset,
		informerFactory: informerFactory,
		eventHandlers:   make([]EventHandler, 0),
		eventChannel:    make(chan *ResourceEvent, config.EventBufferSize),
		cache:           cache,
		ctx:             ctx,
		cancel:          cancel,
		stats: &CacheStats{
			APIServerConnected: true,
		},
	}

	// Initialize informers
	if err := watcher.initializeInformers(); err != nil {
		return nil, fmt.Errorf("failed to initialize informers: %w", err)
	}

	return watcher, nil
}

// initializeInformers sets up Kubernetes informers for different resource types
func (w *Watcher) initializeInformers() error {
	// Pod informer
	if w.config.EnablePodWatch {
		w.podInformer = w.informerFactory.Core().V1().Pods().Informer()
		if _, err := w.podInformer.AddEventHandler(cache.ResourceEventHandlerFuncs{
			AddFunc:    w.handlePodAdd,
			UpdateFunc: w.handlePodUpdate,
			DeleteFunc: w.handlePodDelete,
		}); err != nil {
			return fmt.Errorf("failed to add pod event handler: %w", err)
		}
	}

	// Namespace informer
	if w.config.EnableNamespaceWatch {
		w.namespaceInformer = w.informerFactory.Core().V1().Namespaces().Informer()
		if _, err := w.namespaceInformer.AddEventHandler(cache.ResourceEventHandlerFuncs{
			AddFunc:    w.handleNamespaceAdd,
			UpdateFunc: w.handleNamespaceUpdate,
			DeleteFunc: w.handleNamespaceDelete,
		}); err != nil {
			return fmt.Errorf("failed to add namespace event handler: %w", err)
		}
	}

	// Service informer
	if w.config.EnableServiceWatch {
		w.serviceInformer = w.informerFactory.Core().V1().Services().Informer()
		if _, err := w.serviceInformer.AddEventHandler(cache.ResourceEventHandlerFuncs{
			AddFunc:    w.handleServiceAdd,
			UpdateFunc: w.handleServiceUpdate,
			DeleteFunc: w.handleServiceDelete,
		}); err != nil {
			return fmt.Errorf("failed to add service event handler: %w", err)
		}
	}

	// Endpoint informer
	if w.config.EnableEndpointWatch {
		w.endpointInformer = w.informerFactory.Core().V1().Endpoints().Informer()
		if _, err := w.endpointInformer.AddEventHandler(cache.ResourceEventHandlerFuncs{
			AddFunc:    w.handleEndpointAdd,
			UpdateFunc: w.handleEndpointUpdate,
			DeleteFunc: w.handleEndpointDelete,
		}); err != nil {
			return fmt.Errorf("failed to add endpoint event handler: %w", err)
		}
	}

	// Node informer
	if w.config.EnableNodeWatch {
		w.nodeInformer = w.informerFactory.Core().V1().Nodes().Informer()
		if _, err := w.nodeInformer.AddEventHandler(cache.ResourceEventHandlerFuncs{
			AddFunc:    w.handleNodeAdd,
			UpdateFunc: w.handleNodeUpdate,
			DeleteFunc: w.handleNodeDelete,
		}); err != nil {
			return fmt.Errorf("failed to add node event handler: %w", err)
		}
	}

	return nil
}

// Start begins watching Kubernetes resources
func (w *Watcher) Start() error {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.started {
		return fmt.Errorf("watcher already started")
	}

	w.logger.Info("starting Kubernetes resource watcher")

	// Start informers
	w.informerFactory.Start(w.ctx.Done())

	// Wait for cache sync
	w.logger.Info("waiting for cache sync")
	cacheSyncFuncs := make([]cache.InformerSynced, 0)
	
	if w.podInformer != nil {
		cacheSyncFuncs = append(cacheSyncFuncs, w.podInformer.HasSynced)
	}
	if w.namespaceInformer != nil {
		cacheSyncFuncs = append(cacheSyncFuncs, w.namespaceInformer.HasSynced)
	}
	if w.serviceInformer != nil {
		cacheSyncFuncs = append(cacheSyncFuncs, w.serviceInformer.HasSynced)
	}
	if w.endpointInformer != nil {
		cacheSyncFuncs = append(cacheSyncFuncs, w.endpointInformer.HasSynced)
	}
	if w.nodeInformer != nil {
		cacheSyncFuncs = append(cacheSyncFuncs, w.nodeInformer.HasSynced)
	}

	if !cache.WaitForCacheSync(w.ctx.Done(), cacheSyncFuncs...) {
		return fmt.Errorf("failed to sync cache")
	}

	w.logger.Info("cache sync completed")

	// Start event processing workers
	for i := 0; i < w.config.WorkerCount; i++ {
		w.wg.Add(1)
		go w.eventProcessor(fmt.Sprintf("worker-%d", i))
	}

	// Start statistics updater
	w.wg.Add(1)
	go w.statsUpdater()

	// Start garbage collector
	w.wg.Add(1)
	go w.garbageCollector()

	w.started = true
	w.stats.InSync = true
	w.stats.LastSyncTime = time.Now()

	w.logger.Info("Kubernetes resource watcher started successfully")
	return nil
}

// Stop stops the resource watcher
func (w *Watcher) Stop() error {
	w.mu.Lock()
	defer w.mu.Unlock()

	if !w.started {
		return nil
	}

	w.logger.Info("stopping Kubernetes resource watcher")

	// Cancel context to stop all goroutines
	w.cancel()

	// Wait for all workers to finish
	w.wg.Wait()

	// Close event channel
	close(w.eventChannel)

	w.started = false
	w.stats.InSync = false

	w.logger.Info("Kubernetes resource watcher stopped")
	return nil
}

// AddEventHandler adds an event handler for resource events
func (w *Watcher) AddEventHandler(handler EventHandler) {
	w.mu.Lock()
	defer w.mu.Unlock()

	w.eventHandlers = append(w.eventHandlers, handler)
	w.logger.WithField("handler_count", len(w.eventHandlers)).Debug("added event handler")
}

// GetCache returns the resource cache
func (w *Watcher) GetCache() Cache {
	return w.cache
}

// GetStats returns current cache statistics
func (w *Watcher) GetStats() *CacheStats {
	w.mu.RLock()
	defer w.mu.RUnlock()

	// Update cache stats
	cacheStats := w.cache.Stats()
	
	// Merge with watcher stats
	w.stats.PodCount = cacheStats.PodCount
	w.stats.NamespaceCount = cacheStats.NamespaceCount
	w.stats.ServiceCount = cacheStats.ServiceCount
	w.stats.EndpointCount = cacheStats.EndpointCount
	w.stats.NodeCount = cacheStats.NodeCount

	return w.stats
}

// Pod event handlers
func (w *Watcher) handlePodAdd(obj interface{}) {
	pod, ok := obj.(*corev1.Pod)
	if !ok {
		w.logger.Warn("unexpected object type in pod add handler")
		return
	}

	podInfo := w.convertPod(pod)
	w.cache.StorePod(podInfo)

	event := &ResourceEvent{
		Type:      EventTypeAdded,
		Resource:  ResourceTypePod,
		Timestamp: time.Now(),
		Name:      pod.Name,
		Namespace: pod.Namespace,
		UID:       string(pod.UID),
		Object:    podInfo,
	}

	w.enqueueEvent(event)
}

func (w *Watcher) handlePodUpdate(oldObj, newObj interface{}) {
	oldPod, ok := oldObj.(*corev1.Pod)
	if !ok {
		w.logger.Warn("unexpected old object type in pod update handler")
		return
	}

	newPod, ok := newObj.(*corev1.Pod)
	if !ok {
		w.logger.Warn("unexpected new object type in pod update handler")
		return
	}

	oldPodInfo := w.convertPod(oldPod)
	newPodInfo := w.convertPod(newPod)
	w.cache.StorePod(newPodInfo)

	event := &ResourceEvent{
		Type:      EventTypeModified,
		Resource:  ResourceTypePod,
		Timestamp: time.Now(),
		Name:      newPod.Name,
		Namespace: newPod.Namespace,
		UID:       string(newPod.UID),
		Object:    newPodInfo,
		OldObject: oldPodInfo,
	}

	w.enqueueEvent(event)
}

func (w *Watcher) handlePodDelete(obj interface{}) {
	pod, ok := obj.(*corev1.Pod)
	if !ok {
		// Handle DeletedFinalStateUnknown
		if deletedState, ok := obj.(cache.DeletedFinalStateUnknown); ok {
			pod, ok = deletedState.Obj.(*corev1.Pod)
			if !ok {
				w.logger.Warn("unexpected object type in deleted final state unknown")
				return
			}
		} else {
			w.logger.Warn("unexpected object type in pod delete handler")
			return
		}
	}

	podInfo := w.convertPod(pod)
	now := time.Now()
	podInfo.DeletedAt = &now

	w.cache.DeletePod(pod.Namespace, pod.Name)

	event := &ResourceEvent{
		Type:      EventTypeDeleted,
		Resource:  ResourceTypePod,
		Timestamp: time.Now(),
		Name:      pod.Name,
		Namespace: pod.Namespace,
		UID:       string(pod.UID),
		Object:    podInfo,
	}

	w.enqueueEvent(event)
}

// Namespace event handlers
func (w *Watcher) handleNamespaceAdd(obj interface{}) {
	namespace, ok := obj.(*corev1.Namespace)
	if !ok {
		w.logger.Warn("unexpected object type in namespace add handler")
		return
	}

	namespaceInfo := w.convertNamespace(namespace)
	w.cache.StoreNamespace(namespaceInfo)

	event := &ResourceEvent{
		Type:      EventTypeAdded,
		Resource:  ResourceTypeNamespace,
		Timestamp: time.Now(),
		Name:      namespace.Name,
		UID:       string(namespace.UID),
		Object:    namespaceInfo,
	}

	w.enqueueEvent(event)
}

func (w *Watcher) handleNamespaceUpdate(oldObj, newObj interface{}) {
	oldNamespace, ok := oldObj.(*corev1.Namespace)
	if !ok {
		w.logger.Warn("unexpected old object type in namespace update handler")
		return
	}

	newNamespace, ok := newObj.(*corev1.Namespace)
	if !ok {
		w.logger.Warn("unexpected new object type in namespace update handler")
		return
	}

	oldNamespaceInfo := w.convertNamespace(oldNamespace)
	newNamespaceInfo := w.convertNamespace(newNamespace)
	w.cache.StoreNamespace(newNamespaceInfo)

	event := &ResourceEvent{
		Type:      EventTypeModified,
		Resource:  ResourceTypeNamespace,
		Timestamp: time.Now(),
		Name:      newNamespace.Name,
		UID:       string(newNamespace.UID),
		Object:    newNamespaceInfo,
		OldObject: oldNamespaceInfo,
	}

	w.enqueueEvent(event)
}

func (w *Watcher) handleNamespaceDelete(obj interface{}) {
	namespace, ok := obj.(*corev1.Namespace)
	if !ok {
		if deletedState, ok := obj.(cache.DeletedFinalStateUnknown); ok {
			namespace, ok = deletedState.Obj.(*corev1.Namespace)
			if !ok {
				w.logger.Warn("unexpected object type in deleted final state unknown")
				return
			}
		} else {
			w.logger.Warn("unexpected object type in namespace delete handler")
			return
		}
	}

	namespaceInfo := w.convertNamespace(namespace)
	now := time.Now()
	namespaceInfo.DeletedAt = &now

	w.cache.DeleteNamespace(namespace.Name)

	event := &ResourceEvent{
		Type:      EventTypeDeleted,
		Resource:  ResourceTypeNamespace,
		Timestamp: time.Now(),
		Name:      namespace.Name,
		UID:       string(namespace.UID),
		Object:    namespaceInfo,
	}

	w.enqueueEvent(event)
}

// Service event handlers
func (w *Watcher) handleServiceAdd(obj interface{}) {
	service, ok := obj.(*corev1.Service)
	if !ok {
		w.logger.Warn("unexpected object type in service add handler")
		return
	}

	serviceInfo := w.convertService(service)
	w.cache.StoreService(serviceInfo)

	event := &ResourceEvent{
		Type:      EventTypeAdded,
		Resource:  ResourceTypeService,
		Timestamp: time.Now(),
		Name:      service.Name,
		Namespace: service.Namespace,
		UID:       string(service.UID),
		Object:    serviceInfo,
	}

	w.enqueueEvent(event)
}

func (w *Watcher) handleServiceUpdate(oldObj, newObj interface{}) {
	oldService, ok := oldObj.(*corev1.Service)
	if !ok {
		w.logger.Warn("unexpected old object type in service update handler")
		return
	}

	newService, ok := newObj.(*corev1.Service)
	if !ok {
		w.logger.Warn("unexpected new object type in service update handler")
		return
	}

	oldServiceInfo := w.convertService(oldService)
	newServiceInfo := w.convertService(newService)
	w.cache.StoreService(newServiceInfo)

	event := &ResourceEvent{
		Type:      EventTypeModified,
		Resource:  ResourceTypeService,
		Timestamp: time.Now(),
		Name:      newService.Name,
		Namespace: newService.Namespace,
		UID:       string(newService.UID),
		Object:    newServiceInfo,
		OldObject: oldServiceInfo,
	}

	w.enqueueEvent(event)
}

func (w *Watcher) handleServiceDelete(obj interface{}) {
	service, ok := obj.(*corev1.Service)
	if !ok {
		if deletedState, ok := obj.(cache.DeletedFinalStateUnknown); ok {
			service, ok = deletedState.Obj.(*corev1.Service)
			if !ok {
				w.logger.Warn("unexpected object type in deleted final state unknown")
				return
			}
		} else {
			w.logger.Warn("unexpected object type in service delete handler")
			return
		}
	}

	serviceInfo := w.convertService(service)
	now := time.Now()
	serviceInfo.DeletedAt = &now

	w.cache.DeleteService(service.Namespace, service.Name)

	event := &ResourceEvent{
		Type:      EventTypeDeleted,
		Resource:  ResourceTypeService,
		Timestamp: time.Now(),
		Name:      service.Name,
		Namespace: service.Namespace,
		UID:       string(service.UID),
		Object:    serviceInfo,
	}

	w.enqueueEvent(event)
}

// Endpoint event handlers
func (w *Watcher) handleEndpointAdd(obj interface{}) {
	endpoint, ok := obj.(*corev1.Endpoints)
	if !ok {
		w.logger.Warn("unexpected object type in endpoint add handler")
		return
	}

	endpointInfos := w.convertEndpoints(endpoint)
	for _, endpointInfo := range endpointInfos {
		event := &ResourceEvent{
			Type:      EventTypeAdded,
			Resource:  ResourceTypeEndpoint,
			Timestamp: time.Now(),
			Name:      endpoint.Name,
			Namespace: endpoint.Namespace,
			UID:       string(endpoint.UID),
			Object:    endpointInfo,
		}

		w.enqueueEvent(event)
	}
}

func (w *Watcher) handleEndpointUpdate(oldObj, newObj interface{}) {
	oldEndpoint, ok := oldObj.(*corev1.Endpoints)
	if !ok {
		w.logger.Warn("unexpected old object type in endpoint update handler")
		return
	}

	newEndpoint, ok := newObj.(*corev1.Endpoints)
	if !ok {
		w.logger.Warn("unexpected new object type in endpoint update handler")
		return
	}

	oldEndpointInfos := w.convertEndpoints(oldEndpoint)
	newEndpointInfos := w.convertEndpoints(newEndpoint)

	// For simplicity, emit events for all endpoints
	for i, newEndpointInfo := range newEndpointInfos {
		var oldEndpointInfo *EndpointInfo
		if i < len(oldEndpointInfos) {
			oldEndpointInfo = oldEndpointInfos[i]
		}

		event := &ResourceEvent{
			Type:      EventTypeModified,
			Resource:  ResourceTypeEndpoint,
			Timestamp: time.Now(),
			Name:      newEndpoint.Name,
			Namespace: newEndpoint.Namespace,
			UID:       string(newEndpoint.UID),
			Object:    newEndpointInfo,
			OldObject: oldEndpointInfo,
		}

		w.enqueueEvent(event)
	}
}

func (w *Watcher) handleEndpointDelete(obj interface{}) {
	endpoint, ok := obj.(*corev1.Endpoints)
	if !ok {
		if deletedState, ok := obj.(cache.DeletedFinalStateUnknown); ok {
			endpoint, ok = deletedState.Obj.(*corev1.Endpoints)
			if !ok {
				w.logger.Warn("unexpected object type in deleted final state unknown")
				return
			}
		} else {
			w.logger.Warn("unexpected object type in endpoint delete handler")
			return
		}
	}

	endpointInfos := w.convertEndpoints(endpoint)
	for _, endpointInfo := range endpointInfos {
		event := &ResourceEvent{
			Type:      EventTypeDeleted,
			Resource:  ResourceTypeEndpoint,
			Timestamp: time.Now(),
			Name:      endpoint.Name,
			Namespace: endpoint.Namespace,
			UID:       string(endpoint.UID),
			Object:    endpointInfo,
		}

		w.enqueueEvent(event)
	}
}

// Node event handlers
func (w *Watcher) handleNodeAdd(obj interface{}) {
	node, ok := obj.(*corev1.Node)
	if !ok {
		w.logger.Warn("unexpected object type in node add handler")
		return
	}

	nodeInfo := w.convertNode(node)
	w.cache.StoreNode(nodeInfo)

	event := &ResourceEvent{
		Type:      EventTypeAdded,
		Resource:  ResourceTypeNode,
		Timestamp: time.Now(),
		Name:      node.Name,
		UID:       string(node.UID),
		Object:    nodeInfo,
	}

	w.enqueueEvent(event)
}

func (w *Watcher) handleNodeUpdate(oldObj, newObj interface{}) {
	oldNode, ok := oldObj.(*corev1.Node)
	if !ok {
		w.logger.Warn("unexpected old object type in node update handler")
		return
	}

	newNode, ok := newObj.(*corev1.Node)
	if !ok {
		w.logger.Warn("unexpected new object type in node update handler")
		return
	}

	oldNodeInfo := w.convertNode(oldNode)
	newNodeInfo := w.convertNode(newNode)
	w.cache.StoreNode(newNodeInfo)

	event := &ResourceEvent{
		Type:      EventTypeModified,
		Resource:  ResourceTypeNode,
		Timestamp: time.Now(),
		Name:      newNode.Name,
		UID:       string(newNode.UID),
		Object:    newNodeInfo,
		OldObject: oldNodeInfo,
	}

	w.enqueueEvent(event)
}

func (w *Watcher) handleNodeDelete(obj interface{}) {
	node, ok := obj.(*corev1.Node)
	if !ok {
		if deletedState, ok := obj.(cache.DeletedFinalStateUnknown); ok {
			node, ok = deletedState.Obj.(*corev1.Node)
			if !ok {
				w.logger.Warn("unexpected object type in deleted final state unknown")
				return
			}
		} else {
			w.logger.Warn("unexpected object type in node delete handler")
			return
		}
	}

	nodeInfo := w.convertNode(node)
	now := time.Now()
	nodeInfo.DeletedAt = &now

	w.cache.DeleteNode(node.Name)

	event := &ResourceEvent{
		Type:      EventTypeDeleted,
		Resource:  ResourceTypeNode,
		Timestamp: time.Now(),
		Name:      node.Name,
		UID:       string(node.UID),
		Object:    nodeInfo,
	}

	w.enqueueEvent(event)
}

// enqueueEvent adds an event to the processing queue
func (w *Watcher) enqueueEvent(event *ResourceEvent) {
	select {
	case w.eventChannel <- event:
		w.stats.EventsProcessed++
		w.stats.LastEventProcessed = time.Now()
	default:
		w.logger.Warn("event channel full, dropping event")
	}
}

// eventProcessor processes events from the queue
func (w *Watcher) eventProcessor(workerName string) {
	defer w.wg.Done()

	logger := w.logger.WithField("worker", workerName)
	logger.Debug("starting event processor worker")

	for {
		select {
		case <-w.ctx.Done():
			logger.Debug("stopping event processor worker")
			return

		case event := <-w.eventChannel:
			if event == nil {
				continue
			}

			logger.WithFields(logrus.Fields{
				"type":      event.Type,
				"resource":  event.Resource,
				"name":      event.Name,
				"namespace": event.Namespace,
			}).Debug("processing resource event")

			w.processEvent(event)
		}
	}
}

// processEvent processes a single resource event
func (w *Watcher) processEvent(event *ResourceEvent) {
	w.mu.RLock()
	handlers := make([]EventHandler, len(w.eventHandlers))
	copy(handlers, w.eventHandlers)
	w.mu.RUnlock()

	for _, handler := range handlers {
		switch event.Resource {
		case ResourceTypePod:
			if podInfo, ok := event.Object.(*PodInfo); ok {
				if err := handler.OnPodEvent(event, podInfo); err != nil {
					w.logger.WithError(err).Error("pod event handler failed")
				}
			}
		case ResourceTypeNamespace:
			if namespaceInfo, ok := event.Object.(*NamespaceInfo); ok {
				if err := handler.OnNamespaceEvent(event, namespaceInfo); err != nil {
					w.logger.WithError(err).Error("namespace event handler failed")
				}
			}
		case ResourceTypeService:
			if serviceInfo, ok := event.Object.(*ServiceInfo); ok {
				if err := handler.OnServiceEvent(event, serviceInfo); err != nil {
					w.logger.WithError(err).Error("service event handler failed")
				}
			}
		case ResourceTypeEndpoint:
			if endpointInfo, ok := event.Object.(*EndpointInfo); ok {
				if err := handler.OnEndpointEvent(event, endpointInfo); err != nil {
					w.logger.WithError(err).Error("endpoint event handler failed")
				}
			}
		case ResourceTypeNode:
			if nodeInfo, ok := event.Object.(*NodeInfo); ok {
				if err := handler.OnNodeEvent(event, nodeInfo); err != nil {
					w.logger.WithError(err).Error("node event handler failed")
				}
			}
		}
	}
}

// statsUpdater periodically updates cache statistics
func (w *Watcher) statsUpdater() {
	defer w.wg.Done()

	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	var lastEventCount uint64

	for {
		select {
		case <-w.ctx.Done():
			return

		case <-ticker.C:
			now := time.Now()
			
			// Update events per second
			if w.stats.EventsProcessed > lastEventCount {
				eventDiff := w.stats.EventsProcessed - lastEventCount
				w.stats.EventsPerSecond = float64(eventDiff) / 30.0
				lastEventCount = w.stats.EventsProcessed
			}

			// Update API server connectivity
			if w.clientset != nil {
				if _, err := w.clientset.Discovery().ServerVersion(); err != nil {
					w.stats.APIServerConnected = false
					w.stats.APICallFailures++
				} else {
					w.stats.APIServerConnected = true
					w.stats.LastAPICall = now
				}
			}
		}
	}
}

// garbageCollector periodically cleans up expired resources
func (w *Watcher) garbageCollector() {
	defer w.wg.Done()

	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()

	for {
		select {
		case <-w.ctx.Done():
			return

		case <-ticker.C:
			if err := w.cache.GarbageCollect(); err != nil {
				w.logger.WithError(err).Error("garbage collection failed")
			} else {
				w.stats.LastGCTime = time.Now()
			}
		}
	}
}

// Conversion methods

func (w *Watcher) convertPod(pod *corev1.Pod) *PodInfo {
	podInfo := &PodInfo{
		Name:        pod.Name,
		Namespace:   pod.Namespace,
		UID:         string(pod.UID),
		Labels:      pod.Labels,
		Annotations: pod.Annotations,
		CreatedAt:   pod.CreationTimestamp.Time,
		UpdatedAt:   time.Now(),
		LastSeen:    time.Now(),
	}

	// Set IP information
	if pod.Status.PodIP != "" {
		podInfo.IP = net.ParseIP(pod.Status.PodIP)
	}

	// Set multiple IPs
	for _, podIP := range pod.Status.PodIPs {
		if ip := net.ParseIP(podIP.IP); ip != nil {
			podInfo.IPs = append(podInfo.IPs, ip)
		}
	}

	// Set host information
	if pod.Status.HostIP != "" {
		podInfo.HostIP = net.ParseIP(pod.Status.HostIP)
	}

	// Set network settings
	podInfo.HostNetwork = pod.Spec.HostNetwork
	podInfo.DNSPolicy = string(pod.Spec.DNSPolicy)
	podInfo.DNSConfig = pod.Spec.DNSConfig

	// Set security context
	podInfo.ServiceAccount = pod.Spec.ServiceAccountName
	podInfo.SecurityContext = pod.Spec.SecurityContext
	podInfo.ImagePullSecrets = pod.Spec.ImagePullSecrets

	// Set node information
	podInfo.NodeName = pod.Spec.NodeName
	podInfo.NodeSelector = pod.Spec.NodeSelector

	// Set scheduling information
	podInfo.Priority = pod.Spec.Priority
	podInfo.PriorityClass = pod.Spec.PriorityClassName
	podInfo.Tolerations = pod.Spec.Tolerations
	podInfo.Affinity = pod.Spec.Affinity

	// Set runtime status
	podInfo.Phase = pod.Status.Phase
	podInfo.Conditions = pod.Status.Conditions
	podInfo.QOSClass = pod.Status.QOSClass
	podInfo.StartTime = pod.Status.StartTime
	podInfo.RestartPolicy = pod.Spec.RestartPolicy
	podInfo.PodIPs = pod.Status.PodIPs

	// Convert containers
	for _, container := range pod.Spec.Containers {
		containerInfo := ContainerInfo{
			Name:            container.Name,
			Image:           container.Image,
			Command:         container.Command,
			Args:            container.Args,
			Env:             container.Env,
			Resources:       container.Resources,
			SecurityContext: container.SecurityContext,
			Ports:           container.Ports,
			VolumeMounts:    container.VolumeMounts,
		}

		// Find container status
		for _, containerStatus := range pod.Status.ContainerStatuses {
			if containerStatus.Name == container.Name {
				containerInfo.ImageID = containerStatus.ImageID
				containerInfo.State = containerStatus.State
				containerInfo.Ready = containerStatus.Ready
				containerInfo.RestartCount = containerStatus.RestartCount
				break
			}
		}

		podInfo.Containers = append(podInfo.Containers, containerInfo)
	}

	// Convert init containers
	for _, container := range pod.Spec.InitContainers {
		containerInfo := ContainerInfo{
			Name:            container.Name,
			Image:           container.Image,
			Command:         container.Command,
			Args:            container.Args,
			Env:             container.Env,
			Resources:       container.Resources,
			SecurityContext: container.SecurityContext,
			Ports:           container.Ports,
			VolumeMounts:    container.VolumeMounts,
		}

		// Find container status
		for _, containerStatus := range pod.Status.InitContainerStatuses {
			if containerStatus.Name == container.Name {
				containerInfo.ImageID = containerStatus.ImageID
				containerInfo.State = containerStatus.State
				containerInfo.Ready = containerStatus.Ready
				containerInfo.RestartCount = containerStatus.RestartCount
				break
			}
		}

		podInfo.InitContainers = append(podInfo.InitContainers, containerInfo)
	}

	return podInfo
}

func (w *Watcher) convertNamespace(namespace *corev1.Namespace) *NamespaceInfo {
	namespaceInfo := &NamespaceInfo{
		Name:        namespace.Name,
		UID:         string(namespace.UID),
		Labels:      namespace.Labels,
		Annotations: namespace.Annotations,
		Phase:       namespace.Status.Phase,
		Conditions:  namespace.Status.Conditions,
		CreatedAt:   namespace.CreationTimestamp.Time,
		UpdatedAt:   time.Now(),
		LastSeen:    time.Now(),
	}

	// Check for Istio injection
	if injectionLabel, exists := namespace.Labels["istio-injection"]; exists {
		namespaceInfo.IstioInjection = injectionLabel == "enabled"
	}

	return namespaceInfo
}

func (w *Watcher) convertService(service *corev1.Service) *ServiceInfo {
	serviceInfo := &ServiceInfo{
		Name:                service.Name,
		Namespace:           service.Namespace,
		UID:                 string(service.UID),
		Labels:              service.Labels,
		Annotations:         service.Annotations,
		Type:                service.Spec.Type,
		ClusterIP:           service.Spec.ClusterIP,
		ClusterIPs:          service.Spec.ClusterIPs,
		ExternalIPs:         service.Spec.ExternalIPs,
		LoadBalancerIP:      service.Spec.LoadBalancerIP,
		ExternalName:        service.Spec.ExternalName,
		Selector:            service.Spec.Selector,
		SessionAffinity:     service.Spec.SessionAffinity,
		LoadBalancerSourceRanges: service.Spec.LoadBalancerSourceRanges,
		LoadBalancerIngress: service.Status.LoadBalancer.Ingress,
		Conditions:          service.Status.Conditions,
		CreatedAt:           service.CreationTimestamp.Time,
		UpdatedAt:           time.Now(),
		LastSeen:            time.Now(),
	}

	// Convert ports
	for _, port := range service.Spec.Ports {
		portInfo := ServicePortInfo{
			Name:       port.Name,
			Protocol:   string(port.Protocol),
			Port:       port.Port,
			TargetPort: port.TargetPort,
			NodePort:   port.NodePort,
		}
		serviceInfo.Ports = append(serviceInfo.Ports, portInfo)
	}

	return serviceInfo
}

func (w *Watcher) convertEndpoints(endpoints *corev1.Endpoints) []*EndpointInfo {
	var endpointInfos []*EndpointInfo

	for _, subset := range endpoints.Subsets {
		// Convert ports
		var ports []EndpointPortInfo
		for _, port := range subset.Ports {
			portInfo := EndpointPortInfo{
				Name:     port.Name,
				Port:     port.Port,
				Protocol: string(port.Protocol),
			}
			ports = append(ports, portInfo)
		}

		// Convert ready addresses
		for _, address := range subset.Addresses {
			endpointInfo := &EndpointInfo{
				IP:        address.IP,
				Hostname:  address.Hostname,
				NodeName:  getStringPointer(address.NodeName),
				Ports:     ports,
				Ready:     true,
				Serving:   true,
				TargetRef: address.TargetRef,
				LastSeen:  time.Now(),
			}
			endpointInfos = append(endpointInfos, endpointInfo)
		}

		// Convert not ready addresses
		for _, address := range subset.NotReadyAddresses {
			endpointInfo := &EndpointInfo{
				IP:        address.IP,
				Hostname:  address.Hostname,
				NodeName:  getStringPointer(address.NodeName),
				Ports:     ports,
				Ready:     false,
				Serving:   false,
				TargetRef: address.TargetRef,
				LastSeen:  time.Now(),
			}
			endpointInfos = append(endpointInfos, endpointInfo)
		}
	}

	return endpointInfos
}

func (w *Watcher) convertNode(node *corev1.Node) *NodeInfo {
	nodeInfo := &NodeInfo{
		Name:            node.Name,
		UID:             string(node.UID),
		Labels:          node.Labels,
		Annotations:     node.Annotations,
		PodCIDR:         node.Spec.PodCIDR,
		PodCIDRs:        node.Spec.PodCIDRs,
		ProviderID:      node.Spec.ProviderID,
		Unschedulable:   node.Spec.Unschedulable,
		Taints:          node.Spec.Taints,
		Phase:           node.Status.Phase,
		Conditions:      node.Status.Conditions,
		Addresses:       node.Status.Addresses,
		NodeInfo:        node.Status.NodeInfo,
		Capacity:        node.Status.Capacity,
		Allocatable:     node.Status.Allocatable,
		DaemonEndpoints: node.Status.DaemonEndpoints,
		Images:          node.Status.Images,
		Config:          node.Status.Config,
		CreatedAt:       node.CreationTimestamp.Time,
		UpdatedAt:       time.Now(),
		LastSeen:        time.Now(),
	}

	return nodeInfo
}

// Helper functions
func getStringPointer(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}