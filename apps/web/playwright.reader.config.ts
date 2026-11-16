import {defineConfig} from '@playwright/test';
import base from './playwright.config';

// Изолированная проверка интерфейса: только синтетические ответы API, без входа и БД.
export default defineConfig(base, {
  testMatch: ['reader.spec.ts','wheel-gesture.spec.ts'],
  outputDir: '../../.private/evidence/reader',
  use: {
    baseURL: 'http://127.0.0.1:4174',
    launchOptions: process.env.CRUCIBLE_TEST_BROWSER_EXECUTABLE ? {executablePath: process.env.CRUCIBLE_TEST_BROWSER_EXECUTABLE} : {},
  },
  webServer: {command: 'npm run dev -- --port 4174 --strictPort', url: 'http://127.0.0.1:4174', reuseExistingServer: !process.env.CI},
});
