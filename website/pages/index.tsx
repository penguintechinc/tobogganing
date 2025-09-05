import React from 'react';
import Head from 'next/head';

const HomePage: React.FC = () => {
  return (
    <div className="min-h-screen bg-white">
      <Head>
        <title>Tobogganing - Open Source SASE Solution</title>
        <meta name="description" content="Tobogganing is an Open Source Secure Access Service Edge (SASE) solution implementing Zero Trust Network Architecture." />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      {/* Header */}
      <header className="bg-blue-600 text-white py-4">
        <div className="max-w-6xl mx-auto px-4">
          <h1 className="text-2xl font-bold">🛷 Tobogganing</h1>
          <p className="text-blue-100">Open Source SASE Solution</p>
        </div>
      </header>

      {/* Hero Section */}
      <section className="py-16 bg-gray-50">
        <div className="max-w-6xl mx-auto px-4 text-center">
          <h2 className="text-4xl font-bold text-gray-900 mb-6">
            Enterprise SASE with Zero Trust Architecture
          </h2>
          <p className="text-xl text-gray-600 mb-8 max-w-3xl mx-auto">
            Complete SASE solution with WireGuard VPN, multi-platform clients, 
            and enterprise-grade security. Built with Go, Python, and React Native.
          </p>
          <div className="space-x-4">
            <a 
              href="/portal" 
              className="bg-blue-600 text-white px-6 py-3 rounded-lg font-semibold hover:bg-blue-700"
            >
              View Portal Demo
            </a>
            <a 
              href="https://github.com/penguintechinc/Tobogganing" 
              className="bg-gray-200 text-gray-800 px-6 py-3 rounded-lg font-semibold hover:bg-gray-300"
            >
              View on GitHub
            </a>
            <a 
              href="#features" 
              className="bg-gray-600 text-white px-6 py-3 rounded-lg font-semibold hover:bg-gray-700"
            >
              Learn More
            </a>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-16">
        <div className="max-w-6xl mx-auto px-4">
          <h3 className="text-3xl font-bold text-center mb-12">Key Features</h3>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            
            <div className="bg-white p-6 rounded-lg border border-gray-200">
              <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mb-4">
                <span className="text-blue-600 text-xl">🛡️</span>
              </div>
              <h4 className="text-xl font-semibold mb-2">Zero Trust Security</h4>
              <p className="text-gray-600">Dual authentication with X.509 certificates and JWT/SSO integration.</p>
            </div>

            <div className="bg-white p-6 rounded-lg border border-gray-200">
              <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mb-4">
                <span className="text-green-600 text-xl">📱</span>
              </div>
              <h4 className="text-xl font-semibold mb-2">Multi-Platform</h4>
              <p className="text-gray-600">Native clients for macOS, Windows, Linux, and mobile apps.</p>
            </div>

            <div className="bg-white p-6 rounded-lg border border-gray-200">
              <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mb-4">
                <span className="text-purple-600 text-xl">⚡</span>
              </div>
              <h4 className="text-xl font-semibold mb-2">High Performance</h4>
              <p className="text-gray-600">Built with Go and WireGuard for maximum throughput.</p>
            </div>

            <div className="bg-white p-6 rounded-lg border border-gray-200">
              <div className="w-12 h-12 bg-indigo-100 rounded-lg flex items-center justify-center mb-4">
                <span className="text-indigo-600 text-xl">☁️</span>
              </div>
              <h4 className="text-xl font-semibold mb-2">Cloud Native</h4>
              <p className="text-gray-600">Kubernetes-ready with Docker containers and auto-scaling.</p>
            </div>

            <div className="bg-white p-6 rounded-lg border border-gray-200">
              <div className="w-12 h-12 bg-red-100 rounded-lg flex items-center justify-center mb-4">
                <span className="text-red-600 text-xl">🔒</span>
              </div>
              <h4 className="text-xl font-semibold mb-2">Enterprise Security</h4>
              <p className="text-gray-600">Certificate management, audit logging, and IDS/IPS integration.</p>
            </div>

            <div className="bg-white p-6 rounded-lg border border-gray-200">
              <div className="w-12 h-12 bg-yellow-100 rounded-lg flex items-center justify-center mb-4">
                <span className="text-yellow-600 text-xl">🌍</span>
              </div>
              <h4 className="text-xl font-semibold mb-2">Global Scale</h4>
              <p className="text-gray-600">Multi-datacenter orchestration with automatic failover.</p>
            </div>

          </div>
        </div>
      </section>

      {/* Architecture */}
      <section className="py-16 bg-gray-50">
        <div className="max-w-6xl mx-auto px-4">
          <h3 className="text-3xl font-bold text-center mb-12">Architecture</h3>
          <div className="grid md:grid-cols-3 gap-8">
            
            <div className="text-center">
              <div className="w-16 h-16 bg-blue-600 rounded-lg flex items-center justify-center mx-auto mb-4">
                <span className="text-white text-2xl">📊</span>
              </div>
              <h4 className="text-xl font-semibold mb-2">Manager Service</h4>
              <p className="text-gray-600">Python-based orchestration with web portal and API</p>
            </div>

            <div className="text-center">
              <div className="w-16 h-16 bg-green-600 rounded-lg flex items-center justify-center mx-auto mb-4">
                <span className="text-white text-2xl">🌐</span>
              </div>
              <h4 className="text-xl font-semibold mb-2">Headend Server</h4>
              <p className="text-gray-600">Go-based proxy with WireGuard termination</p>
            </div>

            <div className="text-center">
              <div className="w-16 h-16 bg-purple-600 rounded-lg flex items-center justify-center mx-auto mb-4">
                <span className="text-white text-2xl">💻</span>
              </div>
              <h4 className="text-xl font-semibold mb-2">Client Apps</h4>
              <p className="text-gray-600">Native and Docker clients for all platforms</p>
            </div>

          </div>
        </div>
      </section>

      {/* Management Portal Section */}
      <section className="py-16">
        <div className="max-w-6xl mx-auto px-4">
          <h3 className="text-3xl font-bold text-center mb-12">Enterprise Management Portal</h3>
          
          <div className="bg-white rounded-2xl shadow-xl p-8 lg:p-12 mb-12">
            <div className="grid lg:grid-cols-2 gap-8 items-center">
              <div>
                <h4 className="text-2xl font-bold text-gray-900 mb-4">
                  Comprehensive Web-Based Management
                </h4>
                <p className="text-gray-600 mb-6">
                  Control your entire SASE infrastructure from a single, intuitive web interface. 
                  Manage users, configure firewall rules, monitor network health, and analyze 
                  real-time metrics with our powerful management portal.
                </p>
                <div className="space-y-3">
                  <div className="flex items-center">
                    <div className="w-2 h-2 bg-blue-500 rounded-full mr-3"></div>
                    <span className="text-gray-700">Role-based access control (Admin/Reporter)</span>
                  </div>
                  <div className="flex items-center">
                    <div className="w-2 h-2 bg-green-500 rounded-full mr-3"></div>
                    <span className="text-gray-700">Advanced firewall and network configuration</span>
                  </div>
                  <div className="flex items-center">
                    <div className="w-2 h-2 bg-purple-500 rounded-full mr-3"></div>
                    <span className="text-gray-700">Real-time monitoring and analytics</span>
                  </div>
                  <div className="flex items-center">
                    <div className="w-2 h-2 bg-orange-500 rounded-full mr-3"></div>
                    <span className="text-gray-700">VRF and OSPF routing management</span>
                  </div>
                </div>
                <div className="mt-6">
                  <a 
                    href="/portal" 
                    className="bg-blue-600 text-white px-6 py-3 rounded-lg font-semibold hover:bg-blue-700 inline-flex items-center"
                  >
                    <span>Explore Interactive Demo</span>
                    <svg className="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
                    </svg>
                  </a>
                </div>
              </div>
              
              <div className="bg-gray-50 rounded-xl p-6">
                <div className="bg-white rounded-lg shadow-lg p-4 mb-4">
                  <div className="flex items-center justify-between mb-3">
                    <h5 className="font-semibold text-gray-900">🛷 Tobogganing Dashboard</h5>
                    <div className="flex space-x-1">
                      <div className="w-3 h-3 bg-red-400 rounded-full"></div>
                      <div className="w-3 h-3 bg-yellow-400 rounded-full"></div>
                      <div className="w-3 h-3 bg-green-400 rounded-full"></div>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-3 mb-3">
                    <div className="bg-blue-50 p-2 rounded text-center">
                      <div className="text-lg font-bold text-blue-600">847</div>
                      <div className="text-xs text-gray-600">Clients</div>
                    </div>
                    <div className="bg-green-50 p-2 rounded text-center">
                      <div className="text-lg font-bold text-green-600">731</div>
                      <div className="text-xs text-gray-600">Active</div>
                    </div>
                    <div className="bg-purple-50 p-2 rounded text-center">
                      <div className="text-lg font-bold text-purple-600">12</div>
                      <div className="text-xs text-gray-600">Headends</div>
                    </div>
                  </div>
                  <div className="bg-gray-100 h-12 rounded mb-3 flex items-center justify-center">
                    <svg viewBox="0 0 100 30" className="w-full h-6">
                      <path d="M 5 25 Q 20 15, 35 18 T 65 12 T 95 16" stroke="#3b82f6" strokeWidth="2" fill="none"/>
                      <circle cx="95" cy="16" r="2" fill="#3b82f6"/>
                    </svg>
                  </div>
                  <div className="flex justify-between text-xs text-gray-500">
                    <span>• User Management</span>
                    <span>• Firewall Rules</span>
                    <span>• Real-time Metrics</span>
                  </div>
                </div>
                <div className="text-center text-sm text-gray-600">
                  Live portal interface with interactive controls
                </div>
              </div>
            </div>
          </div>

          {/* Key Portal Features */}
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="text-center p-6 bg-white rounded-lg shadow-sm">
              <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mx-auto mb-4">
                <span className="text-blue-600 text-2xl">👥</span>
              </div>
              <h5 className="text-lg font-semibold mb-2">User Management</h5>
              <p className="text-gray-600 text-sm">Role-based access, JWT authentication, and audit logging</p>
            </div>

            <div className="text-center p-6 bg-white rounded-lg shadow-sm">
              <div className="w-12 h-12 bg-red-100 rounded-lg flex items-center justify-center mx-auto mb-4">
                <span className="text-red-600 text-2xl">🛡️</span>
              </div>
              <h5 className="text-lg font-semibold mb-2">Firewall Control</h5>
              <p className="text-gray-600 text-sm">Domain, IP, and protocol-level traffic filtering</p>
            </div>

            <div className="text-center p-6 bg-white rounded-lg shadow-sm">
              <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mx-auto mb-4">
                <span className="text-green-600 text-2xl">🌐</span>
              </div>
              <h5 className="text-lg font-semibold mb-2">Network Config</h5>
              <p className="text-gray-600 text-sm">VRF setup, OSPF routing, and multi-area design</p>
            </div>

            <div className="text-center p-6 bg-white rounded-lg shadow-sm">
              <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mx-auto mb-4">
                <span className="text-purple-600 text-2xl">📊</span>
              </div>
              <h5 className="text-lg font-semibold mb-2">Real-time Analytics</h5>
              <p className="text-gray-600 text-sm">Traffic monitoring, system health, and performance metrics</p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-800 text-white py-8">
        <div className="max-w-6xl mx-auto px-4 text-center">
          <p className="text-gray-400">
            © 2024 Tobogganing. Open Source MIT License.
          </p>
          <div className="mt-4 space-x-6">
            <a href="https://github.com/penguintechinc/Tobogganing" className="text-gray-400 hover:text-white">
              GitHub
            </a>
            <a href={process.env.NEXT_PUBLIC_DOCS_URL || 'https://docs.tobogganing.io'} target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-white">
              Documentation
            </a>
          </div>
        </div>
      </footer>

    </div>
  );
};

export default HomePage;