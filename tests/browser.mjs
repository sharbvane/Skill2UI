import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { chromium } from 'playwright';

const project = path.resolve(import.meta.dirname, '..');
const output = path.join(project, 'tests/artifacts');
const dataDir = await mkdtemp(path.join(os.tmpdir(), 'skill2ui-browser-'));
const port = Number(process.env.SKILL2UI_TEST_PORT || 7862);
const base = `http://127.0.0.1:${port}`;
const python = process.env.SKILL2UI_PYTHON || path.join(project, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const runtime = spawn(python, ['-m', 'skill2ui', 'serve', '--port', String(port), '--data-dir', dataDir], {cwd:project, windowsHide:true, stdio:['ignore','pipe','pipe']});
let serverLogs=''; runtime.stderr.on('data',d=>serverLogs+=d);runtime.stdout.on('data',d=>serverLogs+=d);
const report={date:new Date().toISOString(),browser:'Chromium',groups:[],screenshots:[]};
let browser;
try {
  await mkdir(output,{recursive:true});
  for(let i=0;i<100;i++){try{if((await fetch(base+'/api/bootstrap')).ok)break;}catch{}if(i===99)throw new Error('Runtime failed: '+serverLogs);await new Promise(r=>setTimeout(r,100));}
  browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);
  const token=(await (await page.request.get(base+'/api/bootstrap')).json()).token;
  const api=async(url,body,method='POST')=>{const r=await page.request.fetch(base+url,{method,headers:{'X-Skill2UI-Token':token},...(body?{data:body}:{})});return {status:r.status(),value:await r.json()};};
  const snap=async name=>{await page.screenshot({path:path.join(output,name+'.png'),fullPage:true});report.screenshots.push(name+'.png');};
  const waitText=async(locator,text)=>{await locator.filter({hasText:text}).waitFor({timeout:15000});};
  const generate=async prompt=>{await page.getByTestId('prompt').fill(prompt);await page.getByTestId('generate').click();await page.getByTestId('generate').filter({hasText:'修改界面'}).waitFor();};
  const importSkill=async directory=>{await page.getByTestId('skill-import').click();await page.getByTestId('import-path').fill(directory);await page.getByTestId('import-submit').click();await page.locator('dialog').waitFor({state:'hidden'});await page.locator('.action-form').first().waitFor();};

  await page.locator('[data-demo="calculator"]').click();
  await page.getByLabel('总金额',{exact:true}).fill('900');await page.getByLabel('人数',{exact:true}).fill('3');
  const tip=page.getByLabel('小费比例 (%)',{exact:true});await tip.press('Home');for(let i=0;i<20;i++)await tip.press('ArrowRight');
  await waitText(page.getByTestId('per_person'),'360');
  await page.getByLabel('人数',{exact:true}).fill('0');await page.locator('.evaluation-error').waitFor();
  await page.getByLabel('人数',{exact:true}).fill('3');await waitText(page.getByTestId('per_person'),'360');
  await page.getByTestId('save').click();await page.locator('.saved-library button').waitFor();
  await snap('calculator');
  report.groups.push({group:'A',status:'passed',input:{total:900,people:3,tip:20},result:{per_person:360},recovery:'people=0 rejected, people=3 recovered'});
  console.log('A passed: live calculator, validation and save');

  await page.locator('[data-demo="chart"]').click();await page.getByLabel('数据 (CSV: label,value)',{exact:true}).fill('label,value\n"Alpha, One",10\nBeta,30');
  await page.getByLabel('筛选项目',{exact:true}).fill('Beta');
  await page.getByLabel('展示方式',{exact:true}).selectOption('table');
  await page.getByRole('cell',{name:'Beta',exact:true}).waitFor();assert.equal(await page.locator('tbody tr').count(),1);
  await generate('把柱状图改成折线图，并保留当前配置');
  assert.equal(await page.getByLabel('筛选项目',{exact:true}).inputValue(),'Beta');
  assert.equal(await page.getByLabel('图表类型',{exact:true}).inputValue(),'line');
  assert.equal(await page.getByLabel('展示方式',{exact:true}).inputValue(),'table');
  await page.getByLabel('展示方式',{exact:true}).selectOption('chart');await page.locator('polyline.chart-line').waitFor({state:'attached'});await page.locator('circle.chart-point').waitFor();
  await generate('把页面改成深色主题');assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
  await snap('data-dark');
  await page.locator('.saved-library button').click();await waitText(page.getByTestId('per_person'),'360');
  assert.equal(await page.getByLabel('总金额',{exact:true}).inputValue(),'900');
  report.groups.push({group:'B',status:'passed',input:'CSV Alpha, One=10; Beta=30, filter=Beta',result:'one row, matching chart, bar→line and dark theme retained state, saved calculator restored'});
  console.log('B passed: CSV/filter/chart/edit/restore');

  const thirdParty=path.join(project,'examples/third-party/documents');
  await importSkill(thirdParty);
  const form=page.locator('[data-action="validate-documents"]');
  await form.locator('input[type="file"]').setInputFiles(path.join(thirdParty,'fixtures/sample.pdf'));
  await form.locator('[data-parameter="json"]').check();
  await page.waitForFunction(()=>document.querySelector('[data-parameter="files"]').value.length>0);
  await form.getByRole('button',{name:'运行操作',exact:true}).click();await page.getByTestId('command').waitFor();
  assert.match(await page.getByTestId('command').textContent(),/validate-documents\.py/);
  assert.equal((await api('/api/jobs',undefined,'GET')).value.length,0,'Nothing executes before confirmation');
  await page.getByTestId('confirm-run').click();await page.getByTestId('job-result').waitFor({timeout:15000});
  const jobs=(await api('/api/jobs',undefined,'GET')).value;
  const job=jobs[0];assert.equal(job.status,'succeeded');assert.equal(job.result.status,'ok');assert.equal(job.result.summary.passed,1);
  assert.equal(job.result.render_check,false);
  assert.ok(job.artifacts.some(x=>x.name==='_skill2ui_stdout.json'));
  const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'_skill2ui_stdout.json',exact:true}).click()]);
  assert.equal(download.suggestedFilename(),'_skill2ui_stdout.json');
  await snap('third-party-execution');
  report.groups.push({group:'C',status:'passed',source:'magnus919/agent-skills @ fb3253335cdb1156522901ef52f9897212b2e4b5',input:'original fixtures/sample.pdf; json=true; render_check=false',result:{status:job.status,summary:job.result.summary,artifact:'_skill2ui_stdout.json'},scope:'structural PDF validation; external renderers not exercised'});
  console.log('C passed: real third-party GUI task and output download');

  const guideDir=path.join(dataDir,'guide-example'),toolDir=path.join(dataDir,'tool-example');
  await mkdir(guideDir);await mkdir(toolDir);
  await writeFile(path.join(guideDir,'SKILL.md'),'---\nname: guide-example\ndescription: A documentation-only planning guide.\n---\n# Plan\nChoose a target, prepare inputs, review the result.');
  await writeFile(path.join(toolDir,'SKILL.md'),'---\nname: tool-example\ndescription: A native git CLI skill.\nallowed-tools: Bash(git:*)\n---\nUse git --version to inspect installed tooling.');
  await writeFile(path.join(toolDir,'skill2ui.json'),JSON.stringify({actions:[{id:'version',label:'Git version',executable:'git',args:['--version'],parameters:[]}]}));
  const guide=(await api('/api/skills/import',{path:guideDir})).value,tool=(await api('/api/skills/import',{path:toolDir})).value;
  assert.equal(guide.category,'guide');assert.ok(guide.actions.every(x=>x.status!=='ready'));
  assert.equal(tool.category,'tool');assert.equal(tool.actions[0].status,'ready');
  const prepared=(await api('/api/actions/prepare',{skill_id:tool.id,action_id:'version',arguments:{}})).value;
  const created=(await api('/api/jobs',{approval_id:prepared.approval_id,confirmed:true})).value;
  let completed;for(let i=0;i<60;i++){completed=(await api('/api/jobs/'+created.id,undefined,'GET')).value;if(!['queued','running'].includes(completed.status))break;await new Promise(r=>setTimeout(r,100));}
  assert.equal(completed.status,'succeeded');assert.match(completed.logs.join(''),/git version/);
  report.groups.push({group:'D',status:'passed',input:'script documents, registered native git, prose-only guide',result:'correct categories, guide non-executable, native Git invocation succeeded'});
  console.log('D passed: script/tool/guide and native invocation');

  const denied=await api('/api/jobs',{approval_id:'invented',confirmed:true});assert.equal(denied.status,400);
  assert.equal((await api('/api/jobs',{approval_id:prepared.approval_id,confirmed:true})).status,400,'approval cannot be reused');
  const evil=(await page.request.post(base+'/api/generate',{headers:{'X-Skill2UI-Token':token,Origin:'https://evil.example'},data:{prompt:'AA'}})).status();assert.equal(evil,403);
  const ui=(await api('/api/generate',{prompt:'AA'})).value.document;ui.components[0].type='script';
  assert.equal((await api('/api/evaluate',{document:ui,state:{}})).status,422);
  await page.locator('[data-demo="plan"]').click();await page.getByLabel('计划步骤（每行一项）',{exact:true}).fill('09:00 Prepare\n10:00 Build');
  await page.locator('.timeline input[type="checkbox"]').first().check();assert.equal(await page.locator('.timeline-step.completed').count(),1);
  await page.locator('[data-demo="scale"]').click();await page.getByLabel('成本权重',{exact:true}).press('End');await page.getByLabel('质量权重',{exact:true}).press('Home');await page.getByLabel('速度权重',{exact:true}).press('Home');
  await page.getByRole('img',{name:/方案评估|加权得分/}).waitFor();
  await page.locator('[data-demo="file"]').click();
  await page.getByLabel('选择文件',{exact:true}).setInputFiles({name:'preview.txt',mimeType:'text/plain',buffer:Buffer.from('Skill2UI file preview works')});
  await waitText(page.locator('.text-preview'),'Skill2UI file preview works');
  await page.setViewportSize({width:390,height:844});await snap('mobile');
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);assert.equal(overflow,false,'Mobile must not overflow');
  await page.keyboard.press('Tab');assert.ok(await page.evaluate(()=>document.activeElement!==document.body));
  assert.deepEqual(errors,[]);
  report.groups.push({group:'E',status:'passed',result:'invalid input/schema, missing/reused approval and foreign origin rejected; recovery, plan, weighted scores, text preview, 390px layout and keyboard checked',unitCoverage:'Missing dependencies, malicious archives, process cancellation/timeout, source tampering, restart recovery are covered in Python tests'});
  report.status='passed';await writeFile(path.join(output,'browser-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
}catch(error){report.status='failed';report.error=error.stack;await writeFile(path.join(output,'browser-report.json'),JSON.stringify(report,null,2));throw error;}
finally{await browser?.close();runtime.kill();await new Promise(r=>runtime.once('exit',r));await rm(dataDir,{recursive:true,force:true});}
