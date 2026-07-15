const files = {
  'src/index.js': `import { createApp } from './app.js';\nimport './styles.css';\n\nconst app = createApp({\n  root: document.querySelector('#app'),\n  theme: 'midnight'\n});\n\napp.start();\n`,
  'src/app.js': `export function createApp({ root, theme }) {\n  const state = { theme, ready: false };\n\n  function start() {\n    state.ready = true;\n    root.innerHTML = '<h1>Hello, Orbit.</h1>';\n  }\n\n  return { start };\n}\n`,
  'src/styles.css': `:root {\n  color-scheme: dark;\n}\n\nbody {\n  margin: 0;\n  background: #10141f;\n  color: #e8edf6;\n  font-family: Inter, sans-serif;\n}\n`,
  'package.json': `{\n  "name": "my-app",\n  "version": "0.1.0",\n  "scripts": {\n    "dev": "vite",\n    "build": "vite build"\n  }\n}\n`,
  'README.md': `# My App\n\nA small project opened in Orbit.\n`
};
let openFiles = ['src/index.js', 'src/app.js'];
let currentFile = 'src/index.js';
const editor = document.querySelector('#editor');
const highlight = document.querySelector('#highlight code');
const lineNumbers = document.querySelector('#lineNumbers');
const tabs = document.querySelector('#tabs');
const tree = document.querySelector('#fileTree');
const languageLabel = document.querySelector('#languageLabel');

const icon = p => p.endsWith('.js') ? ['file-js','JS'] : p.endsWith('.css') ? ['file-css','#'] : p.endsWith('.html') ? ['file-html','◇'] : p.endsWith('.json') ? ['file-json','{}'] : ['','•'];
function escapeHTML(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function syntax(code,path){
  let h=escapeHTML(code);
  h=h.replace(/(\/\/.*)/g,'<span class="tok-comment">$1</span>');
  h=h.replace(/(&quot;[^&]*?&quot;|'[^']*?'|`[^`]*?`)/g,'<span class="tok-string">$1</span>');
  h=h.replace(/\b(import|from|export|function|const|let|return|if|else|new|true|false)\b/g,'<span class="tok-key">$1</span>');
  h=h.replace(/\b(\d+)\b/g,'<span class="tok-num">$1</span>');
  h=h.replace(/\b(createApp|querySelector|start|innerHTML)\b/g,'<span class="tok-fn">$1</span>');
  if(path.endsWith('.css')) h=h.replace(/([\w-]+)(?=\s*:)/g,'<span class="tok-attr">$1</span>');
  return h || ' ';
}
function renderEditor(){const v=editor.value; highlight.innerHTML=syntax(v,currentFile); lineNumbers.innerHTML=Array.from({length:Math.max(1,v.split('\n').length)},(_,i)=>i+1).join('<br>'); const ext=currentFile.split('.').pop(); languageLabel.textContent=({js:'JavaScript',css:'CSS',json:'JSON',md:'Markdown'})[ext]||'Plain Text'; updateCursor();}
function renderTabs(){tabs.innerHTML=openFiles.map(path=>{const [c,i]=icon(path);return `<button class="tab ${path===currentFile?'active':''}" data-file="${path}"><span class="icon ${c}">${i}</span>${path.split('/').pop()}<span class="close" data-close="${path}">×</span></button>`}).join('');}
function folder(name,depth,open=true){return `<div class="tree-item folder-item" style="padding-left:${10+depth*14}px"><span class="arrow">${open?'⌄':'›'}</span><span class="icon folder">▰</span>${name}</div>`}
function renderTree(){let out=folder('src',0); Object.keys(files).filter(p=>p.startsWith('src/')).forEach(p=>{const [c,i]=icon(p);out+=`<div class="tree-item ${p===currentFile?'selected':''}" data-file="${p}" style="padding-left:38px"><span class="icon ${c}">${i}</span>${p.slice(4)}</div>`}); Object.keys(files).filter(p=>!p.startsWith('src/')).forEach(p=>{const[c,i]=icon(p);out+=`<div class="tree-item ${p===currentFile?'selected':''}" data-file="${p}" style="padding-left:12px"><span class="icon ${c}">${i}</span>${p}</div>`});tree.innerHTML=out;}
function switchFile(path){if(!files[path])return;if(!openFiles.includes(path))openFiles.push(path);currentFile=path;editor.value=files[path];renderEditor();renderTabs();renderTree();editor.focus();}
function updateCursor(){const before=editor.value.slice(0,editor.selectionStart);const row=before.split('\n').length;const col=before.length-before.lastIndexOf('\n');document.querySelector('#cursorPosition').textContent=`Ln ${row}, Col ${col}`;}
editor.addEventListener('input',()=>{files[currentFile]=editor.value;renderEditor();});editor.addEventListener('click',updateCursor);editor.addEventListener('keyup',updateCursor);editor.addEventListener('scroll',()=>{highlight.parentElement.scrollTop=editor.scrollTop;highlight.parentElement.scrollLeft=editor.scrollLeft;lineNumbers.scrollTop=editor.scrollTop;});
tabs.addEventListener('click',e=>{const x=e.target.closest('[data-close]');if(x){const f=x.dataset.close;openFiles=openFiles.filter(p=>p!==f);if(!openFiles.length)openFiles=[Object.keys(files)[0]];if(f===currentFile)switchFile(openFiles[0]);else renderTabs();return}const t=e.target.closest('[data-file]');if(t)switchFile(t.dataset.file)});tree.addEventListener('click',e=>{const t=e.target.closest('[data-file]');if(t)switchFile(t.dataset.file)});
document.querySelector('#newFile').addEventListener('click',()=>{const name=prompt('File name (for example src/new.js):','src/new.js');if(name&& !files[name]){files[name]='// New file\n';switchFile(name);toast(`Created ${name}`)}});
function setupResize(handle,target,axis){let start,size;handle.addEventListener('mousedown',e=>{start=axis==='x'?e.clientX:e.clientY;size=axis==='x'?target.offsetWidth:target.offsetHeight;handle.classList.add('dragging');document.body.style.cursor=axis==='x'?'col-resize':'row-resize';const move=e=>{const d=(axis==='x'?e.clientX:e.clientY)-start;target.style[axis==='x'?'width':'height']=Math.max(axis==='x'?160:90,size+d)+'px'};const up=()=>{handle.classList.remove('dragging');document.body.style.cursor='';window.removeEventListener('mousemove',move);window.removeEventListener('mouseup',up)};window.addEventListener('mousemove',move);window.addEventListener('mouseup',up)})}setupResize(document.querySelector('#sideResizer'),document.querySelector('#sidebar'),'x');setupResize(document.querySelector('#termResizer'),document.querySelector('#terminalPanel'),'y');
const output=document.querySelector('#terminalOutput');function print(msg,klass=''){const d=document.createElement('div');d.className='term-line '+klass;d.textContent=msg;output.append(d);output.scrollTop=output.scrollHeight}function command(cmd){const args=cmd.trim().split(/\s+/);if(!cmd.trim())return;print(`➜  ~/my-app  ${cmd}`,'term-command');const c=args[0];if(c==='help')print('Commands: help, ls, pwd, cat <file>, clear, npm run dev, npm run build, echo <text>');else if(c==='pwd')print('/home/orbit/my-app');else if(c==='ls')print('README.md   package.json   src/');else if(c==='cat'){const p=args[1];if(files[p])print(files[p]);else print(`cat: ${p||'missing operand'}: No such file or directory`,'term-error')}else if(c==='clear')output.innerHTML='';else if(c==='echo')print(args.slice(1).join(' '));else if(c==='npm'&&args.slice(1).join(' ')==='run dev'){print('> my-app@0.1.0 dev\n> vite\n\n  VITE v5.3.0  ready in 184 ms\n\n  ➜  Local:   http://localhost:5173/','term-muted')}else if(c==='npm'&&args.slice(1).join(' ')==='run build'){print('✓ built in 0.42s','term-muted')}else print(`orbit: command not found: ${c}`,'term-error')}
document.querySelector('#terminalForm').addEventListener('submit',e=>{e.preventDefault();const i=document.querySelector('#terminalInput');command(i.value);i.value=''});document.querySelector('#clearTerminal').addEventListener('click',()=>output.innerHTML='');
let toastTimer;function toast(message){const t=document.querySelector('#toast');t.textContent=message;t.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('show'),1800)}
renderTree();switchFile(currentFile);print('Orbit terminal — type help to see available commands.','term-muted');
