module.exports = {
  preset: 'jest-expo',
  setupFilesAfterEnv: ['<rootDir>/frontend-tests/jest.setup.ts'],
  testMatch: ['<rootDir>/frontend-tests/**/*.test.tsx'],
};
