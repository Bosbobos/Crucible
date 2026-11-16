import {defineConfig} from 'vite';
export default defineConfig({server:{proxy:{'/api':{target:process.env.CRUCIBLE_DEV_API||'http://127.0.0.1:28080',changeOrigin:true,
 headers:{Origin:process.env.CRUCIBLE_DEV_API||'http://127.0.0.1:28080'}}}}});
