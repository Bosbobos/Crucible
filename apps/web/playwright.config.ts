import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',workers:1,timeout:45000,use:{baseURL:process.env.CRUCIBLE_TEST_ORIGIN||'http://127.0.0.1:28080',viewport:{width:1440,height:1100},trace:'retain-on-failure'},outputDir:'../../.private/evidence/browser',reporter:'list'});
