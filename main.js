function showPage(id) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  var el = document.getElementById(id);
  if (el) el.classList.add('active');
}

document.getElementById('detectBtn')?.addEventListener('click', async () => {

  const status = document.getElementById('status');
  const resultCards = document.getElementById('resultCards');
  const resultCardsOuter = document.getElementById('resultCardsOuter');
  const progressBar = document.getElementById('progressBar');
  const progressBarContainer = document.getElementById('progressBarContainer');
  status.innerText = 'Detecting...';
  if(resultCards) resultCards.style.display = 'none';
  if(resultCardsOuter) resultCardsOuter.style.display = 'none';
  if(progressBar) progressBar.style.width = '0%';
  if(progressBarContainer) progressBarContainer.style.display = 'block';

  // Sử dụng SSE nếu có
  if (!!window.EventSource) {
    const evtSource = new EventSource("http://127.0.0.1:8000/ueba/detect/progress");
    let completed = false;
    evtSource.onmessage = async function(event) {
      let msg = JSON.parse(event.data);
      if (msg.progress !== undefined && progressBar) {
        progressBar.style.width = msg.progress + "%";
        status.innerText = msg.status || ("Progress: " + msg.progress + "%");
      }
      if (msg.done) {
        evtSource.close();
        completed = true;
        if(progressBarContainer) progressBarContainer.style.display = 'none';
        // Fetch kết quả như cũ
        const res = await fetch('http://127.0.0.1:8000/ueba/detect');
        const data = await res.json();
        // Tạo timestamp hiện tại
        const now = new Date();
        const timeString = now.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
        const dateString = now.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
        const timestamp = `${timeString} ${dateString}`;
        status.innerHTML = `Found ${data.anomalies} anomalies<br><small style="color:#000;font-size:0.9em;">Dữ liệu được cập nhật vào lúc ${timestamp}</small>`;
        // Hiển thị top 5 anomalies dạng card
        if (resultCards && resultCardsOuter) {
          resultCards.innerHTML = '';
          let sorted = [...data.data].sort((a,b)=>b.anomaly_score-a.anomaly_score);
          let top5 = sorted.slice(0,5);
          top5.forEach((row, idx) => {
            const card = document.createElement('div');
            card.className = idx === 0 ? 'result-card result-card-top1' : 'result-card result-card-top';
            card.innerHTML = `
              <div style="display:flex;align-items:center;gap:16px;">
                <img src="./assets/user${idx+1}.png" alt="${row.EmployeeID}" style="width:${idx===0?64:40}px;height:${idx===0?64:40}px;border-radius:50%;object-fit:cover;box-shadow:0 2px 8px #0001;" />
                <div>
                  <div style="font-weight:bold;font-size:${idx===0?'1.3rem':'1rem'};color:#000;">${row.EmployeeID}</div>
                  <div style="font-size:0.95em;color:#888;">Hour: ${row.hour_of_day}</div>
                </div>
                <div style="margin-left:auto;font-weight:bold;font-size:${idx===0?'2rem':'1.2rem'};color:${idx===0?'#e11d48':'#0284c7'};">${row.anomaly_score.toFixed(3)}</div>
              </div>
            `;
            resultCards.appendChild(card);
          });
          if(top5.length>0) {
            resultCards.style.display = 'flex';
            resultCardsOuter.style.display = 'flex';
          }
        }
      }
    };
    evtSource.onerror = function() {
      evtSource.close();
      if(progressBarContainer) progressBarContainer.style.display = 'none';
      status.innerText = "Failed to get progress";
    };
  } else {
    // Fallback nếu không có SSE
    if(progressBarContainer) progressBarContainer.style.display = 'none';
    const res = await fetch('http://127.0.0.1:8000/ueba/detect');
    const data = await res.json();
    // Tạo timestamp hiện tại
    const now = new Date();
    const timeString = now.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
    const dateString = now.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
    const timestamp = `${timeString} ${dateString}`;
    status.innerHTML = `Found ${data.anomalies} anomalies<br><small style="color:#888;font-size:0.9em;">Dữ liệu được cập nhật vào lúc ${timestamp}</small>`;
    // Hiển thị top 5 anomalies dạng card
    if (resultCards && resultCardsOuter) {
      resultCards.innerHTML = '';
      let sorted = [...data.data].sort((a,b)=>b.anomaly_score-a.anomaly_score);
      let top5 = sorted.slice(0,5);
      top5.forEach((row, idx) => {
        const card = document.createElement('div');
        card.className = idx === 0 ? 'result-card result-card-top1' : 'result-card result-card-top';
        card.innerHTML = `
          <div style="display:flex;align-items:center;gap:16px;">
            <img src="./assets/user${idx+1}.png" alt="${row.EmployeeID}" style="width:${idx===0?64:40}px;height:${idx===0?64:40}px;border-radius:50%;object-fit:cover;box-shadow:0 2px 8px #0001;" />
            <div>
              <div style="font-weight:bold;font-size:${idx===0?'1.3rem':'1rem'};color:#000;">${row.EmployeeID}</div>
              <div style="font-size:0.95em;color:#888;">Hour: ${row.hour_of_day}</div>
            </div>
            <div style="margin-left:auto;font-weight:bold;font-size:${idx===0?'2rem':'1.2rem'};color:${idx===0?'#e11d48':'#0284c7'};">${row.anomaly_score.toFixed(3)}</div>
          </div>
        `;
        resultCards.appendChild(card);
      });
      if(top5.length>0) {
        resultCards.style.display = 'flex';
        resultCardsOuter.style.display = 'flex';
      }
    }
  }
});


// Charst rendering
document.addEventListener('DOMContentLoaded', function() {
  var ctx = document.getElementById('userQueryChart');
  if (ctx && ctx.getContext) {
    var c = ctx.getContext('2d');
    // Demo data
    var users = ['A', 'B', 'C', 'D', 'E','F','G','H','I','J'];
    var values = [24, 19, 15, 9, 5,11,4,8,6,3];
    var colors = ['#38bdf8'];
    var max = Math.max(...values);
    var w = ctx.width, h = ctx.height;
    var barW = 32, gap = 18;
    // Clear
    c.clearRect(0,0,w,h);
    // Draw axis
    c.strokeStyle = '#bac7db';
    c.lineWidth = 1;
    c.beginPath();
    c.moveTo(30, h-28); c.lineTo(w-10, h-28); c.stroke();
    // Draw bars
    for(let i=0;i<values.length;i++){
      var x = 38 + i*(barW+gap);
      var y = h-28;
      var barH = Math.round((values[i]/max)*(h-48));
      c.fillStyle = colors[0];
      c.fillRect(x, y-barH, barW, barH);
      // Value on top
      c.fillStyle = '#222';
      c.font = 'bold 14px Helve, Arial, sans-serif';
      c.textAlign = 'center';
      c.fillText(values[i], x+barW/2, y-barH-8);
      // User label
      c.font = 'bold 13px Helve, Arial, sans-serif';
      c.fillText(users[i], x+barW/2, h-10);
    }
  }
});
async function runDetection() {
    const status = document.getElementById("status");
    const summary = document.getElementById("summary");
    const table = document.getElementById("resultTable");
    const tbody = table.querySelector("tbody");
    const progressBar = document.getElementById("progressBar");
    const progressBarContainer = document.getElementById("progressBarContainer");

    status.innerText = "Running ML detection...";
    summary.innerText = "";
    tbody.innerHTML = "";
    table.style.display = "none";
    progressBar.style.width = "0%";
    progressBarContainer.style.display = "block";

    // Nếu server hỗ trợ SSE progress
    let completed = false;
    try {
        if (!!window.EventSource) {
            const evtSource = new EventSource("http://127.0.0.1:8000/ueba/detect/progress");
            evtSource.onmessage = function(event) {
                let msg = JSON.parse(event.data);
                if (msg.progress !== undefined) {
                    progressBar.style.width = msg.progress + "%";
                    status.innerText = msg.status || ("Progress: " + msg.progress + "%");
                }
                if (msg.done) {
                    evtSource.close();
                    completed = true;
                    fetchResult();
                }
            };
            evtSource.onerror = function() {
                evtSource.close();
                if (!completed) {
                    status.innerText = "Failed to get progress";
                    progressBarContainer.style.display = "none";
                }
            };
        } else {
            // Fallback nếu không có SSE
            await fetchResult();
        }
    } catch (err) {
        status.innerText = "Failed to call API";
        progressBarContainer.style.display = "none";
        console.error(err);
    }
}
