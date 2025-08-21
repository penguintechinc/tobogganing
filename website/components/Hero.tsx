import React from 'react';
import Link from 'next/link';
import { ArrowRightIcon, ShieldCheckIcon, CloudIcon, LockClosedIcon } from '@heroicons/react/24/outline';

const Hero: React.FC = () => {
  return (
    <div className="bg-gradient-to-br from-primary-50 via-white to-secondary-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 sm:py-24 lg:py-32">
        <div className="text-center">
          {/* Badge */}
          <div className="inline-flex items-center px-4 py-2 rounded-full bg-primary-100 text-primary-700 text-sm font-medium mb-8">
            <ShieldCheckIcon className="h-4 w-4 mr-2" />
            Open Source SASE Solution
          </div>

          {/* Main heading */}
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 mb-6 leading-tight">
            Secure Access Service Edge
            <span className="block text-primary-600">Built for the Modern Enterprise</span>
          </h1>

          {/* Description */}
          <p className="text-xl text-gray-600 mb-10 max-w-3xl mx-auto leading-relaxed">
            SASEWaddle implements Zero Trust Network Architecture (ZTNA) with enterprise-grade security, 
            high-performance WireGuard VPN, React Native mobile apps, and seamless multi-platform client support. 
            Deploy anywhere, scale everywhere.
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center mb-16">
            <Link
              href="/downloads"
              className="bg-primary-600 text-white px-8 py-4 rounded-lg text-lg font-semibold hover:bg-primary-700 transition-all duration-200 flex items-center group shadow-lg hover:shadow-xl"
            >
              Get Started Free
              <ArrowRightIcon className="h-5 w-5 ml-2 group-hover:translate-x-1 transition-transform" />
            </Link>
            <Link
              href="/docs"
              className="bg-white text-primary-600 border-2 border-primary-600 px-8 py-4 rounded-lg text-lg font-semibold hover:bg-primary-50 transition-colors duration-200"
            >
              View Documentation
            </Link>
          </div>

          {/* Key Features */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-4xl mx-auto">
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-12 h-12 bg-primary-100 rounded-lg mb-4">
                <LockClosedIcon className="h-6 w-6 text-primary-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Zero Trust Security</h3>
              <p className="text-gray-600">
                Dual authentication with X.509 certificates and JWT/SSO integration
              </p>
            </div>
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-12 h-12 bg-primary-100 rounded-lg mb-4">
                <CloudIcon className="h-6 w-6 text-primary-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Cloud Native</h3>
              <p className="text-gray-600">
                Deploy on Kubernetes, Docker, or cloud providers with auto-scaling
              </p>
            </div>
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-12 h-12 bg-primary-100 rounded-lg mb-4">
                <ShieldCheckIcon className="h-6 w-6 text-primary-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Enterprise Ready</h3>
              <p className="text-gray-600">
                Traffic mirroring, audit logging, and compliance-ready features
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Architecture Preview */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pb-20">
        <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 p-8 lg:p-12">
          <div className="text-center mb-8">
            <h2 className="text-2xl font-bold text-gray-900 mb-4">Enterprise Architecture</h2>
            <p className="text-gray-600 max-w-2xl mx-auto">
              Three-tier architecture with Manager Service, Headend Server, and Client Applications
            </p>
          </div>
          
          {/* Architecture Diagram */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-center">
            <div className="text-center">
              <div className="bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl p-6 mb-4">
                <div className="w-12 h-12 bg-white rounded-lg flex items-center justify-center mx-auto">
                  <span className="text-blue-600 font-bold">M</span>
                </div>
              </div>
              <h3 className="font-semibold text-gray-900">Manager Service</h3>
              <p className="text-sm text-gray-600 mt-1">Central orchestration & certificates</p>
            </div>
            
            <div className="text-center">
              <div className="bg-gradient-to-br from-green-500 to-green-600 rounded-xl p-6 mb-4">
                <div className="w-12 h-12 bg-white rounded-lg flex items-center justify-center mx-auto">
                  <span className="text-green-600 font-bold">H</span>
                </div>
              </div>
              <h3 className="font-semibold text-gray-900">Headend Server</h3>
              <p className="text-sm text-gray-600 mt-1">WireGuard termination & proxy</p>
            </div>
            
            <div className="text-center">
              <div className="bg-gradient-to-br from-purple-500 to-purple-600 rounded-xl p-6 mb-4">
                <div className="w-12 h-12 bg-white rounded-lg flex items-center justify-center mx-auto">
                  <span className="text-purple-600 font-bold">C</span>
                </div>
              </div>
              <h3 className="font-semibold text-gray-900">Client Applications</h3>
              <p className="text-sm text-gray-600 mt-1">Native, mobile, Docker & embedded</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Hero;