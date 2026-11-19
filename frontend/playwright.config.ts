import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./tests',workers:1,use:{baseURL:'http://127.0.0.1:8000',channel:'msedge',headless:true,viewport:{width:1440,height:1000}},reporter:'list'});
