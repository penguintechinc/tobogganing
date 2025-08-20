import React from 'react';
import Link from 'next/link';
import { 
  ArrowRightIcon, 
  DocumentTextIcon, 
  CodeBracketIcon,
  ChatBubbleLeftRightIcon
} from '@heroicons/react/24/outline';

const CallToAction: React.FC = () => {
  return (
    <div className="bg-gradient-to-r from-primary-600 to-blue-700">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 sm:py-20">
        {/* Main CTA */}
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-white mb-6">
            Ready to Secure Your Network?
          </h2>
          <p className="text-xl text-blue-100 mb-8 max-w-3xl mx-auto">
            Join thousands of organizations using SASEWaddle to implement Zero Trust 
            network security. Get started in minutes with our comprehensive deployment guides.
          </p>
          
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <Link
              href="/downloads"
              className="bg-white text-primary-600 px-8 py-4 rounded-lg text-lg font-semibold hover:bg-gray-50 transition-all duration-200 flex items-center group shadow-lg hover:shadow-xl"
            >
              Download Now
              <ArrowRightIcon className="h-5 w-5 ml-2 group-hover:translate-x-1 transition-transform" />
            </Link>
            <Link
              href="/docs/quickstart"
              className="bg-transparent text-white border-2 border-white px-8 py-4 rounded-lg text-lg font-semibold hover:bg-white hover:text-primary-600 transition-all duration-200"
            >
              Quick Start Guide
            </Link>
          </div>
        </div>

        {/* Resource Links */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="bg-white/10 backdrop-blur rounded-2xl p-6 text-center hover:bg-white/20 transition-all duration-300">
            <div className="inline-flex items-center justify-center w-12 h-12 bg-white/20 rounded-lg mb-4">
              <DocumentTextIcon className="h-6 w-6 text-white" />
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Documentation</h3>
            <p className="text-blue-100 text-sm mb-4">
              Comprehensive guides, API reference, and deployment examples
            </p>
            <Link
              href="/docs"
              className="text-white hover:text-blue-200 text-sm font-medium inline-flex items-center"
            >
              Browse Docs
              <ArrowRightIcon className="h-4 w-4 ml-1" />
            </Link>
          </div>

          <div className="bg-white/10 backdrop-blur rounded-2xl p-6 text-center hover:bg-white/20 transition-all duration-300">
            <div className="inline-flex items-center justify-center w-12 h-12 bg-white/20 rounded-lg mb-4">
              <CodeBracketIcon className="h-6 w-6 text-white" />
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Source Code</h3>
            <p className="text-blue-100 text-sm mb-4">
              Open source on GitHub with examples and contribution guidelines
            </p>
            <Link
              href="https://github.com/your-org/sasewaddle"
              target="_blank"
              rel="noopener noreferrer"
              className="text-white hover:text-blue-200 text-sm font-medium inline-flex items-center"
            >
              View on GitHub
              <ArrowRightIcon className="h-4 w-4 ml-1" />
            </Link>
          </div>

          <div className="bg-white/10 backdrop-blur rounded-2xl p-6 text-center hover:bg-white/20 transition-all duration-300">
            <div className="inline-flex items-center justify-center w-12 h-12 bg-white/20 rounded-lg mb-4">
              <ChatBubbleLeftRightIcon className="h-6 w-6 text-white" />
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Community</h3>
            <p className="text-blue-100 text-sm mb-4">
              Join our community for support, discussions, and feature requests
            </p>
            <Link
              href="/community"
              className="text-white hover:text-blue-200 text-sm font-medium inline-flex items-center"
            >
              Join Discussion
              <ArrowRightIcon className="h-4 w-4 ml-1" />
            </Link>
          </div>
        </div>

        {/* Statistics */}
        <div className="mt-16 border-t border-white/20 pt-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
            <div>
              <div className="text-3xl font-bold text-white mb-1">10k+</div>
              <div className="text-blue-200 text-sm">Downloads</div>
            </div>
            <div>
              <div className="text-3xl font-bold text-white mb-1">500+</div>
              <div className="text-blue-200 text-sm">GitHub Stars</div>
            </div>
            <div>
              <div className="text-3xl font-bold text-white mb-1">50+</div>
              <div className="text-blue-200 text-sm">Contributors</div>
            </div>
            <div>
              <div className="text-3xl font-bold text-white mb-1">99.9%</div>
              <div className="text-blue-200 text-sm">Uptime</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CallToAction;