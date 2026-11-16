import {defineConfig} from '@playwright/test';
import base from './playwright.config';

export default defineConfig({
  ...base,
  testMatch: 'callouts.spec.ts',
  outputDir: '../../.private/evidence/callouts',
  use: {
    ...base.use,
    baseURL: process.env.CRUCIBLE_TEST_ORIGIN || 'http://127.0.0.1:4175',
    launchOptions: process.env.CRUCIBLE_TEST_BROWSER_EXECUTABLE ? {executablePath: process.env.CRUCIBLE_TEST_BROWSER_EXECUTABLE} : {},
  },
  webServer: process.env.CRUCIBLE_TEST_ORIGIN ? [] : {
    command: 'npm run dev -- --port 4175 --strictPort',
    url: 'http://127.0.0.1:4175',
    reuseExistingServer: !process.env.CI,
  },
});
