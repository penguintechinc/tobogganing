import React from 'react';
import Image from 'next/image';

interface AppShowcaseProps {
  title?: string;
}

export const AppShowcase: React.FC<AppShowcaseProps> = ({ 
  title = "SASEWaddle in Action" 
}) => {
  const screenshots = [
    {
      name: 'Enterprise Dashboard',
      src: '/images/screenshots/enterprise-dashboard.svg',
      alt: 'SASEWaddle enterprise management dashboard with real-time monitoring',
      category: 'Web Portal'
    },
    {
      name: 'Mobile App Dashboard', 
      src: '/images/screenshots/mobile-app-dashboard.svg',
      alt: 'SASEWaddle mobile app with VPN connection status and statistics',
      category: 'Mobile App'
    },
    {
      name: 'Architecture Overview',
      src: '/images/screenshots/architecture-overview.svg',
      alt: 'Complete SASEWaddle system architecture with Zero Trust security layers',
      category: 'Documentation'
    },
    {
      name: 'Manager Portal',
      src: '/images/screenshots/manager-portal.svg',
      alt: 'SASEWaddle manager web portal interface',
      category: 'Web Portal'
    }
  ];

  return (
    <section id="showcase" className="py-20 bg-gradient-to-b from-gray-50 to-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
            📸 {title}
          </h2>
          <p className="text-xl text-gray-600 max-w-3xl mx-auto">
            Experience SASEWaddle's intuitive interfaces across all platforms - from enterprise dashboards 
            to mobile apps, all designed for seamless security management.
          </p>
        </div>
        
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-16">
          {screenshots.map((screenshot, index) => (
            <div key={index} className="group relative bg-white rounded-2xl shadow-lg overflow-hidden border border-gray-200 hover:shadow-2xl hover:border-primary-300 transition-all duration-300">
              {/* Category Badge */}
              <div className="absolute top-4 left-4 z-10">
                <span className="inline-flex items-center px-3 py-1 bg-primary-100 text-primary-800 text-xs font-medium rounded-full border border-primary-200">
                  {screenshot.category}
                </span>
              </div>
              
              {/* Screenshot */}
              <div className="aspect-w-16 aspect-h-10 bg-gray-100">
                <Image
                  src={screenshot.src}
                  alt={screenshot.alt}
                  width={800}
                  height={500}
                  className="object-contain w-full h-full group-hover:scale-105 transition-transform duration-300"
                  onError={(e) => {
                    // Handle missing images gracefully
                    e.currentTarget.style.display = 'none';
                  }}
                />
              </div>
              
              {/* Content */}
              <div className="p-6">
                <h3 className="text-xl font-bold text-gray-900 mb-2 group-hover:text-primary-600 transition-colors">
                  {screenshot.name}
                </h3>
                <p className="text-gray-600 leading-relaxed">
                  {screenshot.alt}
                </p>
              </div>
              
              {/* Hover Overlay */}
              <div className="absolute inset-0 bg-primary-600 bg-opacity-0 group-hover:bg-opacity-5 transition-all duration-300 pointer-events-none"></div>
            </div>
          ))}
        </div>

        {/* Features Grid */}
        <div className="bg-white rounded-2xl p-8 lg:p-12 border border-gray-200">
          <div className="text-center mb-12">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">Platform Features</h3>
            <p className="text-gray-600 max-w-2xl mx-auto">
              Comprehensive security management across all your devices and platforms
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
            <div className="text-center">
              <div className="w-16 h-16 bg-blue-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">🖥️</span>
              </div>
              <h4 className="text-lg font-semibold text-gray-900 mb-2">Web Portal</h4>
              <p className="text-gray-600 text-sm">
                Comprehensive management dashboard with real-time monitoring and analytics
              </p>
            </div>

            <div className="text-center">
              <div className="w-16 h-16 bg-green-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">📱</span>
              </div>
              <h4 className="text-lg font-semibold text-gray-900 mb-2">Mobile Apps</h4>
              <p className="text-gray-600 text-sm">
                Native mobile applications for Android and iOS with intuitive VPN controls
              </p>
            </div>

            <div className="text-center">
              <div className="w-16 h-16 bg-purple-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">💻</span>
              </div>
              <h4 className="text-lg font-semibold text-gray-900 mb-2">Desktop Clients</h4>
              <p className="text-gray-600 text-sm">
                Cross-platform desktop applications for Windows, macOS, and Linux
              </p>
            </div>

            <div className="text-center">
              <div className="w-16 h-16 bg-orange-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">🐳</span>
              </div>
              <h4 className="text-lg font-semibold text-gray-900 mb-2">Containers</h4>
              <p className="text-gray-600 text-sm">
                Docker containers for easy deployment and scaling in any environment
              </p>
            </div>
          </div>
        </div>

        {/* Technology Stack */}
        <div className="mt-20">
          <div className="text-center mb-12">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">Built with Modern Technologies</h3>
            <p className="text-gray-600 max-w-2xl mx-auto">
              SASEWaddle leverages cutting-edge technologies for maximum performance and security
            </p>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-8">
            <div className="text-center">
              <div className="w-12 h-12 bg-blue-50 rounded-lg flex items-center justify-center mx-auto mb-3">
                <span className="text-xl">⚛️</span>
              </div>
              <h5 className="text-sm font-medium text-gray-900">React Native</h5>
              <p className="text-xs text-gray-500 mt-1">Mobile Apps</p>
            </div>

            <div className="text-center">
              <div className="w-12 h-12 bg-green-50 rounded-lg flex items-center justify-center mx-auto mb-3">
                <span className="text-xl">🐹</span>
              </div>
              <h5 className="text-sm font-medium text-gray-900">Go</h5>
              <p className="text-xs text-gray-500 mt-1">Headend Server</p>
            </div>

            <div className="text-center">
              <div className="w-12 h-12 bg-yellow-50 rounded-lg flex items-center justify-center mx-auto mb-3">
                <span className="text-xl">🐍</span>
              </div>
              <h5 className="text-sm font-medium text-gray-900">Python</h5>
              <p className="text-xs text-gray-500 mt-1">Manager Service</p>
            </div>

            <div className="text-center">
              <div className="w-12 h-12 bg-purple-50 rounded-lg flex items-center justify-center mx-auto mb-3">
                <span className="text-xl">⚡</span>
              </div>
              <h5 className="text-sm font-medium text-gray-900">WireGuard</h5>
              <p className="text-xs text-gray-500 mt-1">VPN Protocol</p>
            </div>

            <div className="text-center">
              <div className="w-12 h-12 bg-indigo-50 rounded-lg flex items-center justify-center mx-auto mb-3">
                <span className="text-xl">☸️</span>
              </div>
              <h5 className="text-sm font-medium text-gray-900">Kubernetes</h5>
              <p className="text-xs text-gray-500 mt-1">Orchestration</p>
            </div>

            <div className="text-center">
              <div className="w-12 h-12 bg-red-50 rounded-lg flex items-center justify-center mx-auto mb-3">
                <span className="text-xl">📊</span>
              </div>
              <h5 className="text-sm font-medium text-gray-900">Prometheus</h5>
              <p className="text-xs text-gray-500 mt-1">Monitoring</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default AppShowcase;