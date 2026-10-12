// A simulated host uses the official AppBridge, real iframe and actual stdio server.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdir, mkdtemp, writeFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { chromium } from 'playwright';
import { build } from 'esbuild';
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';

const project = path.resolve(import.meta.dirname, '..');
const artifacts = path.join(project, 'tests/artifacts');
const dataDir = await mkdtemp(path.join(os.tmpdir(), 'skill2ui-mcp-browser-'));
const python = process.env.SKILL2UI_PYTHON || path.join(project, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const client = new Client({name:'Skill2UI browser acceptance host', version:'0.1.0'}, {capabilities:{extensions:{'io.modelcontextprotocol/ui':{mimeTypes:['text/html;profile=mcp-app']}}}});
const transport = new StdioClientTransport({command:python,args:['-m','skill2ui','mcp','--data-dir',dataDir],cwd:project,env:{PYTHONUTF8:'1'},stderr:'pipe'});
let stderr = '';
transport.stderr?.on('data', chunk => stderr += chunk.toString());
const report = {date:new Date().toISOString(), status:'running', host:'Simulated browser host using official AppBridge 2.0.3', server:'Real Skill2UI stdio process', checks:[], limitations:['Production Codex/Claude embedding not tested','MCP Skill execution is intentionally unavailable; use standalone runtime','Test iframe checks isolation and CSP, not the complete host sandbox proxy specification']};
let browser, server, page;
const hostCalls=[];
try {
  await mkdir(artifacts,{recursive:true});
  await client.connect(transport);
  assert.equal(client.getServerVersion().version,'0.1.0');
  const tools = (await client.listTools()).tools;
  assert.equal(tools.find(t=>t.name==='skill2ui_generate')._meta.ui.resourceUri,'ui://skill2ui/app.html');
  assert.deepEqual(tools.find(t=>t.name==='skill2ui_evaluate')._meta.ui.visibility,['app']);
  const resources = (await client.listResources()).resources;
  assert.equal(resources[0].mimeType,'text/html;profile=mcp-app');
  const resource = await client.readResource({uri:'ui://skill2ui/app.html'});
  let appHtml = resource.contents[0].text;
  assert.ok(appHtml.includes('<!doctype html>'));
  // Apply a restrictive CSP in this simulated host's opaque-origin iframe.
  appHtml = appHtml.replace('<head>','<head><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; connect-src \'none\'; object-src \'none\'; base-uri \'none\'">');
  const initial = await client.callTool({name:'skill2ui_generate',arguments:{prompt:'AA费用计算器'}});
  assert.equal(initial.structuredContent.document.kind,'calculator');
  report.checks.push('Official Node MCP Client initializes, lists tools/resources, reads App HTML, generates calculator over actual stdio');
  const hostCode = `
    import { AppBridge, PostMessageTransport } from '@modelcontextprotocol/ext-apps/app-bridge';
    const fixture = await (await fetch('/fixture')).json();
    const iframe = document.createElement('iframe');
    iframe.id='view'; iframe.title='Skill2UI MCP App';
    iframe.setAttribute('sandbox','allow-scripts allow-same-origin');
    iframe.style.cssText='width:100%;height:900px;border:0';
    document.body.append(iframe);
    window.testState={initialized:false,calls:[],errors:[]};
    const bridge=new AppBridge(null,{name:'Skill2UI test host',version:'0.1.0'},{serverTools:{},logging:{}},{hostContext:{theme:'light',displayMode:'inline'}});
    bridge.oncalltool=async params=>{
      window.testState.calls.push(params.name);
      return await window.invokeMcpTool(params);
    };
    bridge.onerror=error=>window.testState.errors.push(error.message);
    bridge.oninitialized=async()=>{
      window.testState.initialized=true;
      await bridge.sendToolInput({arguments:{prompt:'AA费用计算器'}});
      await bridge.sendToolResult(fixture.initial);
    };
    window.testBridge=bridge;
    await bridge.connect(new PostMessageTransport(iframe.contentWindow,iframe.contentWindow));
    // A data URL remains opaque-origin even with the specification's allow-same-origin permission.
    iframe.src='data:text/html;charset=utf-8,'+encodeURIComponent(fixture.appHtml);
  `;
  const built = await build({stdin:{contents:hostCode,resolveDir:project,sourcefile:'mcp-test-host.js'},bundle:true,format:'esm',platform:'browser',write:false});
  const hostBundle = built.outputFiles[0].text;
  server = createServer((request,response)=>{
    if(request.url==='/fixture'){response.writeHead(200,{'Content-Type':'application/json'});response.end(JSON.stringify({initial,appHtml}));}
    else if(request.url==='/host.js'){response.writeHead(200,{'Content-Type':'application/javascript'});response.end(hostBundle);}
    else if(request.url==='/'){response.writeHead(200,{'Content-Type':'text/html'});response.end('<!doctype html><html><head><meta charset="utf-8"><title>Skill2UI simulated MCP host</title></head><body><script type="module" src="/host.js"></script></body></html>');}
    else {response.writeHead(404);response.end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({headless:true});
  page = await browser.newPage({viewport:{width:1180,height:980}});
  page.setDefaultTimeout(15000);
  const pageErrors=[], requests=[];
  page.on('pageerror',error=>pageErrors.push(error.message));
  page.on('request',request=>requests.push(request.url()));
  await page.exposeFunction('invokeMcpTool',async params=>{
    const result=await client.callTool(params);
    hostCalls.push({name:params.name,isError:result.isError||false,theme:result.structuredContent?.document?.theme,...(result.isError?{content:result.content}:{})});
    return result;
  });
  await page.goto(base);
  await page.waitForFunction(()=>window.testState?.initialized,{timeout:15000});
  const view = page.frameLocator('#view');
  await view.getByLabel('总金额',{exact:true}).waitFor({timeout:15000});
  await page.waitForFunction(()=>window.testState.calls.includes('skill2ui_evaluate'));
  const metrics = view.locator('.metric strong');
  await metrics.first().filter({hasText:'165'}).waitFor();
  assert.equal(await page.locator('#view').getAttribute('sandbox'),'allow-scripts allow-same-origin');
  const parentAccess = await view.locator('body').evaluate(()=>{try{return Boolean(window.parent.document.body);}catch{return false;}});
  assert.equal(parentAccess,false,'Opaque-origin App cannot read the host DOM');
  report.checks.push('Official AppBridge/PostMessageTransport handshake and tool-input/tool-result notifications render actual resource inside sandboxed iframe');
  report.checks.push('Opaque-origin sandbox rejects App access to parent DOM');
  await view.getByLabel('总金额',{exact:true}).fill('900');
  await view.getByLabel('人数',{exact:true}).fill('3');
  const tip=view.getByLabel('小费比例 (%)',{exact:true});
  await tip.press('Home');
  for(let index=0;index<20;index++)await tip.press('ArrowRight');
  await metrics.first().filter({hasText:'360'}).waitFor();
  await metrics.nth(1).filter({hasText:'1080'}).waitFor();
  report.checks.push('App input -> official bridge tools/call -> real stdio evaluate -> live metrics: 900, 3, 20% = 360 per person / 1080 total');
  await view.getByLabel('人数',{exact:true}).fill('0');
  await view.locator('[role="status"]').filter({hasText:/people|minimum|at least|参数|人数/}).waitFor({timeout:15000});
  await view.getByLabel('人数',{exact:true}).fill('3');
  await metrics.first().filter({hasText:'360'}).waitFor();
  await view.getByLabel('修改界面',{exact:true}).fill('把页面改成深色主题');
  await view.getByRole('button',{name:'更新界面',exact:true}).click();
  await view.locator('#app[data-theme="dark"]').waitFor();
  assert.equal(await view.getByLabel('总金额',{exact:true}).inputValue(),'900');
  assert.equal(await view.getByLabel('人数',{exact:true}).inputValue(),'3');
  assert.equal(await view.getByLabel('小费比例 (%)',{exact:true}).inputValue(),'20');
  await view.locator('.metric strong').first().filter({hasText:'360'}).waitFor();
  await view.getByLabel('修改界面',{exact:true}).fill('把页面改成浅色主题');
  await view.getByLabel('修改界面',{exact:true}).press('Enter');
  await view.locator('#app[data-theme="light"]').waitFor();
  await view.locator('.metric strong').first().filter({hasText:'360'}).waitFor();
  assert.equal(await view.getByLabel('总金额',{exact:true}).inputValue(),'900');
  report.checks.push('Server validation errors display, valid inputs recover, click/Enter follow-ups work without form permissions, theme edits preserve input state');
  const snapshot=await page.evaluate(()=>window.testState);
  assert.ok(snapshot.calls.includes('skill2ui_generate'));
  assert.deepEqual(snapshot.errors,[]);
  assert.deepEqual(pageErrors,[]);
  assert.ok(requests.every(url=>url.startsWith(base)||url==='about:blank'||url.startsWith('data:text/html')),'No external resource/network requests');
  await page.screenshot({path:path.join(artifacts,'mcp-app.png'),fullPage:true});
  report.status='passed';
  report.tool_calls=snapshot.calls;
  report.page_errors=pageErrors;
  report.network_requests=requests.map(url=>url.startsWith('data:text/html')?'data:text/html (bundled App resource)':url);
  report.resource_bytes=Buffer.byteLength(resource.contents[0].text);
  report.server_version=client.getServerVersion();
  report.screenshot='mcp-app.png';
  console.log(JSON.stringify(report,null,2));
} catch(error) {
  report.status='failed';report.error=error.stack;report.server_stderr=stderr;
  report.host_calls=hostCalls;
  if(page){report.host_state=await page.evaluate(()=>window.testState).catch(()=>null);report.app_text=await page.frameLocator('#view').locator('body').innerText().catch(()=>null);await page.screenshot({path:path.join(artifacts,'mcp-failure.png'),fullPage:true}).catch(()=>{});}
  throw error;
} finally {
  await writeFile(path.join(artifacts,'mcp-report.json'),JSON.stringify(report,null,2));
  await browser?.close();
  if(server)await new Promise(resolve=>server.close(resolve));
  await client.close();
  await transport.close();
  await rm(dataDir,{recursive:true,force:true});
}
