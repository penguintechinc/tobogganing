import React, { useState } from 'react';
import Head from 'next/head';

// Deployment scenario types
interface DeploymentScenario {
  id: string;
  title: string;
  subtitle: string;
  description: string;
  benefits: string[];
  useCases: string[];
  complexity: 'Low' | 'Medium' | 'High';
  icon: string;
  color: string;
}

// SVG Component for dataflow diagrams
const DataflowDiagram: React.FC<{ scenario: string }> = ({ scenario }) => {
  const renderCloudDiagram = () => (
    <svg viewBox="0 0 800 500" className="w-full h-96">
      {/* Background */}
      <defs>
        <linearGradient id="cloudGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{ stopColor: '#3b82f6', stopOpacity: 0.1 }} />
          <stop offset="100%" style={{ stopColor: '#1d4ed8', stopOpacity: 0.2 }} />
        </linearGradient>
        <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="2" dy="2" stdDeviation="3" floodOpacity="0.3"/>
        </filter>
      </defs>
      
      {/* Cloud Region */}
      <rect x="50" y="50" width="700" height="400" rx="20" fill="url(#cloudGrad)" stroke="#3b82f6" strokeWidth="2" strokeDasharray="5,5" />
      <text x="400" y="80" textAnchor="middle" className="fill-blue-600 text-lg font-semibold">☁️ AWS/Azure/GCP Cloud Region</text>
      
      {/* Manager Service */}
      <rect x="100" y="120" width="150" height="80" rx="8" fill="#10b981" filter="url(#shadow)" />
      <text x="175" y="145" textAnchor="middle" className="fill-white text-sm font-semibold">📊 Manager</text>
      <text x="175" y="160" textAnchor="middle" className="fill-white text-xs">Service</text>
      <text x="175" y="175" textAnchor="middle" className="fill-white text-xs">Python/MySQL</text>
      <text x="175" y="190" textAnchor="middle" className="fill-white text-xs">Port: 443</text>
      
      {/* Headend Servers */}
      <rect x="320" y="120" width="150" height="80" rx="8" fill="#3b82f6" filter="url(#shadow)" />
      <text x="395" y="145" textAnchor="middle" className="fill-white text-sm font-semibold">🌐 Headend</text>
      <text x="395" y="160" textAnchor="middle" className="fill-white text-xs">US-East-1</text>
      <text x="395" y="175" textAnchor="middle" className="fill-white text-xs">Go/WireGuard</text>
      <text x="395" y="190" textAnchor="middle" className="fill-white text-xs">Port: 51820</text>
      
      <rect x="540" y="120" width="150" height="80" rx="8" fill="#3b82f6" filter="url(#shadow)" />
      <text x="615" y="145" textAnchor="middle" className="fill-white text-sm font-semibold">🌐 Headend</text>
      <text x="615" y="160" textAnchor="middle" className="fill-white text-xs">EU-West-1</text>
      <text x="615" y="175" textAnchor="middle" className="fill-white text-xs">Go/WireGuard</text>
      <text x="615" y="190" textAnchor="middle" className="fill-white text-xs">Port: 51820</text>
      
      {/* Load Balancer */}
      <rect x="320" y="250" width="150" height="60" rx="8" fill="#8b5cf6" filter="url(#shadow)" />
      <text x="395" y="275" textAnchor="middle" className="fill-white text-sm font-semibold">⚖️ Load Balancer</text>
      <text x="395" y="290" textAnchor="middle" className="fill-white text-xs">Global Traffic Manager</text>
      <text x="395" y="305" textAnchor="middle" className="fill-white text-xs">Health Checks</text>
      
      {/* Monitoring */}
      <rect x="100" y="250" width="150" height="60" rx="8" fill="#f59e0b" filter="url(#shadow)" />
      <text x="175" y="275" textAnchor="middle" className="fill-white text-sm font-semibold">📈 Monitoring</text>
      <text x="175" y="290" textAnchor="middle" className="fill-white text-xs">Prometheus/Grafana</text>
      <text x="175" y="305" textAnchor="middle" className="fill-white text-xs">Alerts & Metrics</text>
      
      {/* Database */}
      <rect x="540" y="250" width="150" height="60" rx="8" fill="#ef4444" filter="url(#shadow)" />
      <text x="615" y="275" textAnchor="middle" className="fill-white text-sm font-semibold">🗄️ Database</text>
      <text x="615" y="290" textAnchor="middle" className="fill-white text-xs">MySQL Cluster</text>
      <text x="615" y="305" textAnchor="middle" className="fill-white text-xs">Multi-AZ HA</text>
      
      {/* Clients */}
      <rect x="100" y="380" width="120" height="50" rx="6" fill="#6b7280" filter="url(#shadow)" />
      <text x="160" y="400" textAnchor="middle" className="fill-white text-xs font-semibold">💻 Desktop</text>
      <text x="160" y="415" textAnchor="middle" className="fill-white text-xs">Win/Mac/Linux</text>
      
      <rect x="240" y="380" width="120" height="50" rx="6" fill="#6b7280" filter="url(#shadow)" />
      <text x="300" y="400" textAnchor="middle" className="fill-white text-xs font-semibold">📱 Mobile</text>
      <text x="300" y="415" textAnchor="middle" className="fill-white text-xs">iOS/Android</text>
      
      <rect x="480" y="380" width="120" height="50" rx="6" fill="#6b7280" filter="url(#shadow)" />
      <text x="540" y="400" textAnchor="middle" className="fill-white text-xs font-semibold">🐳 Docker</text>
      <text x="540" y="415" textAnchor="middle" className="fill-white text-xs">Container</text>
      
      <rect x="620" y="380" width="120" height="50" rx="6" fill="#6b7280" filter="url(#shadow)" />
      <text x="680" y="400" textAnchor="middle" className="fill-white text-xs font-semibold">🖥️ Server</text>
      <text x="680" y="415" textAnchor="middle" className="fill-white text-xs">Headless</text>
      
      {/* Connection Lines */}
      {/* Manager to Headends */}
      <line x1="250" y1="160" x2="320" y2="160" stroke="#10b981" strokeWidth="3" markerEnd="url(#arrowgreen)" />
      <line x1="250" y1="160" x2="540" y2="160" stroke="#10b981" strokeWidth="3" markerEnd="url(#arrowgreen)" />
      
      {/* Manager to Database */}
      <line x1="250" y1="180" x2="540" y2="270" stroke="#10b981" strokeWidth="2" markerEnd="url(#arrowgreen)" />
      
      {/* Manager to Monitoring */}
      <line x1="175" y1="200" x2="175" y2="250" stroke="#10b981" strokeWidth="2" markerEnd="url(#arrowgreen)" />
      
      {/* Load Balancer to Headends */}
      <line x1="395" y1="250" x2="395" y2="200" stroke="#8b5cf6" strokeWidth="2" markerEnd="url(#arrowpurple)" />
      <line x1="420" y1="280" x2="540" y2="160" stroke="#8b5cf6" strokeWidth="2" markerEnd="url(#arrowpurple)" />
      
      {/* Clients to Load Balancer */}
      <line x1="160" y1="380" x2="350" y2="310" stroke="#6b7280" strokeWidth="2" strokeDasharray="3,3" />
      <line x1="300" y1="380" x2="370" y2="310" stroke="#6b7280" strokeWidth="2" strokeDasharray="3,3" />
      <line x1="540" y1="380" x2="420" y2="310" stroke="#6b7280" strokeWidth="2" strokeDasharray="3,3" />
      <line x1="680" y1="380" x2="440" y2="310" stroke="#6b7280" strokeWidth="2" strokeDasharray="3,3" />
      
      {/* Arrow Markers */}
      <defs>
        <marker id="arrowgreen" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
          <polygon points="0,0 0,6 9,3" fill="#10b981" />
        </marker>
        <marker id="arrowpurple" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
          <polygon points="0,0 0,6 9,3" fill="#8b5cf6" />
        </marker>
      </defs>
    </svg>
  );

  const renderHybridDiagram = () => (
    <svg viewBox="0 0 800 600" className="w-full h-96">
      <defs>
        <linearGradient id="cloudGradHybrid" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{ stopColor: '#3b82f6', stopOpacity: 0.1 }} />
          <stop offset="100%" style={{ stopColor: '#1d4ed8', stopOpacity: 0.2 }} />
        </linearGradient>
        <linearGradient id="onpremGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{ stopColor: '#10b981', stopOpacity: 0.1 }} />
          <stop offset="100%" style={{ stopColor: '#059669', stopOpacity: 0.2 }} />
        </linearGradient>
        <filter id="shadowHybrid" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="2" dy="2" stdDeviation="3" floodOpacity="0.3"/>
        </filter>
      </defs>
      
      {/* Cloud Section */}
      <rect x="50" y="50" width="350" height="500" rx="15" fill="url(#cloudGradHybrid)" stroke="#3b82f6" strokeWidth="2" strokeDasharray="5,5" />
      <text x="225" y="80" textAnchor="middle" className="fill-blue-600 text-lg font-semibold">☁️ Public Cloud</text>
      
      {/* On-Premise Section */}
      <rect x="450" y="50" width="300" height="500" rx="15" fill="url(#onpremGrad)" stroke="#10b981" strokeWidth="2" strokeDasharray="5,5" />
      <text x="600" y="80" textAnchor="middle" className="fill-green-600 text-lg font-semibold">🏢 On-Premise</text>
      
      {/* Cloud Manager */}
      <rect x="100" y="120" width="140" height="70" rx="8" fill="#10b981" filter="url(#shadowHybrid)" />
      <text x="170" y="145" textAnchor="middle" className="fill-white text-sm font-semibold">📊 Manager</text>
      <text x="170" y="160" textAnchor="middle" className="fill-white text-xs">(Cloud)</text>
      <text x="170" y="175" textAnchor="middle" className="fill-white text-xs">Multi-tenant</text>
      
      {/* Cloud Headend */}
      <rect x="100" y="220" width="140" height="70" rx="8" fill="#3b82f6" filter="url(#shadowHybrid)" />
      <text x="170" y="245" textAnchor="middle" className="fill-white text-sm font-semibold">🌐 Headend</text>
      <text x="170" y="260" textAnchor="middle" className="fill-white text-xs">(Cloud)</text>
      <text x="170" y="275" textAnchor="middle" className="fill-white text-xs">Global Access</text>
      
      {/* Cloud Database */}
      <rect x="100" y="320" width="140" height="70" rx="8" fill="#ef4444" filter="url(#shadowHybrid)" />
      <text x="170" y="345" textAnchor="middle" className="fill-white text-sm font-semibold">🗄️ Database</text>
      <text x="170" y="360" textAnchor="middle" className="fill-white text-xs">(Managed)</text>
      <text x="170" y="375" textAnchor="middle" className="fill-white text-xs">High Availability</text>
      
      {/* On-Premise Headend */}
      <rect x="500" y="120" width="140" height="70" rx="8" fill="#3b82f6" filter="url(#shadowHybrid)" />
      <text x="570" y="145" textAnchor="middle" className="fill-white text-sm font-semibold">🌐 Headend</text>
      <text x="570" y="160" textAnchor="middle" className="fill-white text-xs">(On-Prem)</text>
      <text x="570" y="175" textAnchor="middle" className="fill-white text-xs">Local Traffic</text>
      
      {/* On-Premise Services */}
      <rect x="500" y="220" width="140" height="70" rx="8" fill="#f59e0b" filter="url(#shadowHybrid)" />
      <text x="570" y="245" textAnchor="middle" className="fill-white text-sm font-semibold">🏭 Legacy Apps</text>
      <text x="570" y="260" textAnchor="middle" className="fill-white text-xs">Internal Only</text>
      <text x="570" y="275" textAnchor="middle" className="fill-white text-xs">Zero Trust</text>
      
      {/* On-Premise Database */}
      <rect x="500" y="320" width="140" height="70" rx="8" fill="#6b7280" filter="url(#shadowHybrid)" />
      <text x="570" y="345" textAnchor="middle" className="fill-white text-sm font-semibold">🗃️ Local DB</text>
      <text x="570" y="360" textAnchor="middle" className="fill-white text-xs">Sensitive Data</text>
      <text x="570" y="375" textAnchor="middle" className="fill-white text-xs">Compliance</text>
      
      {/* Remote Workers */}
      <rect x="100" y="450" width="120" height="50" rx="6" fill="#8b5cf6" filter="url(#shadowHybrid)" />
      <text x="160" y="470" textAnchor="middle" className="fill-white text-xs font-semibold">🏠 Remote</text>
      <text x="160" y="485" textAnchor="middle" className="fill-white text-xs">Workers</text>
      
      {/* Office Users */}
      <rect x="520" y="450" width="120" height="50" rx="6" fill="#8b5cf6" filter="url(#shadowHybrid)" />
      <text x="580" y="470" textAnchor="middle" className="fill-white text-xs font-semibold">🏢 Office</text>
      <text x="580" y="485" textAnchor="middle" className="fill-white text-xs">Users</text>
      
      {/* WAN Connection */}
      <rect x="350" y="280" width="100" height="40" rx="20" fill="#ec4899" filter="url(#shadowHybrid)" />
      <text x="400" y="305" textAnchor="middle" className="fill-white text-xs font-semibold">🔗 WAN Link</text>
      
      {/* Connection Lines */}
      <line x1="240" y1="155" x2="500" y2="155" stroke="#10b981" strokeWidth="3" strokeDasharray="8,4" />
      <line x1="240" y1="255" x2="500" y2="255" stroke="#3b82f6" strokeWidth="3" strokeDasharray="8,4" />
      <line x1="350" y1="300" x2="450" y2="300" stroke="#ec4899" strokeWidth="4" />
      
      <line x1="160" y1="450" x2="170" y2="290" stroke="#8b5cf6" strokeWidth="2" />
      <line x1="580" y1="450" x2="570" y2="190" stroke="#8b5cf6" strokeWidth="2" />
      
      <defs>
        <marker id="arrowblue" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
          <polygon points="0,0 0,6 9,3" fill="#3b82f6" />
        </marker>
      </defs>
    </svg>
  );

  const renderOnPremiseDiagram = () => (
    <svg viewBox="0 0 800 500" className="w-full h-96">
      <defs>
        <linearGradient id="onpremBg" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{ stopColor: '#10b981', stopOpacity: 0.1 }} />
          <stop offset="100%" style={{ stopColor: '#059669', stopOpacity: 0.2 }} />
        </linearGradient>
        <filter id="shadowOnprem" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="2" dy="2" stdDeviation="3" floodOpacity="0.3"/>
        </filter>
      </defs>
      
      {/* Data Center */}
      <rect x="50" y="50" width="700" height="400" rx="20" fill="url(#onpremBg)" stroke="#10b981" strokeWidth="3" />
      <text x="400" y="80" textAnchor="middle" className="fill-green-600 text-lg font-semibold">🏢 Private Data Center - Air Gapped</text>
      
      {/* DMZ */}
      <rect x="100" y="120" width="250" height="300" rx="10" fill="rgba(239, 68, 68, 0.1)" stroke="#ef4444" strokeWidth="2" />
      <text x="225" y="140" textAnchor="middle" className="fill-red-600 text-sm font-semibold">🔥 DMZ Network</text>
      
      {/* Internal Network */}
      <rect x="400" y="120" width="300" height="300" rx="10" fill="rgba(59, 130, 246, 0.1)" stroke="#3b82f6" strokeWidth="2" />
      <text x="550" y="140" textAnchor="middle" className="fill-blue-600 text-sm font-semibold">🔒 Internal Network</text>
      
      {/* Manager in DMZ */}
      <rect x="130" y="180" width="120" height="70" rx="8" fill="#10b981" filter="url(#shadowOnprem)" />
      <text x="190" y="205" textAnchor="middle" className="fill-white text-sm font-semibold">📊 Manager</text>
      <text x="190" y="220" textAnchor="middle" className="fill-white text-xs">Certificate CA</text>
      <text x="190" y="235" textAnchor="middle" className="fill-white text-xs">Air Gapped</text>
      
      {/* Headend in DMZ */}
      <rect x="130" y="280" width="120" height="70" rx="8" fill="#3b82f6" filter="url(#shadowOnprem)" />
      <text x="190" y="305" textAnchor="middle" className="fill-white text-sm font-semibold">🌐 Headend</text>
      <text x="190" y="320" textAnchor="middle" className="fill-white text-xs">VPN Gateway</text>
      <text x="190" y="335" textAnchor="middle" className="fill-white text-xs">IDS/IPS</text>
      
      {/* Internal Services */}
      <rect x="430" y="180" width="120" height="70" rx="8" fill="#f59e0b" filter="url(#shadowOnprem)" />
      <text x="490" y="205" textAnchor="middle" className="fill-white text-sm font-semibold">🏭 ERP System</text>
      <text x="490" y="220" textAnchor="middle" className="fill-white text-xs">SAP/Oracle</text>
      <text x="490" y="235" textAnchor="middle" className="fill-white text-xs">Isolated</text>
      
      <rect x="570" y="180" width="120" height="70" rx="8" fill="#8b5cf6" filter="url(#shadowOnprem)" />
      <text x="630" y="205" textAnchor="middle" className="fill-white text-sm font-semibold">🗄️ Database</text>
      <text x="630" y="220" textAnchor="middle" className="fill-white text-xs">Production</text>
      <text x="630" y="235" textAnchor="middle" className="fill-white text-xs">Encrypted</text>
      
      <rect x="430" y="280" width="120" height="70" rx="8" fill="#ef4444" filter="url(#shadowOnprem)" />
      <text x="490" y="305" textAnchor="middle" className="fill-white text-sm font-semibold">🔐 LDAP/AD</text>
      <text x="490" y="320" textAnchor="middle" className="fill-white text-xs">Identity</text>
      <text x="490" y="335" textAnchor="middle" className="fill-white text-xs">Directory</text>
      
      <rect x="570" y="280" width="120" height="70" rx="8" fill="#6b7280" filter="url(#shadowOnprem)" />
      <text x="630" y="305" textAnchor="middle" className="fill-white text-sm font-semibold">📊 SIEM</text>
      <text x="630" y="320" textAnchor="middle" className="fill-white text-xs">Security</text>
      <text x="630" y="335" textAnchor="middle" className="fill-white text-xs">Monitoring</text>
      
      {/* Firewall */}
      <rect x="350" y="270" width="50" height="80" rx="8" fill="#dc2626" filter="url(#shadowOnprem)" />
      <text x="375" y="305" textAnchor="middle" className="fill-white text-xs font-semibold">🔥</text>
      <text x="375" y="320" textAnchor="middle" className="fill-white text-xs">Next-Gen</text>
      <text x="375" y="335" textAnchor="middle" className="fill-white text-xs">Firewall</text>
      
      {/* Connection Lines */}
      <line x1="250" y1="215" x2="350" y2="310" stroke="#10b981" strokeWidth="2" />
      <line x1="250" y1="315" x2="350" y2="310" stroke="#3b82f6" strokeWidth="2" />
      <line x1="400" y1="310" x2="430" y2="310" stroke="#ef4444" strokeWidth="3" />
    </svg>
  );

  const renderMultiRegionDiagram = () => (
    <svg viewBox="0 0 1000 600" className="w-full h-96">
      <defs>
        <linearGradient id="region1" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{ stopColor: '#3b82f6', stopOpacity: 0.1 }} />
          <stop offset="100%" style={{ stopColor: '#1d4ed8', stopOpacity: 0.2 }} />
        </linearGradient>
        <linearGradient id="region2" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{ stopColor: '#10b981', stopOpacity: 0.1 }} />
          <stop offset="100%" style={{ stopColor: '#059669', stopOpacity: 0.2 }} />
        </linearGradient>
        <linearGradient id="region3" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{ stopColor: '#f59e0b', stopOpacity: 0.1 }} />
          <stop offset="100%" style={{ stopColor: '#d97706', stopOpacity: 0.2 }} />
        </linearGradient>
        <filter id="shadowMulti" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="2" dy="2" stdDeviation="3" floodOpacity="0.3"/>
        </filter>
      </defs>
      
      {/* US Region */}
      <rect x="50" y="50" width="280" height="200" rx="15" fill="url(#region1)" stroke="#3b82f6" strokeWidth="2" />
      <text x="190" y="75" textAnchor="middle" className="fill-blue-600 text-sm font-semibold">🇺🇸 US-East-1</text>
      
      {/* EU Region */}
      <rect x="360" y="50" width="280" height="200" rx="15" fill="url(#region2)" stroke="#10b981" strokeWidth="2" />
      <text x="500" y="75" textAnchor="middle" className="fill-green-600 text-sm font-semibold">🇪🇺 EU-West-1</text>
      
      {/* APAC Region */}
      <rect x="670" y="50" width="280" height="200" rx="15" fill="url(#region3)" stroke="#f59e0b" strokeWidth="2" />
      <text x="810" y="75" textAnchor="middle" className="fill-yellow-600 text-sm font-semibold">🌏 APAC-Southeast-1</text>
      
      {/* Manager (Global) */}
      <rect x="450" y="300" width="120" height="80" rx="8" fill="#8b5cf6" filter="url(#shadowMulti)" />
      <text x="510" y="325" textAnchor="middle" className="fill-white text-sm font-semibold">📊 Manager</text>
      <text x="510" y="340" textAnchor="middle" className="fill-white text-xs">Global Control</text>
      <text x="510" y="355" textAnchor="middle" className="fill-white text-xs">Multi-Region</text>
      <text x="510" y="370" textAnchor="middle" className="fill-white text-xs">Orchestration</text>
      
      {/* US Components */}
      <rect x="80" y="100" width="100" height="60" rx="6" fill="#3b82f6" filter="url(#shadowMulti)" />
      <text x="130" y="125" textAnchor="middle" className="fill-white text-xs font-semibold">🌐 Headend</text>
      <text x="130" y="140" textAnchor="middle" className="fill-white text-xs">Virginia</text>
      <text x="130" y="155" textAnchor="middle" className="fill-white text-xs">WireGuard</text>
      
      <rect x="200" y="100" width="100" height="60" rx="6" fill="#ef4444" filter="url(#shadowMulti)" />
      <text x="250" y="125" textAnchor="middle" className="fill-white text-xs font-semibold">🗄️ Database</text>
      <text x="250" y="140" textAnchor="middle" className="fill-white text-xs">Primary</text>
      <text x="250" y="155" textAnchor="middle" className="fill-white text-xs">MySQL</text>
      
      <rect x="80" y="180" width="220" height="50" rx="6" fill="#6b7280" filter="url(#shadowMulti)" />
      <text x="190" y="200" textAnchor="middle" className="fill-white text-xs font-semibold">👥 Users: East Coast, Canada</text>
      <text x="190" y="215" textAnchor="middle" className="fill-white text-xs">Low Latency &lt; 20ms</text>
      
      {/* EU Components */}
      <rect x="390" y="100" width="100" height="60" rx="6" fill="#10b981" filter="url(#shadowMulti)" />
      <text x="440" y="125" textAnchor="middle" className="fill-white text-xs font-semibold">🌐 Headend</text>
      <text x="440" y="140" textAnchor="middle" className="fill-white text-xs">Frankfurt</text>
      <text x="440" y="155" textAnchor="middle" className="fill-white text-xs">WireGuard</text>
      
      <rect x="510" y="100" width="100" height="60" rx="6" fill="#ef4444" filter="url(#shadowMulti)" />
      <text x="560" y="125" textAnchor="middle" className="fill-white text-xs font-semibold">🗄️ Database</text>
      <text x="560" y="140" textAnchor="middle" className="fill-white text-xs">Replica</text>
      <text x="560" y="155" textAnchor="middle" className="fill-white text-xs">Read-Only</text>
      
      <rect x="390" y="180" width="220" height="50" rx="6" fill="#6b7280" filter="url(#shadowMulti)" />
      <text x="500" y="200" textAnchor="middle" className="fill-white text-xs font-semibold">👥 Users: Europe, Middle East</text>
      <text x="500" y="215" textAnchor="middle" className="fill-white text-xs">GDPR Compliant</text>
      
      {/* APAC Components */}
      <rect x="700" y="100" width="100" height="60" rx="6" fill="#f59e0b" filter="url(#shadowMulti)" />
      <text x="750" y="125" textAnchor="middle" className="fill-white text-xs font-semibold">🌐 Headend</text>
      <text x="750" y="140" textAnchor="middle" className="fill-white text-xs">Singapore</text>
      <text x="750" y="155" textAnchor="middle" className="fill-white text-xs">WireGuard</text>
      
      <rect x="820" y="100" width="100" height="60" rx="6" fill="#ef4444" filter="url(#shadowMulti)" />
      <text x="870" y="125" textAnchor="middle" className="fill-white text-xs font-semibold">🗄️ Database</text>
      <text x="870" y="140" textAnchor="middle" className="fill-white text-xs">Local Cache</text>
      <text x="870" y="155" textAnchor="middle" className="fill-white text-xs">Redis</text>
      
      <rect x="700" y="180" width="220" height="50" rx="6" fill="#6b7280" filter="url(#shadowMulti)" />
      <text x="810" y="200" textAnchor="middle" className="fill-white text-xs font-semibold">👥 Users: Asia Pacific</text>
      <text x="810" y="215" textAnchor="middle" className="fill-white text-xs">Data Sovereignty</text>
      
      {/* Global Network */}
      <circle cx="500" cy="450" r="80" fill="rgba(139, 92, 246, 0.1)" stroke="#8b5cf6" strokeWidth="2" strokeDasharray="5,5" />
      <text x="500" y="445" textAnchor="middle" className="fill-purple-600 text-sm font-semibold">🌐 Global Network</text>
      <text x="500" y="460" textAnchor="middle" className="fill-purple-600 text-xs">Load Balancing</text>
      <text x="500" y="475" textAnchor="middle" className="fill-purple-600 text-xs">Health Checks</text>
      
      {/* Mobile Users */}
      <rect x="100" y="540" width="120" height="40" rx="6" fill="#ec4899" filter="url(#shadowMulti)" />
      <text x="160" y="555" textAnchor="middle" className="fill-white text-xs font-semibold">📱 Mobile Users</text>
      <text x="160" y="570" textAnchor="middle" className="fill-white text-xs">Global Roaming</text>
      
      <rect x="440" y="540" width="120" height="40" rx="6" fill="#ec4899" filter="url(#shadowMulti)" />
      <text x="500" y="555" textAnchor="middle" className="fill-white text-xs font-semibold">💼 Business Users</text>
      <text x="500" y="570" textAnchor="middle" className="fill-white text-xs">Compliance</text>
      
      <rect x="780" y="540" width="120" height="40" rx="6" fill="#ec4899" filter="url(#shadowMulti)" />
      <text x="840" y="555" textAnchor="middle" className="fill-white text-xs font-semibold">🏭 Remote Sites</text>
      <text x="840" y="570" textAnchor="middle" className="fill-white text-xs">Site-to-Site</text>
      
      {/* Connection Lines */}
      <line x1="190" y1="250" x2="480" y2="300" stroke="#3b82f6" strokeWidth="2" strokeDasharray="5,5" />
      <line x1="500" y1="250" x2="510" y2="300" stroke="#10b981" strokeWidth="2" strokeDasharray="5,5" />
      <line x1="810" y1="250" x2="540" y2="300" stroke="#f59e0b" strokeWidth="2" strokeDasharray="5,5" />
      
      <line x1="160" y1="540" x2="470" y2="430" stroke="#ec4899" strokeWidth="2" strokeDasharray="3,3" />
      <line x1="500" y1="540" x2="500" y2="430" stroke="#ec4899" strokeWidth="2" strokeDasharray="3,3" />
      <line x1="840" y1="540" x2="530" y2="430" stroke="#ec4899" strokeWidth="2" strokeDasharray="3,3" />
    </svg>
  );

  switch (scenario) {
    case 'cloud': return renderCloudDiagram();
    case 'hybrid': return renderHybridDiagram();
    case 'onpremise': return renderOnPremiseDiagram();
    case 'multiregion': return renderMultiRegionDiagram();
    default: return renderCloudDiagram();
  }
};

const SolutionsPage: React.FC = () => {
  const [activeScenario, setActiveScenario] = useState<string>('cloud');

  const deploymentScenarios: DeploymentScenario[] = [
    {
      id: 'cloud',
      title: 'Cloud-Native Deployment',
      subtitle: 'Fully managed in public cloud',
      description: 'Deploy Tobogganing in AWS, Azure, or Google Cloud with auto-scaling, high availability, and global reach. Perfect for organizations wanting to minimize infrastructure management while maximizing security and performance.',
      benefits: [
        'Auto-scaling based on demand',
        'Global load balancing',
        'Managed database services',
        'Built-in disaster recovery',
        'Pay-as-you-scale pricing',
        'Automatic security updates'
      ],
      useCases: [
        'SaaS companies with global users',
        'Startups needing rapid deployment',
        'Organizations with variable workloads',
        'Companies prioritizing uptime'
      ],
      complexity: 'Low',
      icon: '☁️',
      color: 'blue'
    },
    {
      id: 'hybrid',
      title: 'Hybrid Cloud Architecture',
      subtitle: 'Best of both worlds',
      description: 'Combine public cloud flexibility with on-premise control. Keep sensitive data on-premise while leveraging cloud scalability for global access. Ideal for organizations with compliance requirements and existing infrastructure investments.',
      benefits: [
        'Data sovereignty control',
        'Compliance with regulations',
        'Reduced latency for local users',
        'Cloud scalability for global access',
        'Cost optimization',
        'Gradual cloud migration path'
      ],
      useCases: [
        'Financial institutions',
        'Healthcare organizations',
        'Government agencies',
        'Enterprises with legacy systems'
      ],
      complexity: 'Medium',
      icon: '🌉',
      color: 'green'
    },
    {
      id: 'onpremise',
      title: 'On-Premise Deployment',
      subtitle: 'Complete control and isolation',
      description: 'Deploy entirely within your own data centers with air-gapped security. Maximum control over data, compliance, and customization. Perfect for highly regulated industries and security-sensitive environments.',
      benefits: [
        'Complete data control',
        'Air-gapped security',
        'Custom compliance policies',
        'No cloud dependency',
        'Predictable costs',
        'Maximum customization'
      ],
      useCases: [
        'Defense contractors',
        'Critical infrastructure',
        'Highly regulated industries',
        'Organizations with strict data policies'
      ],
      complexity: 'High',
      icon: '🏢',
      color: 'purple'
    },
    {
      id: 'multiregion',
      title: 'Multi-Region Global',
      subtitle: 'Worldwide presence with local compliance',
      description: 'Deploy across multiple regions with intelligent routing, data residency compliance, and disaster recovery. Provide optimal performance for global users while meeting local regulatory requirements.',
      benefits: [
        'Global performance optimization',
        'Data residency compliance',
        'Disaster recovery across regions',
        'Local regulatory compliance',
        'Intelligent traffic routing',
        'Regional failover capabilities'
      ],
      useCases: [
        'Multinational corporations',
        'Global SaaS providers',
        'CDN and media companies',
        'Organizations with worldwide presence'
      ],
      complexity: 'High',
      icon: '🌍',
      color: 'orange'
    }
  ];

  const getComplexityColor = (complexity: string) => {
    switch (complexity) {
      case 'Low': return 'text-green-600 bg-green-100';
      case 'Medium': return 'text-yellow-600 bg-yellow-100';
      case 'High': return 'text-red-600 bg-red-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  };

  const getScenarioButtonClass = (scenarioId: string) => {
    const baseClass = 'px-6 py-3 rounded-lg font-semibold transition-all duration-200 ';
    if (activeScenario === scenarioId) {
      const scenario = deploymentScenarios.find(s => s.id === scenarioId);
      switch (scenario?.color) {
        case 'blue': return baseClass + 'bg-blue-600 text-white shadow-lg';
        case 'green': return baseClass + 'bg-green-600 text-white shadow-lg';
        case 'purple': return baseClass + 'bg-purple-600 text-white shadow-lg';
        case 'orange': return baseClass + 'bg-orange-600 text-white shadow-lg';
        default: return baseClass + 'bg-gray-600 text-white shadow-lg';
      }
    }
    return baseClass + 'bg-gray-200 text-gray-700 hover:bg-gray-300';
  };

  const activeScenarioData = deploymentScenarios.find(s => s.id === activeScenario);

  return (
    <div className="min-h-screen bg-white">
      <Head>
        <title>Enterprise Solutions - Tobogganing SASE</title>
        <meta name="description" content="Explore Tobogganing's flexible deployment scenarios: cloud-native, hybrid, on-premise, and multi-region architectures for enterprise SASE solutions." />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      {/* Header */}
      <header className="bg-gradient-to-r from-blue-600 to-purple-600 text-white py-6">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold">🛷 Tobogganing</h1>
              <p className="text-blue-100">Enterprise SASE Solutions</p>
            </div>
            <nav className="space-x-6">
              <a href="/" className="text-blue-100 hover:text-white transition-colors">Home</a>
              <a href="/solutions" className="text-white font-semibold">Solutions</a>
              <a href="https://github.com/penguintechinc/Tobogganing" className="text-blue-100 hover:text-white transition-colors">GitHub</a>
            </nav>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="py-16 bg-gradient-to-br from-gray-50 to-blue-50">
        <div className="max-w-7xl mx-auto px-4 text-center">
          <h2 className="text-5xl font-bold text-gray-900 mb-6">
            Enterprise Deployment Solutions
          </h2>
          <p className="text-xl text-gray-600 mb-8 max-w-4xl mx-auto">
            Choose the perfect architecture for your organization. From cloud-native scalability to air-gapped security, 
            Tobogganing adapts to your infrastructure requirements while delivering Zero Trust Network Access everywhere.
          </p>
          <div className="flex flex-wrap justify-center gap-4">
            {deploymentScenarios.map((scenario) => (
              <button
                key={scenario.id}
                onClick={() => setActiveScenario(scenario.id)}
                className={getScenarioButtonClass(scenario.id)}
              >
                <span className="mr-2">{scenario.icon}</span>
                {scenario.title}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Active Scenario Details */}
      {activeScenarioData && (
        <section className="py-16">
          <div className="max-w-7xl mx-auto px-4">
            <div className="grid lg:grid-cols-2 gap-12 items-start">
              
              {/* Scenario Information */}
              <div className="space-y-8">
                <div>
                  <div className="flex items-center gap-4 mb-4">
                    <div className={`w-16 h-16 bg-${activeScenarioData.color}-100 rounded-lg flex items-center justify-center`}>
                      <span className="text-3xl">{activeScenarioData.icon}</span>
                    </div>
                    <div>
                      <h3 className="text-3xl font-bold text-gray-900">{activeScenarioData.title}</h3>
                      <p className="text-lg text-gray-600">{activeScenarioData.subtitle}</p>
                    </div>
                    <span className={`px-3 py-1 rounded-full text-sm font-semibold ${getComplexityColor(activeScenarioData.complexity)}`}>
                      {activeScenarioData.complexity} Complexity
                    </span>
                  </div>
                  <p className="text-gray-700 leading-relaxed">{activeScenarioData.description}</p>
                </div>

                <div className="grid md:grid-cols-2 gap-8">
                  {/* Benefits */}
                  <div>
                    <h4 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
                      <span className="mr-2">✅</span> Key Benefits
                    </h4>
                    <ul className="space-y-2">
                      {activeScenarioData.benefits.map((benefit, index) => (
                        <li key={index} className="flex items-start gap-2">
                          <span className="text-green-500 mt-1">•</span>
                          <span className="text-gray-700">{benefit}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Use Cases */}
                  <div>
                    <h4 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
                      <span className="mr-2">🎯</span> Ideal For
                    </h4>
                    <ul className="space-y-2">
                      {activeScenarioData.useCases.map((useCase, index) => (
                        <li key={index} className="flex items-start gap-2">
                          <span className="text-blue-500 mt-1">•</span>
                          <span className="text-gray-700">{useCase}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>

              {/* Dataflow Diagram */}
              <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-6">
                <h4 className="text-xl font-semibold text-gray-900 mb-4 text-center">
                  Architecture & Data Flow
                </h4>
                <DataflowDiagram scenario={activeScenario} />
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Technical Specifications */}
      <section className="py-16 bg-gray-50">
        <div className="max-w-7xl mx-auto px-4">
          <h3 className="text-3xl font-bold text-center text-gray-900 mb-12">
            Technical Architecture Components
          </h3>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            
            {/* Manager Service */}
            <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6 hover:shadow-lg transition-shadow">
              <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mb-4">
                <span className="text-green-600 text-2xl">📊</span>
              </div>
              <h4 className="text-xl font-semibold mb-3">Manager Service</h4>
              <div className="space-y-2 text-sm text-gray-600">
                <p><strong>Technology:</strong> Python 3.12, py4web</p>
                <p><strong>Database:</strong> MySQL/PostgreSQL with replicas</p>
                <p><strong>Features:</strong> Certificate management, user portal, API</p>
                <p><strong>Monitoring:</strong> Prometheus metrics, health checks</p>
                <p><strong>Authentication:</strong> JWT, bcrypt, session management</p>
              </div>
            </div>

            {/* Headend Server */}
            <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6 hover:shadow-lg transition-shadow">
              <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mb-4">
                <span className="text-blue-600 text-2xl">🌐</span>
              </div>
              <h4 className="text-xl font-semibold mb-3">Headend Server</h4>
              <div className="space-y-2 text-sm text-gray-600">
                <p><strong>Technology:</strong> Go 1.23+, WireGuard</p>
                <p><strong>Protocols:</strong> TCP, UDP, HTTP/HTTPS proxy</p>
                <p><strong>Security:</strong> IDS/IPS integration, traffic mirroring</p>
                <p><strong>Authentication:</strong> X.509 + JWT/SAML/OAuth2</p>
                <p><strong>Networking:</strong> VRF support, OSPF routing</p>
              </div>
            </div>

            {/* Client Applications */}
            <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6 hover:shadow-lg transition-shadow">
              <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mb-4">
                <span className="text-purple-600 text-2xl">💻</span>
              </div>
              <h4 className="text-xl font-semibold mb-3">Client Applications</h4>
              <div className="space-y-2 text-sm text-gray-600">
                <p><strong>Native:</strong> macOS, Windows, Linux (AMD64/ARM64)</p>
                <p><strong>Mobile:</strong> React Native (iOS/Android)</p>
                <p><strong>Container:</strong> Docker multi-arch</p>
                <p><strong>Features:</strong> System tray, auto-updates, split tunneling</p>
                <p><strong>Architectures:</strong> x86_64, ARM64, ARMv7, MIPS</p>
              </div>
            </div>

            {/* Security Features */}
            <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6 hover:shadow-lg transition-shadow">
              <div className="w-12 h-12 bg-red-100 rounded-lg flex items-center justify-center mb-4">
                <span className="text-red-600 text-2xl">🔒</span>
              </div>
              <h4 className="text-xl font-semibold mb-3">Security Layer</h4>
              <div className="space-y-2 text-sm text-gray-600">
                <p><strong>Encryption:</strong> WireGuard, TLS 1.3</p>
                <p><strong>Authentication:</strong> Dual-layer (cert + token)</p>
                <p><strong>Firewall:</strong> Advanced rule engine</p>
                <p><strong>IDS/IPS:</strong> Suricata integration</p>
                <p><strong>Audit:</strong> Comprehensive logging</p>
              </div>
            </div>

            {/* Monitoring & Ops */}
            <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6 hover:shadow-lg transition-shadow">
              <div className="w-12 h-12 bg-yellow-100 rounded-lg flex items-center justify-center mb-4">
                <span className="text-yellow-600 text-2xl">📈</span>
              </div>
              <h4 className="text-xl font-semibold mb-3">Monitoring & Ops</h4>
              <div className="space-y-2 text-sm text-gray-600">
                <p><strong>Metrics:</strong> Prometheus, Grafana dashboards</p>
                <p><strong>Logging:</strong> Structured logs, syslog integration</p>
                <p><strong>Health:</strong> /health, /healthz endpoints</p>
                <p><strong>Alerting:</strong> Connection/performance alerts</p>
                <p><strong>Analytics:</strong> Real-time traffic analysis</p>
              </div>
            </div>

            {/* Deployment */}
            <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6 hover:shadow-lg transition-shadow">
              <div className="w-12 h-12 bg-indigo-100 rounded-lg flex items-center justify-center mb-4">
                <span className="text-indigo-600 text-2xl">🚀</span>
              </div>
              <h4 className="text-xl font-semibold mb-3">Deployment</h4>
              <div className="space-y-2 text-sm text-gray-600">
                <p><strong>Containers:</strong> Docker, Kubernetes ready</p>
                <p><strong>Scaling:</strong> Horizontal auto-scaling</p>
                <p><strong>CI/CD:</strong> GitHub Actions workflows</p>
                <p><strong>Infrastructure:</strong> Terraform support</p>
                <p><strong>Backup:</strong> Automated with S3/MinIO</p>
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* Performance Metrics */}
      <section className="py-16">
        <div className="max-w-7xl mx-auto px-4">
          <h3 className="text-3xl font-bold text-center text-gray-900 mb-12">
            Performance & Scale
          </h3>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8 text-center">
            <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
              <div className="text-3xl font-bold text-blue-600 mb-2">10Gb+</div>
              <div className="text-gray-600">Throughput per headend</div>
              <div className="text-sm text-gray-500 mt-2">WireGuard optimization</div>
            </div>
            <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
              <div className="text-3xl font-bold text-green-600 mb-2">10k+</div>
              <div className="text-gray-600">Concurrent connections</div>
              <div className="text-sm text-gray-500 mt-2">Per headend instance</div>
            </div>
            <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
              <div className="text-3xl font-bold text-purple-600 mb-2">&lt;5ms</div>
              <div className="text-gray-600">Connection latency</div>
              <div className="text-sm text-gray-500 mt-2">Regional deployment</div>
            </div>
            <div className="bg-white rounded-xl shadow-md border border-gray-200 p-6">
              <div className="text-3xl font-bold text-orange-600 mb-2">99.99%</div>
              <div className="text-gray-600">Uptime SLA</div>
              <div className="text-sm text-gray-500 mt-2">Multi-region failover</div>
            </div>
          </div>
        </div>
      </section>

      {/* Call to Action */}
      <section className="py-16 bg-gradient-to-r from-blue-600 to-purple-600 text-white">
        <div className="max-w-4xl mx-auto px-4 text-center">
          <h3 className="text-3xl font-bold mb-6">Ready to Deploy Your SASE Solution?</h3>
          <p className="text-xl mb-8 opacity-90">
            Start with our open source community edition or contact us for enterprise features and support.
          </p>
          <div className="flex flex-wrap justify-center gap-4">
            <a 
              href={process.env.NEXT_PUBLIC_DOCS_URL || 'https://docs.tobogganing.io'}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-white text-blue-600 px-8 py-4 rounded-lg font-semibold hover:bg-gray-100 transition-colors flex items-center gap-2"
            >
              <span>📖</span> View Documentation
            </a>
            <a 
              href="https://github.com/penguintechinc/Tobogganing/releases" 
              className="bg-transparent border-2 border-white text-white px-8 py-4 rounded-lg font-semibold hover:bg-white hover:text-blue-600 transition-colors flex items-center gap-2"
            >
              <span>⬇️</span> Download Clients
            </a>
            <a 
              href="mailto:enterprise@penguintech.io" 
              className="bg-green-500 text-white px-8 py-4 rounded-lg font-semibold hover:bg-green-600 transition-colors flex items-center gap-2"
            >
              <span>💼</span> Enterprise Inquiry
            </a>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-800 text-white py-12">
        <div className="max-w-7xl mx-auto px-4">
          <div className="grid md:grid-cols-4 gap-8">
            <div>
              <h4 className="text-lg font-semibold mb-4">🛷 Tobogganing</h4>
              <p className="text-gray-400 text-sm">
                Open Source SASE solution implementing Zero Trust Network Architecture.
              </p>
            </div>
            <div>
              <h4 className="text-lg font-semibold mb-4">Solutions</h4>
              <ul className="space-y-2 text-sm">
                <li><a href="#" className="text-gray-400 hover:text-white">Cloud Deployment</a></li>
                <li><a href="#" className="text-gray-400 hover:text-white">Hybrid Architecture</a></li>
                <li><a href="#" className="text-gray-400 hover:text-white">On-Premise</a></li>
                <li><a href="#" className="text-gray-400 hover:text-white">Multi-Region</a></li>
              </ul>
            </div>
            <div>
              <h4 className="text-lg font-semibold mb-4">Resources</h4>
              <ul className="space-y-2 text-sm">
                <li><a href="https://github.com/penguintechinc/Tobogganing" className="text-gray-400 hover:text-white">GitHub Repository</a></li>
                <li><a href={process.env.NEXT_PUBLIC_DOCS_URL || 'https://docs.tobogganing.io'} target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-white">Documentation</a></li>
                <li><a href="https://github.com/penguintechinc/Tobogganing/releases" className="text-gray-400 hover:text-white">Downloads</a></li>
                <li><a href="https://github.com/penguintechinc/Tobogganing/issues" className="text-gray-400 hover:text-white">Support</a></li>
              </ul>
            </div>
            <div>
              <h4 className="text-lg font-semibold mb-4">Contact</h4>
              <ul className="space-y-2 text-sm">
                <li><a href="mailto:info@penguintech.io" className="text-gray-400 hover:text-white">General Inquiries</a></li>
                <li><a href="mailto:enterprise@penguintech.io" className="text-gray-400 hover:text-white">Enterprise Sales</a></li>
                <li><a href="mailto:support@penguintech.io" className="text-gray-400 hover:text-white">Technical Support</a></li>
              </ul>
            </div>
          </div>
          <div className="border-t border-gray-700 mt-8 pt-8 text-center">
            <p className="text-gray-400 text-sm">
              © 2024 Tobogganing. Open Source MIT License. Made with ❤️ for Zero Trust security.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default SolutionsPage;