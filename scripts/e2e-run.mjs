// HTTP-прокси работает только в namespace web, без публикации нового порта хоста.
import http from 'node:http';
// Playwright запускается дочерним процессом, а его код возврата сохраняется.
import {spawn} from 'node:child_process';
// Browser Origin должен совпасть с Origin в конфигурации practice.
const origin=new URL(process.env.CRUCIBLE_TEST_ORIGIN||'http://localhost:18080');
// Разрешаем только локальный HTTP-стенд, предназначенный для этих тестов.
if(origin.protocol!=='http:'||origin.hostname!=='localhost')throw new Error('E2E origin must be local HTTP');
// Nginx уже слушает 8080 в общем network namespace.
const server=http.createServer((request,response)=>{
  // Заголовки Origin/Host сохраняются; перенаправляется только TCP-назначение.
  const upstream=http.request({host:'127.0.0.1',port:8080,path:request.url,method:request.method,headers:request.headers},result=>{
    // Browser получает настоящий статус и заголовки приложения.
    response.writeHead(result.statusCode,result.headers);
    // Тело ответа передаётся без интерпретации HTML или JSON.
    result.pipe(response);
  });
  // Недоступность nginx остаётся явной HTTP-ошибкой.
  upstream.on('error',()=>{response.writeHead(502);response.end();});
  // Тело исходного запроса передаётся приложению без изменений.
  request.pipe(upstream);
});
// Запускаем тесты после успешного открытия loopback-порта.
server.listen(Number(origin.port||80),'127.0.0.1',()=>{
  // Shell не используется, аргументы передаются напрямую.
  const child=spawn('npx',['playwright','test'],{stdio:'inherit',env:process.env});
  // При завершении контейнера останавливаем и дочерний процесс.
  process.on('SIGTERM',()=>child.kill('SIGTERM'));
  // Код тестов является кодом завершения контейнера.
  child.on('exit',code=>server.close(()=>process.exit(code??1)));
});
