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
              href="https://github.com/penguintechinc/Tobogganing" 
              className="bg-blue-600 text-white px-6 py-3 rounded-lg font-semibold hover:bg-blue-700"
            >
              View on GitHub
            </a>
            <a 
              href="#features" 
              className="bg-gray-200 text-gray-800 px-6 py-3 rounded-lg font-semibold hover:bg-gray-300"
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
            <a href="https://github.com/penguintechinc/Tobogganing/blob/main/README.md" className="text-gray-400 hover:text-white">
              Documentation
            </a>
          </div>
        </div>
      </footer>

    </div>
  );
};

export default HomePage;