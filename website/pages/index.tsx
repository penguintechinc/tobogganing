import React from 'react';
import Head from 'next/head';
import Link from 'next/link';
import Layout from '../components/Layout';
import Hero from '../components/Hero';
import Features from '../components/Features';
import Architecture from '../components/Architecture';
import ManagerPortal from '../components/ManagerPortal';
import AppShowcase from '../components/AppShowcase';
import EmbeddedSolutions from '../components/EmbeddedSolutions';
import Pricing from '../components/Pricing';
import UseCases from '../components/UseCases';
import CallToAction from '../components/CallToAction';

const HomePage: React.FC = () => {
  return (
    <Layout>
      <Head>
        <title>SASEWaddle - Open Source SASE Solution</title>
        <meta name="description" content="SASEWaddle is an Open Source Secure Access Service Edge (SASE) solution with React Native mobile apps, embedded IoT support, and Zero Trust Network Architecture (ZTNA)." />
        <meta name="keywords" content="SASE, ZTNA, Zero Trust, VPN, WireGuard, Open Source, Network Security, Mobile App, React Native, Embedded IoT, Enterprise Security" />
        <meta property="og:title" content="SASEWaddle - Open Source SASE Solution" />
        <meta property="og:description" content="Enterprise-grade SASE solution with Zero Trust Network Architecture, React Native mobile apps, and embedded IoT support. Built with WireGuard, Go, and Python." />
        <meta property="og:type" content="website" />
        <meta property="og:url" content="https://sasewaddle.com" />
        <link rel="canonical" href="https://sasewaddle.com" />
      </Head>

      {/* Hero Section */}
      <Hero />

      {/* Features Section */}
      <Features />

      {/* Architecture Section */}
      <Architecture />

      {/* Manager Portal Section */}
      <ManagerPortal />

      {/* App Showcase Section */}
      <AppShowcase />

      {/* Embedded Solutions Section */}
      <EmbeddedSolutions />

      {/* Pricing Section */}
      <Pricing />

      {/* Use Cases Section */}
      <UseCases />

      {/* Call to Action Section */}
      <CallToAction />
    </Layout>
  );
};

export default HomePage;