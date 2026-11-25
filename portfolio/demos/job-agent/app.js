const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const canvas = $('#space');
const ctx = canvas.getContext('2d');
let particles = [];

function resizeSpace() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = innerWidth * dpr;
  canvas.height = innerHeight * dpr;
  canvas.style.width = `${innerWidth}px`;
  canvas.style.height = `${innerHeight}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const amount = Math.min(90, Math.floor(innerWidth / 18));
  particles = Array.from({ length: amount }, () => ({
    x: Math.random() * innerWidth,
    y: Math.random() * innerHeight,
    z: Math.random() * 1 + .2,
    vx: (Math.random() - .5) * .12,
    vy: (Math.random() - .5) * .12
  }));
}

function drawSpace() {
  ctx.clearRect(0, 0, innerWidth, innerHeight);
  particles.forEach((p, i) => {
    p.x += p.vx * p.z; p.y += p.vy * p.z;
    if (p.x < -20) p.x = innerWidth + 20;
    if (p.x > innerWidth + 20) p.x = -20;
    if (p.y < -20) p.y = innerHeight + 20;
    if (p.y > innerHeight + 20) p.y = -20;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.z * 1.1, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(145, 177, 255, ${.18 + p.z * .2})`;
    ctx.fill();
    particles.slice(i + 1, i + 5).forEach(q => {
      const d = Math.hypot(p.x - q.x, p.y - q.y);
      if (d < 120) {
        ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y);
        ctx.strokeStyle = `rgba(90, 128, 205, ${(1 - d / 120) * .09})`; ctx.stroke();
      }
    });
  });
  requestAnimationFrame(drawSpace);
}

resizeSpace(); drawSpace();
window.addEventListener('resize', resizeSpace);

document.addEventListener('pointermove', e => {
  document.documentElement.style.setProperty('--mx', `${e.clientX}px`);
  document.documentElement.style.setProperty('--my', `${e.clientY}px`);
  const scene = $('#heroScene');
  if (scene && innerWidth > 720) {
    const rx = (e.clientY / innerHeight - .5) * -8;
    const ry = (e.clientX / innerWidth - .5) * 10;
    scene.style.transform = `rotateX(${rx}deg) rotateY(${ry}deg)`;
  }
});

const observer = new IntersectionObserver(entries => {
  entries.forEach(entry => entry.isIntersecting && entry.target.classList.add('visible'));
}, { threshold: .12 });
$$('.reveal').forEach(el => observer.observe(el));

$$('.tilt').forEach(card => {
  card.addEventListener('pointermove', e => {
    if (innerWidth < 720) return;
    const r = card.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - .5;
    const y = (e.clientY - r.top) / r.height - .5;
    card.style.transform = `rotateX(${y * -8}deg) rotateY(${x * 10}deg) translateY(-5px)`;
  });
  card.addEventListener('pointerleave', () => card.style.transform = '');
});

const roles = {
  'AI 产品经理': [
    ['星云智能', 'AI 产品经理实习生', 91, '强烈推荐', '上海 · 最近 2 天'],
    ['矩阵科技', '大模型产品实习生', 78, '建议考虑', '上海 · 最近 4 天'],
    ['远景数据', '产品运营实习生', 63, '谨慎评估', '远程 · 最近 6 天']
  ],
  '数据产品经理': [
    ['示例云科', '数据产品经理实习生', 88, '强烈推荐', '深圳 · 最近 1 天'],
    ['极光分析', 'BI 产品实习生', 81, '强烈推荐', '深圳 · 最近 5 天'],
    ['蓝图网络', '数据运营实习生', 67, '建议考虑', '远程 · 最近 3 天']
  ],
  '策略产品经理': [
    ['原点科技', '策略产品实习生', 86, '强烈推荐', '北京 · 最近 2 天'],
    ['量子互联', '商业策略实习生', 74, '建议考虑', '北京 · 最近 4 天'],
    ['示例出行', '用户增长实习生', 61, '谨慎评估', '北京 · 最近 7 天']
  ]
};

const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
let running = false;

async function runDemo() {
  if (running) return;
  running = true;
  const button = $('#runDemo');
  const label = $('.run-copy', button);
  const indicator = $('.live-indicator');
  const state = $('#runState');
  const resultStack = $('#resultStack');
  const steps = $$('.agent-step');
  button.disabled = true; label.textContent = 'Agent 正在执行';
  indicator.classList.add('running'); state.textContent = 'RUNNING';
  resultStack.innerHTML = '<div class="empty-state"><div class="scan-cube"><span></span><span></span><span></span></div><strong>正在分析公开岗位</strong><p>保留来源 · 校验结构 · 建立证据</p></div>';
  steps.forEach(step => { step.className = 'agent-step'; $('b', step).textContent = 'WAIT'; });

  for (let i = 0; i < steps.length; i++) {
    steps[i].classList.add('processing'); $('b', steps[i]).textContent = 'RUN';
    await wait(i === 1 ? 820 : 610);
    steps[i].classList.remove('processing'); steps[i].classList.add('done'); $('b', steps[i]).textContent = 'DONE';
  }

  const selectedRole = $('#roleSelect').value;
  const selectedCity = $('#citySelect').value;
  const data = roles[selectedRole];
  resultStack.innerHTML = `
    <div class="job-results">
      <div class="result-title"><strong>推荐岗位 · ${selectedRole}</strong><span>3 LEADS / ${selectedCity}</span></div>
      ${data.map(([company, role, score, status, meta]) => `
        <article class="job-card">
          <div class="job-head"><strong>${company} · ${role}</strong><span>${score}</span></div>
          <div class="job-meta"><span>${meta.replace(/上海|深圳|北京/, selectedCity)}</span><span>来源已验证</span></div>
          <div class="score-bar"><i style="width:${score}%"></i></div>
          <div class="job-foot"><b>${status}</b><span>Evidence 6 · Risk 1</span></div>
        </article>`).join('')}
      <div class="approval-banner"><span>高匹配岗位已进入申请材料审批队列</span><b>WAITING FOR HUMAN</b></div>
    </div>`;
  state.textContent = 'COMPLETED'; indicator.classList.remove('running');
  label.textContent = '重新运行模拟'; button.disabled = false; running = false;
}

$('#runDemo').addEventListener('click', runDemo);
