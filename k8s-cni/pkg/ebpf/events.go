// Package ebpf event processing and real-time monitoring
//
// This file implements real-time event processing from eBPF programs,
// providing immediate notifications for security events, policy violations,
// performance anomalies, and network topology changes.

package ebpf

import (
	"bytes"
	"context"
	"encoding/binary"
	"fmt"
	"net"
	"sync"
	"time"

	"github.com/cilium/ebpf"
	"github.com/cilium/ebpf/ringbuf"
	"github.com/sirupsen/logrus"
)

// Event types from eBPF programs
const (
	EventTypeNewFlow        = 1
	EventTypeConnectionEst  = 2
	EventTypeConnectionTerm = 3
	EventTypeAnomalyDetected = 4
	EventTypePerfAlert      = 5
	EventTypePolicyViolation = 6
	EventTypeSecurityAlert  = 7
	EventTypeTopologyChange = 8
)

// Event severity levels
const (
	SeverityInfo     = 0
	SeverityWarning  = 1
	SeverityError    = 2
	SeverityCritical = 3
)

// EventProcessor handles real-time events from eBPF programs
type EventProcessor struct {
	logger    *logrus.Entry
	maps      map[string]*ebpf.Map
	readers   map[string]*ringbuf.Reader
	
	// Event handlers
	handlers map[uint8][]EventHandler
	mu       sync.RWMutex

	// Statistics
	eventsProcessed uint64
	eventErrors     uint64
	lastEvent       time.Time
}

// EventHandler is called when events are received
type EventHandler func(*Event) error

// Event represents a processed eBPF event
type Event struct {
	Type        uint8
	Severity    uint8
	Timestamp   time.Time
	Source      string // eBPF program source
	FlowKey     *FlowKey
	ConnectionID uint32
	MetricValue uint64
	Message     string
	Data        map[string]interface{} // Additional event data
}

// FlowEvent represents a network flow event
type FlowEvent struct {
	Event
	SrcIP       net.IP
	DstIP       net.IP
	SrcPort     uint16
	DstPort     uint16
	Protocol    uint8
	Direction   uint8
	BytesTotal  uint64
	PacketsTotal uint64
	Duration    time.Duration
}

// PolicyViolationEvent represents a policy violation
type PolicyViolationEvent struct {
	Event
	SrcIP        net.IP
	DstIP        net.IP
	SrcPort      uint16
	DstPort      uint16
	Protocol     uint8
	Direction    uint8
	RuleID       uint32
	SrcNamespace string
	DstNamespace string
	Action       string
}

// SecurityAlertEvent represents a security-related alert
type SecurityAlertEvent struct {
	Event
	AlertType    string
	ThreatLevel  uint8
	SourceIP     net.IP
	TargetIP     net.IP
	Description  string
	Indicators   []string
}

// PerformanceAlertEvent represents a performance-related alert
type PerformanceAlertEvent struct {
	Event
	MetricName   string
	CurrentValue float64
	Threshold    float64
	Unit         string
	Duration     time.Duration
}

// NewEventProcessor creates a new event processor
func NewEventProcessor(maps map[string]*ebpf.Map) (*EventProcessor, error) {
	processor := &EventProcessor{
		logger:   logrus.WithField("component", "event-processor"),
		maps:     maps,
		readers:  make(map[string]*ringbuf.Reader),
		handlers: make(map[uint8][]EventHandler),
	}

	// Initialize ring buffer readers
	if err := processor.initRingBuffers(); err != nil {
		return nil, fmt.Errorf("failed to initialize ring buffers: %w", err)
	}

	// Set up default event handlers
	processor.setupDefaultHandlers()

	return processor, nil
}

// initRingBuffers initializes ring buffer readers for event maps
func (ep *EventProcessor) initRingBuffers() error {
	// Look for ring buffer maps
	ringBufferMaps := []string{
		"violation_events",
		"monitor_events",
		"security_events",
		"perf_events",
	}

	for _, mapName := range ringBufferMaps {
		if bpfMap, exists := ep.maps[mapName]; exists {
			reader, err := ringbuf.NewReader(bpfMap)
			if err != nil {
				return fmt.Errorf("failed to create ring buffer reader for %s: %w", mapName, err)
			}
			ep.readers[mapName] = reader
			ep.logger.WithField("map", mapName).Debug("initialized ring buffer reader")
		}
	}

	return nil
}

// setupDefaultHandlers sets up default event handlers
func (ep *EventProcessor) setupDefaultHandlers() {
	// Policy violation handler
	ep.RegisterHandler(EventTypePolicyViolation, func(event *Event) error {
		ep.logger.WithFields(logrus.Fields{
			"type":     "policy_violation",
			"severity": event.Severity,
			"flow":     event.FlowKey,
			"message":  event.Message,
		}).Warn("policy violation detected")
		return nil
	})

	// Security alert handler
	ep.RegisterHandler(EventTypeSecurityAlert, func(event *Event) error {
		ep.logger.WithFields(logrus.Fields{
			"type":     "security_alert",
			"severity": event.Severity,
			"message":  event.Message,
		}).Error("security alert")
		return nil
	})

	// Performance alert handler
	ep.RegisterHandler(EventTypePerfAlert, func(event *Event) error {
		ep.logger.WithFields(logrus.Fields{
			"type":     "performance_alert",
			"severity": event.Severity,
			"metric":   event.MetricValue,
			"message":  event.Message,
		}).Warn("performance alert")
		return nil
	})

	// New flow handler
	ep.RegisterHandler(EventTypeNewFlow, func(event *Event) error {
		ep.logger.WithFields(logrus.Fields{
			"type": "new_flow",
			"flow": event.FlowKey,
		}).Debug("new flow detected")
		return nil
	})
}

// RegisterHandler registers an event handler for a specific event type
func (ep *EventProcessor) RegisterHandler(eventType uint8, handler EventHandler) {
	ep.mu.Lock()
	defer ep.mu.Unlock()

	if ep.handlers[eventType] == nil {
		ep.handlers[eventType] = make([]EventHandler, 0)
	}
	ep.handlers[eventType] = append(ep.handlers[eventType], handler)

	ep.logger.WithField("event_type", eventType).Debug("registered event handler")
}

// Start begins event processing in background goroutines
func (ep *EventProcessor) Start(ctx context.Context) {
	ep.logger.Info("starting eBPF event processing")

	var wg sync.WaitGroup

	// Start a goroutine for each ring buffer reader
	for mapName, reader := range ep.readers {
		wg.Add(1)
		go func(name string, r *ringbuf.Reader) {
			defer wg.Done()
			ep.processEvents(ctx, name, r)
		}(mapName, reader)
	}

	// Wait for all event processors to complete
	wg.Wait()
	ep.logger.Info("event processing stopped")
}

// processEvents processes events from a specific ring buffer
func (ep *EventProcessor) processEvents(ctx context.Context, mapName string, reader *ringbuf.Reader) {
	logger := ep.logger.WithField("map", mapName)
	logger.Debug("starting event processing loop")

	for {
		select {
		case <-ctx.Done():
			logger.Debug("stopping event processing")
			if err := reader.Close(); err != nil {
				logger.WithError(err).Warn("failed to close ring buffer reader")
			}
			return

		default:
			// Read event from ring buffer with timeout
			record, err := reader.Read()
			if err != nil {
				if err == ringbuf.ErrClosed {
					logger.Debug("ring buffer closed")
					return
				}
				ep.eventErrors++
				logger.WithError(err).Error("failed to read from ring buffer")
				time.Sleep(100 * time.Millisecond) // Brief pause before retry
				continue
			}

			// Process the event
			if err := ep.processRawEvent(mapName, record.RawSample); err != nil {
				ep.eventErrors++
				logger.WithError(err).Error("failed to process event")
			} else {
				ep.eventsProcessed++
				ep.lastEvent = time.Now()
			}
		}
	}
}

// processRawEvent processes a raw event from the ring buffer
func (ep *EventProcessor) processRawEvent(mapName string, rawData []byte) error {
	// Parse the raw event data based on the map type
	var event *Event
	var err error

	switch mapName {
	case "violation_events":
		event, err = ep.parseViolationEvent(rawData)
	case "monitor_events":
		event, err = ep.parseMonitorEvent(rawData)
	case "security_events":
		event, err = ep.parseSecurityEvent(rawData)
	case "perf_events":
		event, err = ep.parsePerformanceEvent(rawData)
	default:
		return fmt.Errorf("unknown event map: %s", mapName)
	}

	if err != nil {
		return fmt.Errorf("failed to parse event from %s: %w", mapName, err)
	}

	event.Source = mapName

	// Dispatch to handlers
	return ep.dispatchEvent(event)
}

// parseViolationEvent parses a policy violation event
func (ep *EventProcessor) parseViolationEvent(data []byte) (*Event, error) {
	if len(data) < 48 { // Minimum size for violation event
		return nil, fmt.Errorf("violation event data too short: %d bytes", len(data))
	}

	buf := bytes.NewReader(data)
	event := &Event{
		Type: EventTypePolicyViolation,
		Data: make(map[string]interface{}),
	}

	// Parse binary data (simplified - real implementation would use proper struct)
	var srcIP, dstIP uint32
	var srcPort, dstPort uint16
	var protocol, direction uint8
	var ruleID uint32
	var timestamp uint64

	if err := binary.Read(buf, binary.LittleEndian, &srcIP); err != nil {
		return nil, err
	}
	if err := binary.Read(buf, binary.LittleEndian, &dstIP); err != nil {
		return nil, err
	}
	if err := binary.Read(buf, binary.LittleEndian, &srcPort); err != nil {
		return nil, err
	}
	if err := binary.Read(buf, binary.LittleEndian, &dstPort); err != nil {
		return nil, err
	}
	if err := binary.Read(buf, binary.LittleEndian, &protocol); err != nil {
		return nil, err
	}
	if err := binary.Read(buf, binary.LittleEndian, &direction); err != nil {
		return nil, err
	}
	if err := binary.Read(buf, binary.LittleEndian, &ruleID); err != nil {
		return nil, err
	}
	if err := binary.Read(buf, binary.LittleEndian, &timestamp); err != nil {
		return nil, err
	}

	event.Timestamp = time.Unix(0, int64(timestamp))
	event.Severity = SeverityWarning
	event.FlowKey = &FlowKey{
		SrcIP:     srcIP,
		DstIP:     dstIP,
		SrcPort:   srcPort,
		DstPort:   dstPort,
		Protocol:  protocol,
		Direction: direction,
	}
	event.MetricValue = uint64(ruleID)
	event.Message = fmt.Sprintf("Policy violation: %s:%d -> %s:%d proto=%d rule=%d",
		uint32ToIP(srcIP), srcPort, uint32ToIP(dstIP), dstPort, protocol, ruleID)

	// Store additional data
	event.Data["src_ip"] = uint32ToIP(srcIP)
	event.Data["dst_ip"] = uint32ToIP(dstIP)
	event.Data["src_port"] = srcPort
	event.Data["dst_port"] = dstPort
	event.Data["protocol"] = protocol
	event.Data["direction"] = direction
	event.Data["rule_id"] = ruleID

	return event, nil
}

// parseMonitorEvent parses a monitoring event
func (ep *EventProcessor) parseMonitorEvent(data []byte) (*Event, error) {
	if len(data) < 256 { // Monitor event struct size
		return nil, fmt.Errorf("monitor event data too short: %d bytes", len(data))
	}

	event := &Event{
		Type:      EventTypeNewFlow, // Default type
		Timestamp: time.Now(),
		Severity:  SeverityInfo,
		Data:      make(map[string]interface{}),
	}

	// Parse monitor event (simplified)
	buf := bytes.NewReader(data)
	var eventType, severity uint8
	var timestamp uint64
	var metricValue uint64

	binary.Read(buf, binary.LittleEndian, &eventType)
	binary.Read(buf, binary.LittleEndian, &severity)
	binary.Read(buf, binary.LittleEndian, &timestamp)
	binary.Read(buf, binary.LittleEndian, &metricValue)

	event.Type = eventType
	event.Severity = severity
	event.Timestamp = time.Unix(0, int64(timestamp))
	event.MetricValue = metricValue

	// Parse message (last 128 bytes)
	messageBytes := data[len(data)-128:]
	nullIndex := bytes.IndexByte(messageBytes, 0)
	if nullIndex >= 0 {
		event.Message = string(messageBytes[:nullIndex])
	} else {
		event.Message = string(messageBytes)
	}

	return event, nil
}

// parseSecurityEvent parses a security alert event
func (ep *EventProcessor) parseSecurityEvent(data []byte) (*Event, error) {
	event := &Event{
		Type:      EventTypeSecurityAlert,
		Timestamp: time.Now(),
		Severity:  SeverityError,
		Data:      make(map[string]interface{}),
		Message:   "Security alert detected",
	}

	// Security events would have more complex parsing
	// For now, just return a basic event

	return event, nil
}

// parsePerformanceEvent parses a performance alert event
func (ep *EventProcessor) parsePerformanceEvent(data []byte) (*Event, error) {
	event := &Event{
		Type:      EventTypePerfAlert,
		Timestamp: time.Now(),
		Severity:  SeverityWarning,
		Data:      make(map[string]interface{}),
		Message:   "Performance alert",
	}

	// Performance events would have metric-specific parsing
	// For now, just return a basic event

	return event, nil
}

// dispatchEvent sends an event to all registered handlers
func (ep *EventProcessor) dispatchEvent(event *Event) error {
	ep.mu.RLock()
	handlers := ep.handlers[event.Type]
	ep.mu.RUnlock()

	if len(handlers) == 0 {
		// No handlers registered for this event type
		return nil
	}

	// Call all handlers for this event type
	var errors []error
	for _, handler := range handlers {
		if err := handler(event); err != nil {
			errors = append(errors, err)
		}
	}

	if len(errors) > 0 {
		return fmt.Errorf("handler errors: %v", errors)
	}

	return nil
}

// GetStatistics returns event processing statistics
func (ep *EventProcessor) GetStatistics() *EventProcessorStats {
	return &EventProcessorStats{
		EventsProcessed: ep.eventsProcessed,
		EventErrors:     ep.eventErrors,
		LastEvent:       ep.lastEvent,
		ActiveReaders:   len(ep.readers),
		RegisteredHandlers: len(ep.handlers),
	}
}

// Close shuts down the event processor and cleans up resources
func (ep *EventProcessor) Close() error {
	ep.logger.Info("shutting down event processor")

	// Close all ring buffer readers
	for mapName, reader := range ep.readers {
		if err := reader.Close(); err != nil {
			ep.logger.WithError(err).WithField("map", mapName).Warn("failed to close ring buffer reader")
		}
	}

	return nil
}

// EventProcessorStats holds statistics for the event processor
type EventProcessorStats struct {
	EventsProcessed    uint64
	EventErrors        uint64
	LastEvent          time.Time
	ActiveReaders      int
	RegisteredHandlers int
}

// Helper functions for creating specialized event handlers

// NewFlowEventHandler creates a handler for flow events
func NewFlowEventHandler(callback func(*FlowEvent)) EventHandler {
	return func(event *Event) error {
		if event.Type != EventTypeNewFlow {
			return nil
		}

		flowEvent := &FlowEvent{
			Event: *event,
		}

		if event.FlowKey != nil {
			flowEvent.SrcIP = uint32ToIP(event.FlowKey.SrcIP)
			flowEvent.DstIP = uint32ToIP(event.FlowKey.DstIP)
			flowEvent.SrcPort = event.FlowKey.SrcPort
			flowEvent.DstPort = event.FlowKey.DstPort
			flowEvent.Protocol = event.FlowKey.Protocol
			flowEvent.Direction = event.FlowKey.Direction
		}

		callback(flowEvent)
		return nil
	}
}

// NewPolicyViolationHandler creates a handler for policy violations
func NewPolicyViolationHandler(callback func(*PolicyViolationEvent)) EventHandler {
	return func(event *Event) error {
		if event.Type != EventTypePolicyViolation {
			return nil
		}

		violationEvent := &PolicyViolationEvent{
			Event:  *event,
			RuleID: uint32(event.MetricValue),
		}

		if event.FlowKey != nil {
			violationEvent.SrcIP = uint32ToIP(event.FlowKey.SrcIP)
			violationEvent.DstIP = uint32ToIP(event.FlowKey.DstIP)
			violationEvent.SrcPort = event.FlowKey.SrcPort
			violationEvent.DstPort = event.FlowKey.DstPort
			violationEvent.Protocol = event.FlowKey.Protocol
			violationEvent.Direction = event.FlowKey.Direction
		}

		// Extract additional data
		if srcNS, ok := event.Data["src_namespace"].(string); ok {
			violationEvent.SrcNamespace = srcNS
		}
		if dstNS, ok := event.Data["dst_namespace"].(string); ok {
			violationEvent.DstNamespace = dstNS
		}

		callback(violationEvent)
		return nil
	}
}

// NewSecurityAlertHandler creates a handler for security alerts
func NewSecurityAlertHandler(callback func(*SecurityAlertEvent)) EventHandler {
	return func(event *Event) error {
		if event.Type != EventTypeSecurityAlert {
			return nil
		}

		alertEvent := &SecurityAlertEvent{
			Event:       *event,
			AlertType:   "unknown",
			ThreatLevel: uint8(event.Severity),
			Description: event.Message,
		}

		callback(alertEvent)
		return nil
	}
}