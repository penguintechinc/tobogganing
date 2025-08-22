import React from 'react';
import Link from 'next/link';
import { ArrowRightIcon, ShieldCheckIcon, CloudIcon, LockClosedIcon } from '@heroicons/react/24/outline';

const Hero: React.FC = () => {
  return (
    <div className="relative bg-gradient-to-br from-primary-50 via-white to-secondary-50 overflow-hidden">
      {/* Background decorations */}
      <div className="absolute inset-0">
        <div className="absolute top-10 left-10 w-72 h-72 bg-primary-200 rounded-full mix-blend-multiply filter blur-xl opacity-30 animate-bounce-slow"></div>
        <div className="absolute top-10 right-10 w-72 h-72 bg-secondary-200 rounded-full mix-blend-multiply filter blur-xl opacity-30 animate-bounce-slow animation-delay-2000"></div>
        <div className="absolute bottom-10 left-1/2 w-72 h-72 bg-accent-200 rounded-full mix-blend-multiply filter blur-xl opacity-30 animate-bounce-slow animation-delay-4000"></div>
      </div>

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 sm:py-24 lg:py-32">
        <div className="text-center">
          {/* Animated Badge */}
          <div className="inline-flex items-center px-6 py-3 rounded-full bg-gradient-to-r from-primary-500 to-secondary-500 text-white text-sm font-semibold mb-8 shadow-lg hover:shadow-xl transition-all duration-300 transform hover:scale-105">
            <ShieldCheckIcon className="h-5 w-5 mr-2 animate-pulse" />
            🐧 Open Source SASE Solution
          </div>

          {/* Main heading with gradient text */}
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-6 leading-tight animate-fade-in">
            Secure Access Service Edge
            <span className="block bg-gradient-to-r from-primary-600 via-secondary-600 to-accent-600 bg-clip-text text-transparent">
              Built for the Modern Enterprise
            </span>
          </h1>

          {/* Enhanced Description */}
          <p className="text-xl text-gray-700 mb-10 max-w-4xl mx-auto leading-relaxed animate-slide-up">
            🚀 SASEWaddle implements <strong>Zero Trust Network Architecture (ZTNA)</strong> with enterprise-grade security, 
            lightning-fast <strong>WireGuard VPN</strong>, beautiful React Native mobile apps, and seamless multi-platform client support. 
            <br />
            <span className="text-primary-600 font-semibold">Deploy anywhere, scale everywhere, secure everything.</span>
          </p>

          {/* Enhanced CTA Buttons */}
          <div className="flex flex-col sm:flex-row gap-6 justify-center items-center mb-16 animate-slide-up">
            <Link
              href="/downloads"
              className="group relative bg-gradient-to-r from-primary-600 to-secondary-600 text-white px-10 py-5 rounded-xl text-lg font-bold hover:from-primary-700 hover:to-secondary-700 transition-all duration-300 flex items-center shadow-xl hover:shadow-2xl transform hover:scale-105 hover:-translate-y-1"
            >
              <span className="relative z-10 flex items-center">
                🚀 Get Started Free
                <ArrowRightIcon className="h-6 w-6 ml-3 group-hover:translate-x-2 transition-transform duration-300" />
              </span>
              <div className="absolute inset-0 bg-gradient-to-r from-accent-600 to-primary-700 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
            </Link>
            <Link
              href="/docs"
              className="group bg-white/80 backdrop-blur-sm text-primary-700 border-3 border-primary-600 px-10 py-5 rounded-xl text-lg font-bold hover:bg-primary-50 hover:border-primary-700 transition-all duration-300 shadow-lg hover:shadow-xl transform hover:scale-105"
            >
              📚 View Documentation
            </Link>
          </div>

          {/* Stats Section */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-8 max-w-2xl mx-auto mb-16">
            <div className="text-center">
              <div className="text-3xl font-bold text-primary-600 mb-1">100%</div>
              <div className="text-sm text-gray-600 font-medium">Open Source</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-secondary-600 mb-1">∞</div>
              <div className="text-sm text-gray-600 font-medium">Unlimited Scale</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-accent-600 mb-1">0ms</div>
              <div className="text-sm text-gray-600 font-medium">Zero Trust</div>
            </div>
          </div>

          {/* Key Features */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-4xl mx-auto">
            <div className="group text-center bg-white/50 backdrop-blur-sm rounded-2xl p-8 border border-primary-200/50 hover:bg-white/80 hover:border-primary-300 hover:shadow-xl transition-all duration-300 transform hover:-translate-y-2">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-primary-500 to-primary-600 rounded-2xl mb-6 group-hover:scale-110 transition-transform duration-300 shadow-lg">
                <LockClosedIcon className="h-8 w-8 text-white" />
              </div>
              <h3 className="text-xl font-bold text-gray-900 mb-3 group-hover:text-primary-600 transition-colors">🔐 Zero Trust Security</h3>
              <p className="text-gray-600 leading-relaxed">
                Dual authentication with X.509 certificates and JWT/SSO integration for bulletproof security
              </p>
            </div>
            <div className="group text-center bg-white/50 backdrop-blur-sm rounded-2xl p-8 border border-secondary-200/50 hover:bg-white/80 hover:border-secondary-300 hover:shadow-xl transition-all duration-300 transform hover:-translate-y-2">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-secondary-500 to-secondary-600 rounded-2xl mb-6 group-hover:scale-110 transition-transform duration-300 shadow-lg">
                <CloudIcon className="h-8 w-8 text-white" />
              </div>
              <h3 className="text-xl font-bold text-gray-900 mb-3 group-hover:text-secondary-600 transition-colors">☁️ Cloud Native</h3>
              <p className="text-gray-600 leading-relaxed">
                Deploy on Kubernetes, Docker, or any cloud provider with auto-scaling magic
              </p>
            </div>
            <div className="group text-center bg-white/50 backdrop-blur-sm rounded-2xl p-8 border border-accent-200/50 hover:bg-white/80 hover:border-accent-300 hover:shadow-xl transition-all duration-300 transform hover:-translate-y-2">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-accent-500 to-accent-600 rounded-2xl mb-6 group-hover:scale-110 transition-transform duration-300 shadow-lg">
                <ShieldCheckIcon className="h-8 w-8 text-white" />
              </div>
              <h3 className="text-xl font-bold text-gray-900 mb-3 group-hover:text-accent-600 transition-colors">🚀 Enterprise Ready</h3>
              <p className="text-gray-600 leading-relaxed">
                Traffic mirroring, audit logging, and compliance features built for scale
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Architecture Preview */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pb-20">
        <div className="bg-gradient-to-br from-white to-gray-50/50 rounded-3xl shadow-2xl border border-gray-200/50 p-8 lg:p-12 backdrop-blur-sm">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold bg-gradient-to-r from-primary-600 via-secondary-600 to-accent-600 bg-clip-text text-transparent mb-6">🏗️ Enterprise Architecture</h2>
            <p className="text-xl text-gray-600 max-w-3xl mx-auto leading-relaxed">
              Three-tier architecture with Manager Service, Headend Server, and Client Applications - 
              <span className="text-primary-600 font-semibold"> designed for scale, security, and simplicity</span>
            </p>
          </div>
          
          {/* Architecture Diagram */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-center">
            <div className="group text-center">
              <div className="relative bg-gradient-to-br from-primary-500 to-primary-600 rounded-2xl p-8 mb-6 shadow-lg group-hover:shadow-xl transition-all duration-300 transform group-hover:-translate-y-1">
                <div className="absolute -top-2 -right-2 w-6 h-6 bg-accent-500 rounded-full animate-ping"></div>
                <div className="w-16 h-16 bg-white rounded-xl flex items-center justify-center mx-auto shadow-lg">
                  <span className="text-primary-600 font-bold text-2xl">🐧</span>
                </div>
              </div>
              <h3 className="text-xl font-bold text-gray-900 mb-2">Manager Service</h3>
              <p className="text-gray-600 leading-relaxed">Central orchestration, certificates & py4web dashboard</p>
            </div>
            
            <div className="group text-center">
              <div className="relative bg-gradient-to-br from-secondary-500 to-secondary-600 rounded-2xl p-8 mb-6 shadow-lg group-hover:shadow-xl transition-all duration-300 transform group-hover:-translate-y-1">
                <div className="absolute -top-2 -right-2 w-6 h-6 bg-accent-500 rounded-full animate-ping animation-delay-1000"></div>
                <div className="w-16 h-16 bg-white rounded-xl flex items-center justify-center mx-auto shadow-lg">
                  <span className="text-secondary-600 font-bold text-2xl">⚡</span>
                </div>
              </div>
              <h3 className="text-xl font-bold text-gray-900 mb-2">Headend Server</h3>
              <p className="text-gray-600 leading-relaxed">WireGuard termination, Go proxy & traffic mirroring</p>
            </div>
            
            <div className="group text-center">
              <div className="relative bg-gradient-to-br from-accent-500 to-accent-600 rounded-2xl p-8 mb-6 shadow-lg group-hover:shadow-xl transition-all duration-300 transform group-hover:-translate-y-1">
                <div className="absolute -top-2 -right-2 w-6 h-6 bg-secondary-500 rounded-full animate-ping animation-delay-2000"></div>
                <div className="w-16 h-16 bg-white rounded-xl flex items-center justify-center mx-auto shadow-lg">
                  <span className="text-accent-600 font-bold text-2xl">📱</span>
                </div>
              </div>
              <h3 className="text-xl font-bold text-gray-900 mb-2">Client Applications</h3>
              <p className="text-gray-600 leading-relaxed">Native, React Native mobile, Docker & embedded</p>
            </div>
          </div>
          
          {/* Connection Arrows */}
          <div className="hidden lg:block absolute top-1/2 left-1/4 transform -translate-y-1/2">
            <ArrowRightIcon className="h-8 w-8 text-primary-400 animate-pulse" />
          </div>
          <div className="hidden lg:block absolute top-1/2 right-1/4 transform -translate-y-1/2">
            <ArrowRightIcon className="h-8 w-8 text-secondary-400 animate-pulse animation-delay-1000" />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Hero;