import React from 'react';
import {
  CpuChipIcon,
  ShieldCheckIcon,
  CircuitBoardIcon,
  CloudIcon,
  EnvelopeIcon,
  PhoneIcon,
} from '@heroicons/react/24/outline';

const embeddedFeatures = [
  {
    name: 'Hardware Integration',
    description: 'Native integration with ARM and x86 embedded systems, IoT devices, and edge computing platforms.',
    icon: CpuChipIcon,
    color: 'bg-blue-500',
  },
  {
    name: 'Security-First Design',
    description: 'Hardware-level security features including secure boot, hardware encryption, and trusted execution.',
    icon: ShieldCheckIcon,
    color: 'bg-green-500',
  },
  {
    name: 'Custom Firmware',
    description: 'Tailored firmware solutions for your specific hardware platform with optimized performance.',
    icon: CircuitBoardIcon,
    color: 'bg-purple-500',
  },
  {
    name: 'Edge-to-Cloud',
    description: 'Seamless connectivity from edge devices to cloud infrastructure with Zero Trust security.',
    icon: CloudIcon,
    color: 'bg-indigo-500',
  },
];

const EmbeddedSolutions: React.FC = () => {
  return (
    <div id="embedded" className="bg-gradient-to-b from-gray-50 to-white py-20 sm:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
            🔌 Embedded Solutions
          </h2>
          <p className="text-xl text-gray-600 max-w-3xl mx-auto mb-8">
            Custom SASEWaddle implementations for embedded systems, IoT devices, and edge computing platforms. 
            Secure connectivity from the smallest sensors to the largest industrial systems.
          </p>
          <div className="inline-flex items-center px-4 py-2 bg-amber-100 border border-amber-200 rounded-lg">
            <span className="text-amber-800 font-medium">Enterprise Feature</span>
          </div>
        </div>

        {/* Features Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 mb-16">
          {embeddedFeatures.map((feature, index) => (
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

        {/* Use Cases */}
        <div className="bg-white rounded-2xl p-8 lg:p-12 border border-gray-200 mb-16">
          <div className="text-center mb-12">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">Embedded Use Cases</h3>
            <p className="text-gray-600 max-w-2xl mx-auto">
              SASEWaddle embedded solutions secure connectivity across diverse industrial and IoT environments
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="w-16 h-16 bg-blue-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">🏭</span>
              </div>
              <h4 className="text-lg font-semibold text-gray-900 mb-2">Industrial IoT</h4>
              <p className="text-gray-600 text-sm">
                Manufacturing equipment, SCADA systems, and industrial sensors with secure remote access and monitoring.
              </p>
            </div>

            <div className="text-center">
              <div className="w-16 h-16 bg-green-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">🚗</span>
              </div>
              <h4 className="text-lg font-semibold text-gray-900 mb-2">Connected Vehicles</h4>
              <p className="text-gray-600 text-sm">
                Automotive telematics, fleet management, and vehicle-to-infrastructure communication systems.
              </p>
            </div>

            <div className="text-center">
              <div className="w-16 h-16 bg-purple-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">🏥</span>
              </div>
              <h4 className="text-lg font-semibold text-gray-900 mb-2">Medical Devices</h4>
              <p className="text-gray-600 text-sm">
                Healthcare IoT, patient monitoring systems, and medical equipment with HIPAA-compliant connectivity.
              </p>
            </div>
          </div>
        </div>

        {/* Contact Sales Section */}
        <div className="bg-gradient-to-r from-primary-600 to-blue-600 rounded-2xl p-8 lg:p-12 text-center text-white">
          <h3 className="text-2xl sm:text-3xl font-bold mb-4">
            Ready to Secure Your Embedded Infrastructure?
          </h3>
          <p className="text-lg text-blue-100 mb-8 max-w-2xl mx-auto">
            Our embedded solutions team will work with you to create a custom SASEWaddle implementation 
            for your specific hardware platform and security requirements.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            {/* Email Contact */}
            <a
              href="mailto:sales@penguintech.io?subject=SASEWaddle Embedded Solutions Inquiry"
              className="inline-flex items-center px-6 py-3 bg-white text-primary-600 font-semibold rounded-lg hover:bg-blue-50 transition-colors group"
            >
              <EnvelopeIcon className="h-5 w-5 mr-2 group-hover:scale-110 transition-transform" />
              sales@penguintech.io
            </a>

            {/* Phone Contact */}
            <div className="flex items-center text-blue-100">
              <PhoneIcon className="h-5 w-5 mr-2" />
              <span className="font-medium">Custom Pricing Available</span>
            </div>
          </div>

          <div className="mt-8 text-sm text-blue-200">
            <p>
              ✓ Free consultation • ✓ Custom development • ✓ Enterprise support • ✓ Hardware certification
            </p>
          </div>
        </div>

        {/* Technical Specifications */}
        <div className="mt-20">
          <div className="text-center mb-12">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">Supported Platforms</h3>
            <p className="text-gray-600 max-w-2xl mx-auto">
              SASEWaddle embedded solutions support a wide range of hardware architectures and operating systems
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <div className="bg-white rounded-xl p-6 border border-gray-200">
              <h4 className="text-lg font-semibold text-gray-900 mb-4">ARM Processors</h4>
              <ul className="space-y-2 text-sm text-gray-600">
                <li>• Cortex-A53/A72/A78</li>
                <li>• Raspberry Pi 4/5</li>
                <li>• NVIDIA Jetson</li>
                <li>• Qualcomm Snapdragon</li>
              </ul>
            </div>

            <div className="bg-white rounded-xl p-6 border border-gray-200">
              <h4 className="text-lg font-semibold text-gray-900 mb-4">x86 Platforms</h4>
              <ul className="space-y-2 text-sm text-gray-600">
                <li>• Intel Atom/Core</li>
                <li>• AMD Ryzen Embedded</li>
                <li>• Industrial PCs</li>
                <li>• Edge Gateways</li>
              </ul>
            </div>

            <div className="bg-white rounded-xl p-6 border border-gray-200">
              <h4 className="text-lg font-semibold text-gray-900 mb-4">Operating Systems</h4>
              <ul className="space-y-2 text-sm text-gray-600">
                <li>• Embedded Linux</li>
                <li>• Yocto/OpenWRT</li>
                <li>• Ubuntu Core</li>
                <li>• Custom RTOS</li>
              </ul>
            </div>

            <div className="bg-white rounded-xl p-6 border border-gray-200">
              <h4 className="text-lg font-semibold text-gray-900 mb-4">Connectivity</h4>
              <ul className="space-y-2 text-sm text-gray-600">
                <li>• 4G/5G Cellular</li>
                <li>• Wi-Fi 6/6E</li>
                <li>• Ethernet/PoE</li>
                <li>• LoRaWAN/Zigbee</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default EmbeddedSolutions;