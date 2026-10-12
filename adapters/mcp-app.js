import { App } from '@modelcontextprotocol/ext-apps';

// This adapter uses the official host bridge; it makes no localhost HTTP requests.
const host = new App({name: 'Skill2UI', version: '0.1.0'});
let documentUI, state = {}, revision = 0;
const root = document.getElementById('app');
const style = document.createElement('style');
style.textContent = `*{box-sizing:border-box}body{margin:0;font:14px system-ui;color:#26374c;background:#f2f6fa}main{padding:24px;max-width:960px;margin:auto}h1{font-size:25px;margin:0 0 8px}p{line-height:1.6;color:#607087}button,input,select,textarea{font:inherit;border:1px solid #b9c9d9;border-radius:8px;padding:10px;background:#fff;color:inherit}button{cursor:pointer;background:#17665f;color:white}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid #63bcb4;outline-offset:2px}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px}.field{display:flex;flex-direction:column;gap:8px}textarea{min-height:110px}.metric{padding:18px;background:white;border-radius:12px;border:1px solid #dce5ef}.metric strong{display:block;font-size:30px;margin-top:12px}.prompt{display:flex;gap:8px;margin-top:20px}.prompt input{min-width:0;flex:1}pre{white-space:pre-wrap;word-break:break-word;padding:16px;background:white}details{padding:14px;background:#fff;border-radius:10px}svg{width:100%;height:230px}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:10px;border-bottom:1px solid #dce5ef}.error{color:#b33241}[data-theme=dark]{color:#ecf2fa;background:#142437}[data-theme=dark] .metric,[data-theme=dark] pre,[data-theme=dark] details{background:#20334a}[data-theme=dark] p{color:#b6c5d6}`;
document.head.append(style);
function el(tag, text, attrs={}) {const n=document.createElement(tag); if(text!=null)n.textContent=String(text); for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v)); return n;}
const errors=el('p','',{class:'error',role:'status'});
async function call(name,args) {const result=await host.callServerTool({name,arguments:args}); if(result.isError)throw new Error(result.content?.find(x=>x.type==='text')?.text || '操作失败'); return result.structuredContent || JSON.parse(result.content.find(x=>x.type==='text').text);}
function show(result) {
  if(!result?.document)return;
  const previous=documentUI;
  documentUI=result.document;
  if(previous?.id!==documentUI.id)state={};
  else for(const c of documentUI.components){const old=previous.components.find(i=>i.id===c.id);if(old&&JSON.stringify(old.value)!==JSON.stringify(c.value))state[c.id]=c.value;}
  render();
}
function render() {
  root.replaceChildren(); root.dataset.theme=documentUI.theme;
  root.append(el('small','Skill2UI · MCP App'),el('h1',documentUI.title),el('p',documentUI.description));
  const fields=el('div',null,{class:'fields'});
  const metrics=[];
  const add=(components,target)=>{for(const c of components){
    if(c.type==='group'){const group=el('details');group.append(el('summary',c.label));add(c.children,group);target.append(group);continue;}
    if(c.type==='metric'){const metric=el('div',null,{class:'metric'}),value=el('strong','—');metric.append(el('span',c.label),value);target.append(metric);metrics.push([c,value]);continue;}
    if(['number','slider','text','textarea','select'].includes(c.type)){
      const label=el('label',null,{class:'field'});label.append(el('span',c.label));
      const input=el(c.type==='select'?'select':c.type==='textarea'?'textarea':'input',null,{'aria-label':c.label});
      if(c.type==='select')for(const option of c.options)input.append(el('option',option,{value:option}));
      else if(input.tagName==='INPUT')input.type=c.type==='slider'?'range':c.type==='number'?'number':'text';
      for(const name of ['min','max','step'])if(c[name]!=null)input.setAttribute(name,c[name]);
      input.value=state[c.id]??c.value??'';
      input.oninput=()=>{state[c.id]=['number','slider'].includes(c.type)?Number(input.value):input.value;refresh();};label.append(input);target.append(label);continue;
    }
    if(c.type==='file'||c.type==='action'||c.type==='log'||c.type==='progress')return;
    const panel=el('details');panel.open=true;panel.append(el('summary',c.label));
    if(['table','chart'].includes(c.type)&&documentUI.data.length){const table=el('table'),head=el('tr');const keys=Object.keys(documentUI.data[0]);for(const key of keys)head.append(el('th',key));table.append(head);for(const row of documentUI.data){const tr=el('tr');for(const key of keys)tr.append(el('td',row[key]));table.append(tr);}panel.append(table);}
    else panel.append(el('pre',typeof c.value==='object'?JSON.stringify(c.value,null,2):c.value??'使用参数区编辑内容。'));
    target.append(panel);
  }};
  add(documentUI.components,fields);root.append(fields);
  if(documentUI.kind==='skill')root.append(el('p','已静态识别 Skill。文件上传、授权和脚本执行请在独立浏览器运行时完成：skill2ui serve。'));
  const form=el('div',null,{class:'prompt'}),prompt=el('input',null,{'aria-label':'修改界面',placeholder:'描述修改，如「改成深色主题」'}),button=el('button','更新界面',{type:'button'});
  const update=async()=>{button.disabled=true;try{show(await call('skill2ui_generate',{prompt:prompt.value,document:documentUI,state}));}catch(e){errors.textContent=e.message;}finally{button.disabled=false;}};
  form.append(prompt,button);button.onclick=update;prompt.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();if(!button.disabled)update();}};
  root.append(form,errors);
  async function refresh(){const own=++revision;try{const result=await call('skill2ui_evaluate',{document:documentUI,state});if(own!==revision)return;for(const [c,value]of metrics)value.textContent=result.metrics[c.id]??'—';errors.textContent='';}catch(e){if(own===revision)errors.textContent=e.message;}}
  refresh();
}
host.ontoolresult=result=>{try{show(result.structuredContent||JSON.parse(result.content?.find(x=>x.type==='text')?.text||'{}'));}catch(e){errors.textContent=e.message;}};
host.onerror=error=>{errors.textContent=error.message;};
root.append(el('h1','Skill2UI'),el('p','等待宿主传入界面。使用 skill2ui_generate 生成交互工具。'),errors);
await host.connect();
