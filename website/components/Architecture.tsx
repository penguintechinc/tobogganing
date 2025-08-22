import React from 'react';
import { 
  ArrowRightIcon, 
  ShieldCheckIcon, 
  ServerIcon,
  DevicePhoneMobileIcon,
  CloudIcon,
  LockClosedIcon
} from '@heroicons/react/24/outline';

const Architecture: React.FC = () => {
  return (
    <div id="architecture" className="bg-gray-50 py-20 sm:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
            SASE Architecture Overview
          </h2>
          <p className="text-xl text-gray-600 max-w-3xl mx-auto">
            SASEWaddle implements a three-tier architecture with centralized management, 
            distributed headend servers, and multi-platform clients for comprehensive SASE coverage.
          </p>
        </div>

        {/* Architecture Diagram */}
        <div className="bg-white rounded-3xl shadow-xl p-8 lg:p-12 mb-16">
          <div className="flex justify-center">
            <img 
              src="/images/diagrams/connectivity-flow.svg" 
              alt="SASEWaddle Connectivity Flow Diagram"
              className="w-full max-w-4xl h-auto object-contain"
              style={{ maxHeight: '600px' }}
            />
          </div>
          <div className="mt-8 text-center">
            <p className="text-sm text-gray-600 max-w-4xl mx-auto">
              Complete connectivity flow showing how users and services connect through SASEWaddle's 
              Zero Trust architecture with WireGuard VPN tunnels, headend proxy servers, 
              centralized management, and comprehensive security monitoring.
            </p>
          </div>
        </div>

        {/* Security Flow */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 mb-16">
          {/* Authentication Flow */}
          <div className="bg-white rounded-2xl p-8 shadow-lg border border-gray-200">
            <div className="flex items-center mb-6">
              <div className="bg-primary-100 rounded-lg p-3 mr-4">
                <LockClosedIcon className="h-6 w-6 text-primary-600" />
              </div>
              <h3 className="text-xl font-semibold text-gray-900">Dual Authentication</h3>
            </div>
            
            <div className="space-y-4">
              <div className="flex items-start">
                <div className="bg-primary-600 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-semibold mr-3 mt-1">1</div>
                <div>
                  <h4 className="font-semibold text-gray-900">Certificate Authentication</h4>
                  <p className="text-sm text-gray-600">X.509 certificates for WireGuard tunnel establishment</p>
                </div>
              </div>
              
              <div className="flex items-start">
                <div className="bg-primary-600 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-semibold mr-3 mt-1">2</div>
                <div>
                  <h4 className="font-semibold text-gray-900">Application Authentication</h4>
                  <p className="text-sm text-gray-600">JWT tokens or SSO for application-level access</p>
                </div>
              </div>
              
              <div className="flex items-start">
                <div className="bg-primary-600 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-semibold mr-3 mt-1">3</div>
                <div>
                  <h4 className="font-semibold text-gray-900">Continuous Verification</h4>
                  <p className="text-sm text-gray-600">Token refresh and certificate rotation</p>
                </div>
              </div>
            </div>
          </div>

          {/* Traffic Flow */}
          <div className="bg-white rounded-2xl p-8 shadow-lg border border-gray-200">
            <div className="flex items-center mb-6">
              <div className="bg-green-100 rounded-lg p-3 mr-4">
                <ShieldCheckIcon className="h-6 w-6 text-green-600" />
              </div>
              <h3 className="text-xl font-semibold text-gray-900">Traffic Processing</h3>
            </div>
            
            <div className="space-y-4">
              <div className="flex items-start">
                <div className="bg-green-600 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-semibold mr-3 mt-1">1</div>
                <div>
                  <h4 className="font-semibold text-gray-900">WireGuard Termination</h4>
                  <p className="text-sm text-gray-600">High-performance VPN tunnel termination</p>
                </div>
              </div>
              
              <div className="flex items-start">
                <div className="bg-green-600 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-semibold mr-3 mt-1">2</div>
                <div>
                  <h4 className="font-semibold text-gray-900">Protocol Proxying</h4>
                  <p className="text-sm text-gray-600">HTTP/HTTPS, TCP, UDP proxy with authentication</p>
                </div>
              </div>
              
              <div className="flex items-start">
                <div className="bg-green-600 text-white rounded-full w-6 h-6 flex items-center justify-center text-xs font-semibold mr-3 mt-1">3</div>
                <div>
                  <h4 className="font-semibold text-gray-900">Security Monitoring</h4>
                  <p className="text-sm text-gray-600">Traffic mirroring to IDS/IPS systems</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Deployment Options */}
        <div className="bg-white rounded-2xl p-8 lg:p-12 shadow-lg">
          <div className="text-center mb-8">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">Flexible Deployment Options</h3>
            <p className="text-gray-600 max-w-2xl mx-auto">
              Deploy SASEWaddle in any environment with our comprehensive deployment configurations
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="bg-blue-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
                <CloudIcon className="h-8 w-8 text-blue-600" />
              </div>
              <h4 className="text-lg font-semibold text-gray-900 mb-2">Kubernetes</h4>
              <p className="text-sm text-gray-600 mb-4">
                Production-ready with auto-scaling, health checks, and monitoring
              </p>
              <ul className="text-xs text-gray-500 space-y-1">
                <li>• Horizontal Pod Autoscaling</li>
                <li>• Persistent Volumes</li>
                <li>• Service Mesh Ready</li>
                <li>• Multi-cluster Support</li>
              </ul>
            </div>

            <div className="text-center">
              <div className="bg-green-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
                <ServerIcon className="h-8 w-8 text-green-600" />
              </div>
              <h4 className="text-lg font-semibold text-gray-900 mb-2">Docker Compose</h4>
              <p className="text-sm text-gray-600 mb-4">
                Quick deployment for development and small production environments
              </p>
              <ul className="text-xs text-gray-500 space-y-1">
                <li>• Single-node Deployment</li>
                <li>• Built-in Networking</li>
                <li>• Volume Management</li>
                <li>• Development Tools</li>
              </ul>
            </div>

            <div className="text-center">
              <div className="bg-purple-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
                <CloudIcon className="h-8 w-8 text-purple-600" />
              </div>
              <h4 className="text-lg font-semibold text-gray-900 mb-2">Cloud Native</h4>
              <p className="text-sm text-gray-600 mb-4">
                Terraform configurations for AWS, Azure, and Google Cloud
              </p>
              <ul className="text-xs text-gray-500 space-y-1">
                <li>• Infrastructure as Code</li>
                <li>• Load Balancers</li>
                <li>• Managed Databases</li>
                <li>• Auto Scaling Groups</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Architecture;