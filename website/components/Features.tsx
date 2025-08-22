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
    <div id="features" className="bg-gradient-to-br from-gray-50 via-white to-primary-50/30 py-20 sm:py-24 relative overflow-hidden">
      {/* Background decorations */}
      <div className="absolute inset-0">
        <div className="absolute top-0 right-0 w-96 h-96 bg-primary-200/20 rounded-full mix-blend-multiply filter blur-3xl opacity-40"></div>
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-secondary-200/20 rounded-full mix-blend-multiply filter blur-3xl opacity-40"></div>
      </div>
      
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-20">
          <div className="inline-flex items-center px-6 py-3 rounded-full bg-gradient-to-r from-primary-500/10 to-secondary-500/10 text-primary-700 text-sm font-semibold mb-6 border border-primary-200">
            <span className="animate-pulse mr-2">✨</span>
            Enterprise-Grade Features
          </div>
          <h2 className="text-4xl sm:text-5xl font-bold mb-6">
            <span className="text-gray-900">Everything You Need for</span>
            <span className="block bg-gradient-to-r from-primary-600 via-secondary-600 to-accent-600 bg-clip-text text-transparent">
              Zero Trust Security 🐧
            </span>
          </h2>
          <p className="text-xl text-gray-600 max-w-4xl mx-auto leading-relaxed">
            SASEWaddle provides all the features you need to secure your distributed workforce 
            with <strong>Zero Trust principles</strong> and modern cloud-native architecture that <em>just works</em>.
          </p>
        </div>

        {/* Features Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((feature, index) => (
            <div
              key={feature.name}
              className="group relative bg-white/80 backdrop-blur-sm rounded-2xl p-6 shadow-sm border border-gray-200/50 hover:shadow-2xl hover:border-primary-300 transition-all duration-500 transform hover:-translate-y-2 hover:scale-105"
            >
              {/* Icon */}
              <div className={`inline-flex items-center justify-center w-14 h-14 ${feature.color} rounded-2xl mb-6 group-hover:scale-110 group-hover:rotate-3 transition-all duration-300 shadow-lg`}>
                <feature.icon className="h-7 w-7 text-white" aria-hidden="true" />
              </div>

              {/* Content */}
              <h3 className="text-lg font-bold text-gray-900 mb-3 group-hover:text-primary-600 transition-colors">
                {feature.name}
              </h3>
              <p className="text-gray-600 text-sm leading-relaxed">
                {feature.description}
              </p>

              {/* Hover gradient overlay */}
              <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-primary-50 via-white to-secondary-50 opacity-0 group-hover:opacity-100 transition-opacity duration-300 -z-10"></div>
              
              {/* Subtle border glow on hover */}
              <div className="absolute inset-0 rounded-2xl bg-gradient-to-r from-primary-500 to-secondary-500 opacity-0 group-hover:opacity-20 transition-opacity duration-300 -z-20 blur-md"></div>
            </div>
          ))}
        </div>

        {/* Technical Specifications */}
        <div className="mt-24 bg-gradient-to-br from-white to-gray-50/80 rounded-3xl p-8 lg:p-12 shadow-xl border border-gray-200/50 backdrop-blur-sm">
          <div className="text-center mb-16">
            <div className="inline-flex items-center px-4 py-2 rounded-full bg-gradient-to-r from-accent-500/10 to-primary-500/10 text-accent-700 text-sm font-semibold mb-4 border border-accent-200">
              <span className="mr-2">🔧</span>
              Technical Stack
            </div>
            <h3 className="text-3xl font-bold text-gray-900 mb-4">Built with Modern Tech 🚀</h3>
            <p className="text-lg text-gray-600 max-w-3xl mx-auto leading-relaxed">
              Powered by cutting-edge technologies for <strong>maximum performance</strong>, 
              <strong>bulletproof security</strong>, and <strong>infinite scalability</strong>
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Manager Service */}
            <div className="group bg-white rounded-2xl p-8 border border-gray-200/50 shadow-lg hover:shadow-xl transition-all duration-300 transform hover:-translate-y-1">
              <div className="flex items-center mb-6">
                <div className="w-12 h-12 bg-gradient-to-br from-primary-500 to-primary-600 rounded-xl flex items-center justify-center mr-4">
                  <span className="text-white font-bold text-xl">🐍</span>
                </div>
                <h4 className="text-xl font-bold text-gray-900 group-hover:text-primary-600 transition-colors">Manager Service</h4>
              </div>
              <ul className="space-y-3 text-sm text-gray-600">
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-primary-400 to-primary-600 rounded-full mr-3 animate-pulse"></div>
                  <strong>Python 3.12</strong> with asyncio & threading
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-primary-400 to-primary-600 rounded-full mr-3"></div>
                  <strong>py4web</strong> REST API framework
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-primary-400 to-primary-600 rounded-full mr-3"></div>
                  <strong>MySQL/PostgreSQL</strong> with PyDAL ORM
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-primary-400 to-primary-600 rounded-full mr-3"></div>
                  <strong>Redis</strong> caching & sessions
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-primary-400 to-primary-600 rounded-full mr-3"></div>
                  <strong>X.509</strong> certificate management
                </li>
              </ul>
            </div>

            {/* Headend Server */}
            <div className="group bg-white rounded-2xl p-8 border border-gray-200/50 shadow-lg hover:shadow-xl transition-all duration-300 transform hover:-translate-y-1">
              <div className="flex items-center mb-6">
                <div className="w-12 h-12 bg-gradient-to-br from-secondary-500 to-secondary-600 rounded-xl flex items-center justify-center mr-4">
                  <span className="text-white font-bold text-xl">⚡</span>
                </div>
                <h4 className="text-xl font-bold text-gray-900 group-hover:text-secondary-600 transition-colors">Headend Server</h4>
              </div>
              <ul className="space-y-3 text-sm text-gray-600">
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-secondary-400 to-secondary-600 rounded-full mr-3 animate-pulse"></div>
                  <strong>Go 1.23</strong> with goroutines
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-secondary-400 to-secondary-600 rounded-full mr-3"></div>
                  <strong>WireGuard</strong> kernel module
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-secondary-400 to-secondary-600 rounded-full mr-3"></div>
                  <strong>Multi-protocol</strong> proxy (TCP/UDP/HTTPS)
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-secondary-400 to-secondary-600 rounded-full mr-3"></div>
                  <strong>Traffic mirroring</strong> (VXLAN/GRE/ERSPAN)
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-secondary-400 to-secondary-600 rounded-full mr-3"></div>
                  <strong>External IdP</strong> integration
                </li>
              </ul>
            </div>

            {/* Client Applications */}
            <div className="group bg-white rounded-2xl p-8 border border-gray-200/50 shadow-lg hover:shadow-xl transition-all duration-300 transform hover:-translate-y-1">
              <div className="flex items-center mb-6">
                <div className="w-12 h-12 bg-gradient-to-br from-accent-500 to-accent-600 rounded-xl flex items-center justify-center mr-4">
                  <span className="text-white font-bold text-xl">📱</span>
                </div>
                <h4 className="text-xl font-bold text-gray-900 group-hover:text-accent-600 transition-colors">Client Applications</h4>
              </div>
              <ul className="space-y-3 text-sm text-gray-600">
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-accent-400 to-accent-600 rounded-full mr-3 animate-pulse"></div>
                  <strong>Go native</strong> binaries (GUI + Headless)
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-accent-400 to-accent-600 rounded-full mr-3"></div>
                  <strong>React Native</strong> mobile apps
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-accent-400 to-accent-600 rounded-full mr-3"></div>
                  <strong>Docker</strong> containers (ARM64/AMD64)
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-accent-400 to-accent-600 rounded-full mr-3"></div>
                  <strong>Cross-platform</strong> support
                </li>
                <li className="flex items-center">
                  <div className="w-2 h-2 bg-gradient-to-r from-accent-400 to-accent-600 rounded-full mr-3"></div>
                  <strong>Auto-configuration</strong> & updates
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