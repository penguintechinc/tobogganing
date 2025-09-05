import React, { useState } from 'react';
import Head from 'next/head';
import {
  ChartBarIcon,
  CogIcon,
  ShieldCheckIcon,
  UsersIcon,
  ServerIcon,
  CloudIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowUpIcon,
  ArrowDownIcon,
  EyeIcon,
  PencilIcon,
  TrashIcon,
  PlusIcon
} from '@heroicons/react/24/outline';

// Mock data for dashboard
const mockStats = {
  totalClients: 847,
  activeConnections: 731,
  headendServers: 12,
  totalTraffic: '2.4 TB',
  avgLatency: '23ms',
  uptime: '99.97%'
};

const mockAlerts = [
  { id: 1, type: 'warning', message: 'High CPU usage on Headend US-East-2', time: '5 min ago' },
  { id: 2, type: 'info', message: 'New client registered: mobile-device-4821', time: '12 min ago' },
  { id: 3, type: 'error', message: 'Certificate expiring in 7 days for region EU-West', time: '1 hour ago' }
];

const mockUsers = [
  { id: 1, name: 'John Smith', email: 'john.smith@company.com', role: 'Admin', status: 'active', lastLogin: '2 hours ago' },
  { id: 2, name: 'Sarah Johnson', email: 'sarah.j@company.com', role: 'Reporter', status: 'active', lastLogin: '15 min ago' },
  { id: 3, name: 'Mike Chen', email: 'mike.chen@company.com', role: 'Admin', status: 'inactive', lastLogin: '3 days ago' },
];

const mockFirewallRules = [
  { id: 1, name: 'Allow Corporate Domains', type: 'domain', target: '*.company.com', action: 'allow', priority: 10 },
  { id: 2, name: 'Block Social Media', type: 'domain', target: '*.facebook.com', action: 'deny', priority: 5 },
  { id: 3, name: 'Allow HTTPS Traffic', type: 'protocol', target: 'tcp:*:*->*:443', action: 'allow', priority: 20 },
];

const mockClients = [
  { id: 1, name: 'laptop-john-001', os: 'macOS 14.0', type: 'GUI', lastSeen: '2 min ago', status: 'online', ip: '10.0.1.15' },
  { id: 2, name: 'server-prod-backend', os: 'Ubuntu 22.04', type: 'Headless', lastSeen: '30 sec ago', status: 'online', ip: '10.0.1.32' },
  { id: 3, name: 'mobile-sarah-phone', os: 'iOS 17.1', type: 'Mobile', lastSeen: '5 min ago', status: 'warning', ip: '10.0.1.78' },
];

const mockVRFs = [
  { id: 1, name: 'corporate-wan', rd: '65000:100', networks: ['10.0.0.0/16', '192.168.1.0/24'], ospfArea: '0.0.0.0' },
  { id: 2, name: 'customer-a', rd: '65000:200', networks: ['172.16.0.0/16'], ospfArea: '0.0.0.1' },
];

const PortalPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [selectedUser, setSelectedUser] = useState<number | null>(null);

  const tabs = [
    { id: 'dashboard', name: 'Dashboard', icon: ChartBarIcon },
    { id: 'users', name: 'Users', icon: UsersIcon },
    { id: 'firewall', name: 'Firewall', icon: ShieldCheckIcon },
    { id: 'networks', name: 'Networks', icon: CogIcon },
    { id: 'clients', name: 'Clients', icon: ServerIcon },
    { id: 'monitoring', name: 'Monitoring', icon: CloudIcon }
  ];

  const renderDashboard = () => (
    <div className="space-y-6">
      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-6">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <UsersIcon className="h-8 w-8 text-blue-600" />
            </div>
            <div className="ml-5 w-0 flex-1">
              <dl>
                <dt className="text-sm font-medium text-gray-500 truncate">Total Clients</dt>
                <dd className="text-2xl font-bold text-gray-900">{mockStats.totalClients}</dd>
              </dl>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <CheckCircleIcon className="h-8 w-8 text-green-600" />
            </div>
            <div className="ml-5 w-0 flex-1">
              <dl>
                <dt className="text-sm font-medium text-gray-500 truncate">Active Connections</dt>
                <dd className="text-2xl font-bold text-gray-900">{mockStats.activeConnections}</dd>
              </dl>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <ServerIcon className="h-8 w-8 text-purple-600" />
            </div>
            <div className="ml-5 w-0 flex-1">
              <dl>
                <dt className="text-sm font-medium text-gray-500 truncate">Headend Servers</dt>
                <dd className="text-2xl font-bold text-gray-900">{mockStats.headendServers}</dd>
              </dl>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <ArrowUpIcon className="h-8 w-8 text-indigo-600" />
            </div>
            <div className="ml-5 w-0 flex-1">
              <dl>
                <dt className="text-sm font-medium text-gray-500 truncate">Total Traffic</dt>
                <dd className="text-2xl font-bold text-gray-900">{mockStats.totalTraffic}</dd>
              </dl>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <CloudIcon className="h-8 w-8 text-yellow-600" />
            </div>
            <div className="ml-5 w-0 flex-1">
              <dl>
                <dt className="text-sm font-medium text-gray-500 truncate">Avg Latency</dt>
                <dd className="text-2xl font-bold text-gray-900">{mockStats.avgLatency}</dd>
              </dl>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <CheckCircleIcon className="h-8 w-8 text-green-600" />
            </div>
            <div className="ml-5 w-0 flex-1">
              <dl>
                <dt className="text-sm font-medium text-gray-500 truncate">Uptime</dt>
                <dd className="text-2xl font-bold text-gray-900">{mockStats.uptime}</dd>
              </dl>
            </div>
          </div>
        </div>
      </div>

      {/* Charts and Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Traffic Chart */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Traffic Overview</h3>
          <div className="h-64 bg-gray-50 rounded flex items-center justify-center">
            <svg viewBox="0 0 400 200" className="w-full h-full">
              <defs>
                <linearGradient id="trafficGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" style={{ stopColor: '#3b82f6', stopOpacity: 0.8 }} />
                  <stop offset="100%" style={{ stopColor: '#3b82f6', stopOpacity: 0.1 }} />
                </linearGradient>
              </defs>
              <path d="M 20 180 Q 100 120, 180 140 T 380 80" stroke="#3b82f6" strokeWidth="3" fill="none"/>
              <path d="M 20 180 Q 100 120, 180 140 T 380 80 L 380 180 L 20 180 Z" fill="url(#trafficGradient)"/>
              <text x="200" y="30" textAnchor="middle" className="fill-gray-600 text-sm">Network Traffic (24h)</text>
            </svg>
          </div>
        </div>

        {/* Recent Alerts */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Recent Alerts</h3>
          <div className="space-y-3">
            {mockAlerts.map((alert) => (
              <div key={alert.id} className="flex items-start space-x-3">
                <div className="flex-shrink-0">
                  {alert.type === 'warning' && <ExclamationTriangleIcon className="h-5 w-5 text-yellow-500" />}
                  {alert.type === 'error' && <XCircleIcon className="h-5 w-5 text-red-500" />}
                  {alert.type === 'info' && <CheckCircleIcon className="h-5 w-5 text-blue-500" />}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-gray-900">{alert.message}</p>
                  <p className="text-sm text-gray-500">{alert.time}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );

  const renderUsers = () => (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium text-gray-900">User Management</h3>
        <button className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 flex items-center space-x-2">
          <PlusIcon className="h-4 w-4" />
          <span>Add User</span>
        </button>
      </div>

      <div className="bg-white shadow rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Role</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Last Login</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {mockUsers.map((user) => (
              <tr key={user.id}>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div>
                    <div className="text-sm font-medium text-gray-900">{user.name}</div>
                    <div className="text-sm text-gray-500">{user.email}</div>
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                    user.role === 'Admin' ? 'bg-purple-100 text-purple-800' : 'bg-green-100 text-green-800'
                  }`}>
                    {user.role}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                    user.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                  }`}>
                    {user.status}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{user.lastLogin}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  <div className="flex space-x-2">
                    <button className="text-blue-600 hover:text-blue-900">
                      <EyeIcon className="h-4 w-4" />
                    </button>
                    <button className="text-yellow-600 hover:text-yellow-900">
                      <PencilIcon className="h-4 w-4" />
                    </button>
                    <button className="text-red-600 hover:text-red-900">
                      <TrashIcon className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  const renderFirewall = () => (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium text-gray-900">Firewall Rules</h3>
        <button className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 flex items-center space-x-2">
          <PlusIcon className="h-4 w-4" />
          <span>Add Rule</span>
        </button>
      </div>

      <div className="bg-white shadow rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Rule Name</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Target</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Priority</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {mockFirewallRules.map((rule) => (
              <tr key={rule.id}>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{rule.name}</td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-blue-100 text-blue-800">
                    {rule.type}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 font-mono">{rule.target}</td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                    rule.action === 'allow' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                  }`}>
                    {rule.action}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{rule.priority}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  <div className="flex space-x-2">
                    <button className="text-yellow-600 hover:text-yellow-900">
                      <PencilIcon className="h-4 w-4" />
                    </button>
                    <button className="text-red-600 hover:text-red-900">
                      <TrashIcon className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  const renderNetworks = () => (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium text-gray-900">VRF & Network Configuration</h3>
        <button className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 flex items-center space-x-2">
          <PlusIcon className="h-4 w-4" />
          <span>Create VRF</span>
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {mockVRFs.map((vrf) => (
          <div key={vrf.id} className="bg-white shadow rounded-lg p-6">
            <div className="flex justify-between items-start mb-4">
              <div>
                <h4 className="text-lg font-medium text-gray-900">{vrf.name}</h4>
                <p className="text-sm text-gray-500">Route Distinguisher: {vrf.rd}</p>
              </div>
              <div className="flex space-x-2">
                <button className="text-yellow-600 hover:text-yellow-900">
                  <PencilIcon className="h-4 w-4" />
                </button>
                <button className="text-red-600 hover:text-red-900">
                  <TrashIcon className="h-4 w-4" />
                </button>
              </div>
            </div>
            
            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium text-gray-700">Networks:</label>
                <div className="mt-1 space-y-1">
                  {vrf.networks.map((network, index) => (
                    <span key={index} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 mr-2">
                      {network}
                    </span>
                  ))}
                </div>
              </div>
              
              <div>
                <label className="text-sm font-medium text-gray-700">OSPF Area:</label>
                <p className="text-sm text-gray-900 font-mono">{vrf.ospfArea}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  const renderClients = () => (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-medium text-gray-900">Client Management</h3>
        <button className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 flex items-center space-x-2">
          <PlusIcon className="h-4 w-4" />
          <span>Register Client</span>
        </button>
      </div>

      <div className="bg-white shadow rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Client</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Type</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">IP Address</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Last Seen</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {mockClients.map((client) => (
              <tr key={client.id}>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div>
                    <div className="text-sm font-medium text-gray-900">{client.name}</div>
                    <div className="text-sm text-gray-500">{client.os}</div>
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-purple-100 text-purple-800">
                    {client.type}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                    client.status === 'online' ? 'bg-green-100 text-green-800' : 
                    client.status === 'warning' ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800'
                  }`}>
                    {client.status}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 font-mono">{client.ip}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{client.lastSeen}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  <div className="flex space-x-2">
                    <button className="text-blue-600 hover:text-blue-900">
                      <EyeIcon className="h-4 w-4" />
                    </button>
                    <button className="text-yellow-600 hover:text-yellow-900">
                      <PencilIcon className="h-4 w-4" />
                    </button>
                    <button className="text-red-600 hover:text-red-900">
                      <TrashIcon className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  const renderMonitoring = () => (
    <div className="space-y-6">
      <h3 className="text-lg font-medium text-gray-900">Real-time Monitoring</h3>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* System Health */}
        <div className="bg-white shadow rounded-lg p-6">
          <h4 className="text-md font-medium text-gray-900 mb-4">System Health</h4>
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">Manager Service</span>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                Healthy
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">Headend US-East-1</span>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                Healthy
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">Headend US-West-2</span>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                Warning
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">Database Replica</span>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                Synced
              </span>
            </div>
          </div>
        </div>

        {/* Performance Metrics */}
        <div className="bg-white shadow rounded-lg p-6">
          <h4 className="text-md font-medium text-gray-900 mb-4">Performance Metrics</h4>
          <div className="h-48 bg-gray-50 rounded flex items-center justify-center">
            <svg viewBox="0 0 300 150" className="w-full h-full">
              <defs>
                <linearGradient id="cpuGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" style={{ stopColor: '#10b981', stopOpacity: 0.8 }} />
                  <stop offset="100%" style={{ stopColor: '#10b981', stopOpacity: 0.1 }} />
                </linearGradient>
                <linearGradient id="memoryGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" style={{ stopColor: '#f59e0b', stopOpacity: 0.8 }} />
                  <stop offset="100%" style={{ stopColor: '#f59e0b', stopOpacity: 0.1 }} />
                </linearGradient>
              </defs>
              
              {/* CPU Usage Line */}
              <path d="M 20 120 Q 60 100, 100 90 T 180 80 T 280 85" stroke="#10b981" strokeWidth="2" fill="none"/>
              <path d="M 20 120 Q 60 100, 100 90 T 180 80 T 280 85 L 280 140 L 20 140 Z" fill="url(#cpuGradient)"/>
              
              {/* Memory Usage Line */}
              <path d="M 20 130 Q 60 110, 100 105 T 180 95 T 280 100" stroke="#f59e0b" strokeWidth="2" fill="none"/>
              
              <text x="150" y="20" textAnchor="middle" className="fill-gray-600 text-sm font-medium">System Resources</text>
              <text x="30" y="40" className="fill-green-600 text-xs">CPU</text>
              <text x="70" y="40" className="fill-yellow-600 text-xs">Memory</text>
            </svg>
          </div>
        </div>
      </div>

      {/* Logs */}
      <div className="bg-white shadow rounded-lg p-6">
        <h4 className="text-md font-medium text-gray-900 mb-4">Recent Logs</h4>
        <div className="bg-black rounded p-4 font-mono text-sm">
          <div className="text-green-400">2024-09-04 15:32:41 [INFO] Client laptop-john-001 connected successfully</div>
          <div className="text-blue-400">2024-09-04 15:32:38 [DEBUG] Firewall rule evaluation for user john.smith@company.com</div>
          <div className="text-yellow-400">2024-09-04 15:32:35 [WARN] High memory usage detected on headend us-west-2</div>
          <div className="text-green-400">2024-09-04 15:32:30 [INFO] OSPF neighbor 10.0.1.15 state change: Full</div>
          <div className="text-red-400">2024-09-04 15:32:25 [ERROR] Certificate validation failed for client mobile-device-xyz</div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-100">
      <Head>
        <title>Management Portal - Tobogganing SASE</title>
        <meta name="description" content="Interactive mockup of the Tobogganing SASE management portal showcasing configuration and monitoring capabilities." />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <h1 className="text-xl font-bold text-gray-900">🛷 Tobogganing</h1>
              <span className="ml-2 text-sm text-gray-500">Management Portal</span>
            </div>
            <div className="flex items-center space-x-4">
              <span className="text-sm text-gray-600">Admin: John Smith</span>
              <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center">
                <span className="text-white text-sm font-bold">JS</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-8">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center px-3 py-4 text-sm font-medium border-b-2 ${
                    activeTab === tab.id
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  <Icon className="h-4 w-4 mr-2" />
                  {tab.name}
                </button>
              );
            })}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Portal Demo Notice */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
          <div className="flex">
            <div className="flex-shrink-0">
              <ChartBarIcon className="h-5 w-5 text-blue-400" />
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-blue-800">Interactive Portal Demo</h3>
              <div className="mt-2 text-sm text-blue-700">
                <p>This is an interactive mockup of the Tobogganing SASE Management Portal. Explore the different tabs to see user management, firewall configuration, network setup, client monitoring, and real-time analytics capabilities.</p>
              </div>
            </div>
          </div>
        </div>

        {/* Tab Content */}
        {activeTab === 'dashboard' && renderDashboard()}
        {activeTab === 'users' && renderUsers()}
        {activeTab === 'firewall' && renderFirewall()}
        {activeTab === 'networks' && renderNetworks()}
        {activeTab === 'clients' && renderClients()}
        {activeTab === 'monitoring' && renderMonitoring()}
      </main>
    </div>
  );
};

export default PortalPage;