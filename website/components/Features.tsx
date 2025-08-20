import React from 'react';
import {
  ShieldCheckIcon,
  CloudIcon,
  CpuChipIcon,
  GlobeAltIcon,
  LockClosedIcon,
  ChartBarIcon,
  DevicePhoneMobileIcon,
  ServerIcon,
} from '@heroicons/react/24/outline';

const features = [
  {
    name: 'Zero Trust Architecture',
    description: 'Dual authentication with X.509 certificates and JWT/SSO integration. Every connection is verified and encrypted.',
    icon: ShieldCheckIcon,
    color: 'bg-blue-500',
  },
  {
    name: 'Multi-Platform Clients',
    description: 'Native applications for macOS, Windows, and Linux, plus Docker containers for easy deployment.',
    icon: DevicePhoneMobileIcon,
    color: 'bg-green-500',
  },
  {
    name: 'High Performance',
    description: 'Built with Go and Python asyncio for concurrent connections. WireGuard provides maximum throughput.',
    icon: CpuChipIcon,
    color: 'bg-purple-500',
  },
  {
    name: 'Cloud Native',
    description: 'Kubernetes-ready with auto-scaling, health checks, and monitoring. Deploy on any cloud provider.',
    icon: CloudIcon,
    color: 'bg-indigo-500',
  },
  {
    name: 'Enterprise Security',
    description: 'Certificate management, audit logging, traffic mirroring for IDS/IPS, and compliance-ready features.',
    icon: LockClosedIcon,
    color: 'bg-red-500',
  },
  {
    name: 'Global Scale',
    description: 'Multi-datacenter orchestration with automatic failover and geographic load balancing.',
    icon: GlobeAltIcon,
    color: 'bg-yellow-500',
  },
  {
    name: 'Real-time Monitoring',
    description: 'Prometheus metrics, Grafana dashboards, and comprehensive health monitoring built-in.',
    icon: ChartBarIcon,
    color: 'bg-pink-500',
  },
  {
    name: 'Infrastructure as Code',
    description: 'Complete Terraform, Kubernetes manifests, and Docker Compose configurations included.',
    icon: ServerIcon,
    color: 'bg-cyan-500',
  },
];

const Features: React.FC = () => {
  return (
    <div id="features" className="bg-white py-20 sm:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
            Enterprise-Grade Features
          </h2>
          <p className="text-xl text-gray-600 max-w-3xl mx-auto">
            SASEWaddle provides all the features you need to secure your distributed workforce 
            with Zero Trust principles and modern cloud-native architecture.
          </p>
        </div>

        {/* Features Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
          {features.map((feature, index) => (
            <div
              key={feature.name}
              className="group relative bg-white rounded-2xl p-6 shadow-sm border border-gray-200 hover:shadow-lg hover:border-primary-300 transition-all duration-300"
            >
              {/* Icon */}
              <div className={`inline-flex items-center justify-center w-12 h-12 ${feature.color} rounded-xl mb-4 group-hover:scale-110 transition-transform duration-300`}>
                <feature.icon className="h-6 w-6 text-white" aria-hidden="true" />
              </div>

              {/* Content */}
              <h3 className="text-lg font-semibold text-gray-900 mb-2 group-hover:text-primary-600 transition-colors">
                {feature.name}
              </h3>
              <p className="text-gray-600 text-sm leading-relaxed">
                {feature.description}
              </p>

              {/* Hover effect */}
              <div className="absolute inset-0 rounded-2xl bg-primary-50 opacity-0 group-hover:opacity-100 transition-opacity duration-300 -z-10"></div>
            </div>
          ))}
        </div>

        {/* Technical Specifications */}
        <div className="mt-20 bg-gray-50 rounded-2xl p-8 lg:p-12">
          <div className="text-center mb-12">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">Technical Specifications</h3>
            <p className="text-gray-600 max-w-2xl mx-auto">
              Built with modern technologies for maximum performance, security, and scalability
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Manager Service */}
            <div className="bg-white rounded-xl p-6 border border-gray-200">
              <h4 className="text-lg font-semibold text-gray-900 mb-4">Manager Service</h4>
              <ul className="space-y-2 text-sm text-gray-600">
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-primary-500 rounded-full mr-3"></span>
                  Python 3.12 with asyncio
                </li>
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-primary-500 rounded-full mr-3"></span>
                  py4web REST API framework
                </li>
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-primary-500 rounded-full mr-3"></span>
                  SQLite/PostgreSQL database
                </li>
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-primary-500 rounded-full mr-3"></span>
                  Redis caching & sessions
                </li>
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-primary-500 rounded-full mr-3"></span>
                  X.509 certificate management
                </li>
              </ul>
            </div>

            {/* Headend Server */}
            <div className="bg-white rounded-xl p-6 border border-gray-200">
              <h4 className="text-lg font-semibold text-gray-900 mb-4">Headend Server</h4>
              <ul className="space-y-2 text-sm text-gray-600">
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-green-500 rounded-full mr-3"></span>
                  Go 1.21 with goroutines
                </li>
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-green-500 rounded-full mr-3"></span>
                  WireGuard kernel module
                </li>
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-green-500 rounded-full mr-3"></span>
                  Multi-protocol proxy
                </li>
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-green-500 rounded-full mr-3"></span>
                  Traffic mirroring (VXLAN/GRE)
                </li>
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-green-500 rounded-full mr-3"></span>
                  External IdP integration
                </li>
              </ul>
            </div>

            {/* Client Applications */}
            <div className="bg-white rounded-xl p-6 border border-gray-200">
              <h4 className="text-lg font-semibold text-gray-900 mb-4">Client Applications</h4>
              <ul className="space-y-2 text-sm text-gray-600">
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-purple-500 rounded-full mr-3"></span>
                  Go native binaries
                </li>
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-purple-500 rounded-full mr-3"></span>
                  Docker containers
                </li>
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-purple-500 rounded-full mr-3"></span>
                  Cross-platform support
                </li>
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-purple-500 rounded-full mr-3"></span>
                  Auto-configuration
                </li>
                <li className="flex items-center">
                  <span className="w-2 h-2 bg-purple-500 rounded-full mr-3"></span>
                  GUI & CLI interfaces
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Features;