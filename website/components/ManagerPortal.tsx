import React from 'react';
import { 
  ChartBarIcon,
  CogIcon,
  ShieldCheckIcon,
  UsersIcon,
  ServerIcon,
  ArrowRightIcon
} from '@heroicons/react/24/outline';

const ManagerPortal: React.FC = () => {
  return (
    <div id="manager-portal" className="bg-white py-20 sm:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
            Centralized Management Portal
          </h2>
          <p className="text-xl text-gray-600 max-w-3xl mx-auto">
            Comprehensive web-based management interface for configuring, monitoring, 
            and controlling your entire SASE infrastructure from a single dashboard.
          </p>
        </div>

        {/* Manager Portal Screenshot */}
        <div className="bg-gray-50 rounded-3xl shadow-xl p-8 lg:p-12 mb-16">
          <div className="flex justify-center">
            <img 
              src="/images/screenshots/manager-portal.svg" 
              alt="SASEWaddle Manager Portal Dashboard"
              className="max-w-full h-auto border border-gray-200 rounded-lg shadow-lg"
              style={{ maxHeight: '700px' }}
            />
          </div>
          <div className="mt-8 text-center">
            <p className="text-sm text-gray-600 max-w-4xl mx-auto">
              The Manager Portal provides real-time visibility into your SASE deployment with 
              comprehensive dashboards, user management, VRF configuration, and system monitoring.
            </p>
          </div>
        </div>

        {/* Key Features Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 mb-16">
          {/* User Management */}
          <div className="bg-white rounded-2xl p-6 shadow-lg border border-gray-200">
            <div className="flex items-center mb-4">
              <div className="bg-blue-100 rounded-lg p-3 mr-4">
                <UsersIcon className="h-6 w-6 text-blue-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900">User Management</h3>
            </div>
            <ul className="text-sm text-gray-600 space-y-2">
              <li>• Role-based access control (Admin/Reporter)</li>
              <li>• User registration and authentication</li>
              <li>• JWT token management</li>
              <li>• Activity logging and audit trails</li>
              <li>• External IdP integration</li>
            </ul>
          </div>

          {/* Network Configuration */}
          <div className="bg-white rounded-2xl p-6 shadow-lg border border-gray-200">
            <div className="flex items-center mb-4">
              <div className="bg-green-100 rounded-lg p-3 mr-4">
                <CogIcon className="h-6 w-6 text-green-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900">Network Configuration</h3>
            </div>
            <ul className="text-sm text-gray-600 space-y-2">
              <li>• VRF (Virtual Routing and Forwarding) setup</li>
              <li>• OSPF routing configuration</li>
              <li>• Multi-area OSPF design</li>
              <li>• Route Distinguisher management</li>
              <li>• Firewall rules configuration</li>
            </ul>
          </div>

          {/* Security Controls */}
          <div className="bg-white rounded-2xl p-6 shadow-lg border border-gray-200">
            <div className="flex items-center mb-4">
              <div className="bg-red-100 rounded-lg p-3 mr-4">
                <ShieldCheckIcon className="h-6 w-6 text-red-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900">Security Controls</h3>
            </div>
            <ul className="text-sm text-gray-600 space-y-2">
              <li>• Domain and IP filtering rules</li>
              <li>• Protocol-level access control</li>
              <li>• Port-based traffic management</li>
              <li>• Certificate lifecycle management</li>
              <li>• Traffic mirroring configuration</li>
            </ul>
          </div>

          {/* Monitoring & Analytics */}
          <div className="bg-white rounded-2xl p-6 shadow-lg border border-gray-200">
            <div className="flex items-center mb-4">
              <div className="bg-purple-100 rounded-lg p-3 mr-4">
                <ChartBarIcon className="h-6 w-6 text-purple-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900">Monitoring & Analytics</h3>
            </div>
            <ul className="text-sm text-gray-600 space-y-2">
              <li>• Real-time traffic analytics</li>
              <li>• Prometheus metrics integration</li>
              <li>• Health status monitoring</li>
              <li>• Performance dashboards</li>
              <li>• Syslog integration for compliance</li>
            </ul>
          </div>

          {/* Infrastructure Management */}
          <div className="bg-white rounded-2xl p-6 shadow-lg border border-gray-200">
            <div className="flex items-center mb-4">
              <div className="bg-yellow-100 rounded-lg p-3 mr-4">
                <ServerIcon className="h-6 w-6 text-yellow-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900">Infrastructure Management</h3>
            </div>
            <ul className="text-sm text-gray-600 space-y-2">
              <li>• Multi-datacenter orchestration</li>
              <li>• Headend server configuration</li>
              <li>• Client registration and deployment</li>
              <li>• Port configuration management</li>
              <li>• Redis caching for performance</li>
            </ul>
          </div>

          {/* API & Integration */}
          <div className="bg-white rounded-2xl p-6 shadow-lg border border-gray-200">
            <div className="flex items-center mb-4">
              <div className="bg-indigo-100 rounded-lg p-3 mr-4">
                <ArrowRightIcon className="h-6 w-6 text-indigo-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900">API & Integration</h3>
            </div>
            <ul className="text-sm text-gray-600 space-y-2">
              <li>• RESTful API for all operations</li>
              <li>• OpenAPI/Swagger documentation</li>
              <li>• Webhook support for events</li>
              <li>• Third-party integrations</li>
              <li>• Automation-friendly design</li>
            </ul>
          </div>
        </div>

        {/* Call to Action */}
        <div className="bg-gradient-to-r from-primary-600 to-primary-700 rounded-2xl p-8 lg:p-12 text-center">
          <h3 className="text-2xl font-bold text-white mb-4">
            Ready to Deploy SASEWaddle?
          </h3>
          <p className="text-primary-100 text-lg mb-8 max-w-2xl mx-auto">
            Get started with our comprehensive deployment guides and see the Manager Portal in action
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href="#download"
              className="bg-white text-primary-600 px-8 py-3 rounded-lg font-semibold hover:bg-primary-50 transition-colors"
            >
              Download Now
            </a>
            <a
              href="#documentation"
              className="border-2 border-white text-white px-8 py-3 rounded-lg font-semibold hover:bg-white hover:text-primary-600 transition-colors"
            >
              View Documentation
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ManagerPortal;