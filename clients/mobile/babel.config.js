module.exports = {
  presets: ['module:metro-react-native-babel-preset'],
  plugins: [
    ['module-resolver', {
      root: ['./src'],
      alias: {
        '@': './src',
        '@assets': './src/assets',
        '@components': './src/components',
        '@screens': './src/screens',
        '@utils': './src/utils',
        '@types': './src/types',
        '@config': './src/config',
        '@constants': './src/constants',
        '@providers': './src/providers',
      },
    }],
  ],
};