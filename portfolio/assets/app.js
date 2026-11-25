document.querySelectorAll('[data-year]').forEach(el=>el.textContent=new Date().getFullYear());
const navLinks=[...document.querySelectorAll('.nav-links a[href^="#"]')];
const sections=[...document.querySelectorAll('main section[id]')];
const observer=new IntersectionObserver(entries=>{entries.forEach(entry=>{if(entry.isIntersecting){navLinks.forEach(a=>a.classList.toggle('active',a.getAttribute('href')==='#'+entry.target.id))}})},{rootMargin:'-35% 0px -55% 0px'});
sections.forEach(section=>observer.observe(section));

const cards={
  skills:[
    {title:'数据产品',code:'BI',color:'#a9ecd3',desc:'用 Power Query、数据模型和 DAX，把分散数据变成可追踪的业务指标与决策页面。'},
    {title:'AI 工作流',code:'AI',color:'#c7b3ff',desc:'从真实流程摩擦出发，设计状态、事件、任务与审批机制，让 Agent 在清晰边界内工作。'},
    {title:'项目推进',code:'PM',color:'#ffd0df',desc:'拆解目标、识别风险、协调软硬件与业务团队，并用 Jira 等工具跟踪闭环。'},
    {title:'运筹与建模',code:'OR',color:'#fff0a8',desc:'将安全、能耗、优先级与时间窗等复杂约束转化为可计算和可验证的方案。'},
    {title:'技术理解',code:'DEV',color:'#b8ebf1',desc:'熟悉 Python、SQL、R、C++，能够与研发团队讨论数据结构、接口与实现边界。'}
  ],
  interests:[
    {title:'AI 工具探索',code:'01',color:'#c7b3ff',desc:'持续尝试把大模型、飞书智能体与 Claude Code 放进真实项目管理与个人效率场景。'},
    {title:'数据可视化',code:'02',color:'#a9ecd3',desc:'喜欢寻找最短的信息路径，让复杂状态和关键指标在一个页面里清楚呈现。'},
    {title:'系统思考',code:'03',color:'#fff0a8',desc:'对供应链、物流网络和复杂系统中的反馈关系、约束与权衡保持长期兴趣。'},
    {title:'校园协作',code:'04',color:'#ffd0df',desc:'学生会主席、班级团支书与研究生代表经历，让组织活动与团队协作成为日常。'}
  ]
};
let currentDeck='skills';let lastIndex=-1;
const drawn=document.querySelector('#drawnCard');
function drawCard(){
  const pool=cards[currentDeck];let i=Math.floor(Math.random()*pool.length);if(pool.length>1&&i===lastIndex)i=(i+1)%pool.length;lastIndex=i;const card=pool[i];
  drawn.classList.add('flipping');
  setTimeout(()=>{drawn.style.setProperty('--card-color',card.color);drawn.querySelector('.card-type').textContent=currentDeck==='skills'?'Skill card':'Interest card';drawn.querySelector('h3').textContent=card.title;drawn.querySelector('.card-meter strong').textContent=card.code;drawn.querySelector('p').textContent=card.desc;drawn.classList.remove('flipping')},260);
}
document.querySelectorAll('[data-deck]').forEach(button=>button.addEventListener('click',()=>{currentDeck=button.dataset.deck;lastIndex=-1;document.querySelectorAll('[data-deck]').forEach(b=>b.classList.toggle('active',b===button));document.querySelector('#deckHint').textContent='当前卡池：'+(currentDeck==='skills'?'技能卡':'兴趣卡');drawCard()}));
document.querySelector('#drawCard')?.addEventListener('click',drawCard);
document.querySelector('#copyEmail')?.addEventListener('click',async e=>{try{await navigator.clipboard.writeText('lichangxia411@163.com');e.currentTarget.textContent='已复制邮箱';setTimeout(()=>e.currentTarget.textContent='复制邮箱',1600)}catch{location.href='mailto:lichangxia411@163.com'}});

if(!matchMedia('(prefers-reduced-motion: reduce)').matches){
  const stage=document.querySelector('.portrait-stage');
  stage?.addEventListener('pointermove',e=>{const r=stage.getBoundingClientRect(),x=(e.clientX-r.left)/r.width-.5,y=(e.clientY-r.top)/r.height-.5;stage.querySelector('.portrait').style.transform=`translate(${x*9}px,${y*7}px)`;stage.querySelector('.portrait-aura').style.transform=`translate(${x*-12}px,${y*-8}px)`});
  stage?.addEventListener('pointerleave',()=>{stage.querySelector('.portrait').style.transform='';stage.querySelector('.portrait-aura').style.transform=''});
}
