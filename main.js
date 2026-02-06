// Vẽ chart anomaly score vào card
async function renderAnomalyScoreChart() {
  const canvas = document.getElementById('anomalyScoreChart');
  const tooltip = document.getElementById('anomalyScoreTooltip');
  if (!canvas) return;
  // Hiệu ứng loading cho chart (thêm logo)
  let chartLoading = document.getElementById('ml-detect-chart-loading');
  if (!chartLoading) {
    chartLoading = document.createElement('div');
    chartLoading.id = 'ml-detect-chart-loading';
    chartLoading.style = 'position:absolute;top:0;left:0;width:100%;height:100%;background:transparent;display:flex;align-items:center;justify-content:center;z-index:10;';
    chartLoading.innerHTML = `
      <div style="display:flex;flex-direction:column;align-items:center;gap:10px;">
        <img src='./assets/UEBA_coporation_logo.png' alt='logo' style='width:60px;height:60px;object-fit:contain;filter:drop-shadow(0 2px 6px #0002);'>
        <div class="loader"></div>
      </div>
    `;
    canvas.parentElement.appendChild(chartLoading);
  } else {
    chartLoading.style.display = 'flex';
  }
  // Lấy kích thước card, scale cho retina/hiDPI
  const parent = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = parent.offsetWidth * dpr;
  canvas.height = parent.offsetHeight * dpr;
  canvas.style.width = parent.offsetWidth + 'px';
  canvas.style.height = parent.offsetHeight + 'px';
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, parent.offsetWidth, parent.offsetHeight);
  // Fetch data
  try {
    const res = await fetch('http://127.0.0.1:8000/ueba/scorechart');
    const data = await res.json();
    const points = data.data || [];
    const threshold = data.threshold ?? 0.5;
    if (!points.length) {
      if (chartLoading) chartLoading.style.display = 'none';
      return;
    }
    // Ẩn loading khi đã có dữ liệu
    if (chartLoading) chartLoading.style.display = 'none';
    // Scatter plot anomaly score theo index (hoặc thời gian)
    const w = parent.offsetWidth, h = parent.offsetHeight;
    const padding = 70;
    const r = 7; // radius điểm nét hơn
    const minScore = Math.min(...points.map(p=>p.anomaly_score));
    const maxScore = Math.max(...points.map(p=>p.anomaly_score));
    // Trục Y
    ctx.strokeStyle = '#bac7db';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(padding, padding);
    ctx.lineTo(padding, h-padding);
    ctx.lineTo(w-padding, h-padding);
    ctx.stroke();
    // Nhãn min/max
    ctx.fillStyle = '#222';
    ctx.font = 'bold 14px Arial, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(minScore.toFixed(2), padding-4, h-padding);
    ctx.fillText(maxScore.toFixed(2), padding-4, padding+8);
    ctx.textAlign = 'center';
    ctx.fillText('Anomaly Score', w/2, h-6);
    // Vẽ threshold
    if (threshold !== undefined) {
      const yThresh = h-padding-((threshold-minScore)/(maxScore-minScore+1e-8))*(h-2*padding);
      ctx.strokeStyle = '#e1851d';
      ctx.setLineDash([6,4]);
      ctx.beginPath();
      ctx.moveTo(padding, yThresh);
      ctx.lineTo(w-padding, yThresh);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.font = 'bold 12px Arial, sans-serif';
      ctx.fillStyle = '#e11d48';
      ctx.textAlign = 'left';
      ctx.fillText('Threshold', w-padding+6, yThresh+4);
    }
    // Vẽ các điểm
    const step = (w-2*padding)/(points.length-1);
    // Lưu lại vị trí các điểm để hover
    window.anomalyScorePoints = [];
    for(let i=0;i<points.length;i++){
      const p = points[i];
      const x = padding + i*step;
      const y = h-padding-((p.anomaly_score-minScore)/(maxScore-minScore+1e-8))*(h-2*padding);
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2*Math.PI);
      ctx.fillStyle = p.is_anomaly ? '#f44949' : '#54c5f5';
      ctx.globalAlpha = p.is_anomaly ? 0.95 : 0.7;
      ctx.fill();
      ctx.globalAlpha = 1.0;
      window.anomalyScorePoints.push({x, y, r, ...p});
    }
    // Chú thích dưới chart
    ctx.font = '15px Helve, sans-serif';
    ctx.fillStyle = '#444';
    ctx.textAlign = 'left';
    ctx.fillText('● Normal', padding, h-padding+22);
    ctx.fillStyle = '#e11d48';
    ctx.fillText('● Anomaly (outlier)', padding+110, h-padding+22);
    ctx.fillStyle = '#444';
    ctx.fillText('Red points indicate anomalies, closer to 0 is more dangerous.', padding, h-padding+40);
    // Tooltip hover
    let lastHoverIdx = -1;
    canvas.onmousemove = function(e) {
      if (!window.anomalyScorePoints) return;
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      let found = null;
      let foundIdx = -1;
      for (let i=0;i<window.anomalyScorePoints.length;i++) {
        const pt = window.anomalyScorePoints[i];
        if (pt.x > 0 && pt.y > 0 && pt.x < canvas.width && pt.y < canvas.height && typeof pt.anomaly_score === 'number') {
          if (Math.abs(mx-pt.x) <= r+4 && Math.abs(my-pt.y) <= r+4) {
            found = pt; foundIdx = i; break;
          }
        }
      }
      if (found) {
        // Vẽ lại dot hover viền trắng
        ctx.save();
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        // Vẽ lại toàn bộ chart để xóa viền cũ
        ctx.clearRect(0, 0, parent.offsetWidth, parent.offsetHeight);
        // ...vẽ lại chart như ban đầu...
        // Trục Y
        ctx.strokeStyle = '#bac7db';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(padding, padding);
        ctx.lineTo(padding, h-padding);
        ctx.lineTo(w-padding, h-padding);
        ctx.stroke();
        // Nhãn min/max
        ctx.fillStyle = '#222';
        ctx.font = 'bold 14px Arial, sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(minScore.toFixed(2), padding-4, h-padding);
        ctx.fillText(maxScore.toFixed(2), padding-4, padding+8);
        ctx.textAlign = 'center';
        ctx.fillText('Anomaly Score', w/2, h-6);
        // Vẽ threshold
        if (threshold !== undefined) {
          const yThresh = h-padding-((threshold-minScore)/(maxScore-minScore+1e-8))*(h-2*padding);
          ctx.strokeStyle = '#e1851d';
          ctx.setLineDash([6,4]);
          ctx.beginPath();
          ctx.moveTo(padding, yThresh);
          ctx.lineTo(w-padding, yThresh);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.font = 'bold 12px Arial, sans-serif';
          ctx.fillStyle = '#e11d48';
          ctx.textAlign = 'left';
          ctx.fillText('Threshold', w-padding+6, yThresh+4);
        }
        // Vẽ lại các dot
        for(let i=0;i<window.anomalyScorePoints.length;i++){
          const pt = window.anomalyScorePoints[i];
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, r, 0, 2*Math.PI);
          ctx.fillStyle = pt.is_anomaly ? '#f44949' : '#54c5f5';
          ctx.globalAlpha = pt.is_anomaly ? 0.95 : 0.7;
          ctx.fill();
          ctx.globalAlpha = 1.0;
          // Nếu là dot hover thì vẽ viền trắng
          if (i === foundIdx) {
            ctx.lineWidth = 3.5;
            ctx.strokeStyle = '#000000';
            ctx.stroke();
          }
        }
        // Chú thích dưới chart
        ctx.font = '15px Helve, sans-serif';
        ctx.fillStyle = '#444';
        ctx.textAlign = 'left';
        ctx.fillText('● Normal', padding, h-padding+22);
        ctx.fillStyle = '#e11d48';
        ctx.fillText('● Anomaly (outlier)', padding+110, h-padding+22);
        ctx.fillStyle = '#444';
        ctx.fillText('Red points indicate anomalies, closer to 0 is more dangerous.', padding, h-padding+40);
        ctx.restore();
        // Tooltip
        if (tooltip) {
          tooltip.style.display = 'block';
          // // Tìm đúng trường QueryLogID, kiểm tra mọi trường hợp
          // let logid = '';
          if ('QueryLogID' in found) logid = found.QueryLogID;
          else if ('queryLogID' in found) logid = found.queryLogID;
          else if ('querylogid' in found) logid = found.querylogid;
          else if ('querylogid_col' in found) logid = found.query_log_id;
          else {
            // Tìm trường có tên gần giống
            for (const k in found) {
              if (k.toLowerCase().includes('logid')) { logid = found[k]; break; }
            }
          }
          tooltip.innerHTML = `<b style=\"font-size:0.8rem\">EmployeeID:</b> ${found.employee_id}<br><b style=\"font-size:0.8rem\">Score:</b> ${found.anomaly_score.toFixed(3)}<br><b style=\"font-size:0.8rem\">Risk:</b> ${found.risk_level}<br><b style=\"font-size:0.8rem\">Time:</b> ${found.query_time}<br><b style=\"font-size:0.8rem\">LogID:</b> ${logid ?? '--'}<br><b style=\"font-size:0.8rem\">Context:</b> ${found.context}`;
          const pad = 12;
          const tw = tooltip.offsetWidth || 220;
          const th = tooltip.offsetHeight || 120;
          let left = e.clientX + pad;
          let top = e.clientY - 8;
          if (left + tw > window.innerWidth - 8) left = e.clientX - tw - pad;
          if (left < 0) left = 0;
          if (top + th > window.innerHeight - 8) top = window.innerHeight - th - 8;
          if (top < 0) top = 0;
          tooltip.style.left = left + 'px';
          tooltip.style.top = top + 'px';
        }
        canvas.style.cursor = 'pointer';
        lastHoverIdx = foundIdx;
      } else {
        if (tooltip) tooltip.style.display = 'none';
        canvas.style.cursor = '';
        // Nếu vừa rời khỏi dot thì vẽ lại chart không viền
        if (lastHoverIdx !== -1) {
          ctx.save();
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          ctx.clearRect(0, 0, parent.offsetWidth, parent.offsetHeight);
          // ...vẽ lại chart như ban đầu...
          // Trục Y
          ctx.strokeStyle = '#bac7db';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(padding, padding);
          ctx.lineTo(padding, h-padding);
          ctx.lineTo(w-padding, h-padding);
          ctx.stroke();
          // Nhãn min/max
          ctx.fillStyle = '#222';
          ctx.font = 'bold 14px Arial, sans-serif';
          ctx.textAlign = 'right';
          ctx.fillText(minScore.toFixed(2), padding-4, h-padding);
          ctx.fillText(maxScore.toFixed(2), padding-4, padding+8);
          ctx.textAlign = 'center';
          ctx.fillText('Anomaly Score', w/2, h-6);
          // Vẽ threshold
          if (threshold !== undefined) {
            const yThresh = h-padding-((threshold-minScore)/(maxScore-minScore+1e-8))*(h-2*padding);
            ctx.strokeStyle = '#e1851d';
            ctx.setLineDash([6,4]);
            ctx.beginPath();
            ctx.moveTo(padding, yThresh);
            ctx.lineTo(w-padding, yThresh);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.font = 'bold 12px Arial, sans-serif';
            ctx.fillStyle = '#e11d48';
            ctx.textAlign = 'left';
            ctx.fillText('Threshold', w-padding+6, yThresh+4);
          }
          // Vẽ lại các dot
          for(let i=0;i<window.anomalyScorePoints.length;i++){
            const pt = window.anomalyScorePoints[i];
            ctx.beginPath();
            ctx.arc(pt.x, pt.y, r, 0, 2*Math.PI);
            ctx.fillStyle = pt.is_anomaly ? '#f44949' : '#54c5f5';
            ctx.globalAlpha = pt.is_anomaly ? 0.95 : 0.7;
            ctx.fill();
            ctx.globalAlpha = 1.0;
          }
          // Chú thích dưới chart
          ctx.font = '15px Helve, sans-serif';
          ctx.fillStyle = '#444';
          ctx.textAlign = 'left';
          ctx.fillText('● Normal', padding, h-padding+22);
          ctx.fillStyle = '#e11d48';
          ctx.fillText('● Anomaly (outlier)', padding+110, h-padding+22);
          ctx.fillStyle = '#444';
          ctx.fillText('Red points indicate anomalies, closer to 0 is more dangerous.', padding, h-padding+40);
          ctx.restore();
          lastHoverIdx = -1;
        }
      }
    };
    canvas.onmouseleave = function() {
      if (tooltip) tooltip.style.display = 'none';
      canvas.style.cursor = '';
    };
  } catch(e) {
    // Không vẽ gì nếu lỗi
    console.error('Chart error:', e);
  }
}
function showPage(id, event) {
  if (event) event.preventDefault();
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
  if (id === 'detect') {
    renderMLDetect_DetectSection();
    setTimeout(renderAnomalyScoreChart, 300); // Đảm bảo DOM đã render xong
  }
}
// Render dữ liệu anomaly từ /ueba/detect vào bảng list
// Biến toàn cục lưu detect JSON mới nhất
window.lastDetectJson = null;
async function renderMLDetect_DetectSection() {
  const overview = document.getElementById('ml-detect-overview');
  const anomalyTable = document.getElementById('ml-anomaly-table');
  const exportBtn = document.querySelector('.btn-export');
  if (exportBtn) {
    exportBtn.disabled = true;
    exportBtn.style.background = '#a3a3a3';
    exportBtn.style.color = '#fff';
    exportBtn.style.cursor = 'not-allowed';
  }
    if (overview) overview.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;min-height:180px;gap:10px;">
      <img src='./assets/UEBA_coporation_logo.png' alt='logo' style='width:60px;height:60px;object-fit:contain;filter:drop-shadow(0 2px 6px #0002);'>
      <div class="loader"></div>
    </div>`;
    if (anomalyTable) anomalyTable.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:180px;gap:10px;">
      <img src='./assets/UEBA_coporation_logo.png' alt='logo' style='width:60px;height:60px;object-fit:contain;filter:drop-shadow(0 2px 6px #0002);'>
      <div class="loader"></div>
    </div>`;
  try {
    const res = await fetch('http://127.0.0.1:8000/ueba/detect');
    const data = await res.json();
    window.lastDetectJson = data;
    if (exportBtn) {
      exportBtn.disabled = false;
      exportBtn.style.background = '';
      exportBtn.style.color = '';
      exportBtn.style.cursor = '';
    }
    // Render tổng quan sinh động hơn
    if (overview) {
      const anomalyRate = data.total_rows ? ((data.anomalies/data.total_rows)*100) : 0;
      let badge = '';
      let badgeColor = '';
      if (anomalyRate < 5) { badge = 'SAFE'; badgeColor = '#22c55e'; }
      else if (anomalyRate < 15) { badge = 'WARNING'; badgeColor = '#facc15'; }
      else { badge = 'DANGER'; badgeColor = '#ef4444'; }
      overview.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
          <img src='./assets/overview.png' alt='shield' style='width:32px;height:32px;object-fit:contain;filter:drop-shadow(0 2px 6px #0002);'>
          <span style="padding:4px 14px;border-radius:16px;font-weight:bold;font-size:0.95em;background:${badgeColor};color:#fff;box-shadow:0 2px 8px #0001;">${badge}</span>
        </div>
        <div style="font-size: 0.8rem;">Total Records: <b style="font-size: 0.8rem;">${data.total_rows ?? '--'}</b></div>
        <div style="font-size: 0.8rem;">Anomalies Detected: <b style="font-size: 0.8rem;">${data.anomalies ?? '--'}</b></div>
        <div style="font-size: 0.8rem;">Anomaly Rate: <b style="font-size: 0.8rem;">${anomalyRate.toFixed(2)}%</b></div>
        <div style="margin:12px 0 8px 0;width:100%;height:10px;background:#e0e7ef;border-radius:6px;overflow:hidden;">
          <div style="height:100%;width:${anomalyRate.toFixed(2)}%;background:${badgeColor};transition:width 0.6s;"></div>
        </div>
        <div style="font-size:0.9em;color:#1e293b;opacity:0.95;margin-top:12px;font-style:italic;min-height:32px;">
          <span style="font-size:1.1em;">⚠️</span> ${data.context}
        </div>
      `;
    }
    // Render bảng anomaly
    if (anomalyTable) {
      anomalyTable.innerHTML = `
        <table style="width:100%;border-collapse:collapse;">
          <thead>
            <tr>
              <th style="font-size: 0.8rem;">EmployeeID</th>
              <th style="font-size: 0.8rem;">QueryTime</th>
              <th style="font-size: 0.8rem;">LogID</th>
              <th style="font-size: 0.8rem;">Anomaly Score</th>
              <th style="font-size: 0.8rem;">RowsExamined</th>
              <th style="font-size: 0.8rem;">RowsReturned</th>
              <th style="font-size: 0.8rem;">ExecutionTime</th>
              <th style="font-size: 0.8rem;">QueryLength</th>
              <th style="font-size: 0.8rem;">IsSensitive</th>
              <th style="font-size: 0.8rem;">Type</th>
            </tr>
          </thead>
          <tbody>
            ${data.data.map(row => {
              let logid = '';
              if (row.QueryLogID !== undefined) logid = row.QueryLogID;
              else if (row.queryLogID !== undefined) logid = row.queryLogID;
              else if (row.querylogid !== undefined) logid = row.querylogid;
              else if (row.query_log_id !== undefined) logid = row.query_log_id;
              else {
                for (const k in row) {
                  if (k.toLowerCase().includes('logid')) { logid = row[k]; break; }
                }
              }
              return `
              <tr>
                <td style="font-size: 0.8rem;">${row.EmployeeID ?? '--'}</td>
                <td style="font-size: 0.8rem;">${row.QueryTime ?? '--'}</td>
                <td style="font-size: 0.8rem;">${logid ?? '--'}</td>
                <td style="font-size: 0.8rem;">${row.anomaly_score !== undefined ? Number(row.anomaly_score).toFixed(3) : '--'}</td>
                <td style="font-size: 0.8rem;">${row.RowsExamined !== undefined ? (Number.isInteger(Number(row.RowsExamined)) ? Number(row.RowsExamined) : Number(row.RowsExamined).toFixed(3)) : '--'}</td>
                <td style="font-size: 0.8rem;">${row.RowsReturned !== undefined ? (Number.isInteger(Number(row.RowsReturned)) ? Number(row.RowsReturned) : Number(row.RowsReturned).toFixed(3)) : '--'}</td>
                <td style="font-size: 0.8rem;">${row.ExecutionTime !== undefined ? (Number.isInteger(Number(row.ExecutionTime)) ? Number(row.ExecutionTime) : Number(row.ExecutionTime).toFixed(3)) : '--'}</td>
                <td style="font-size: 0.8rem;">${row.QueryLength !== undefined ? (Number.isInteger(Number(row.QueryLength)) ? Number(row.QueryLength) : Number(row.QueryLength).toFixed(3)) : '--'}</td>
                <td style="font-size: 0.8rem;">${row.IsSensitive !== undefined ? (Number.isInteger(Number(row.IsSensitive)) ? Number(row.IsSensitive) : Number(row.IsSensitive).toFixed(3)) : '--'}</td>
                <td style="font-size: 0.8rem;">${row.query_type !== undefined ? (Number.isInteger(Number(row.query_type)) ? Number(row.query_type) : Number(row.query_type).toFixed(3)) : '--'}</td>
              </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      `;
    }
  } catch (e) {
    if (overview) overview.innerHTML = '<span style="color:red;">Lỗi khi tải dữ liệu ML</span>';
    if (anomalyTable) anomalyTable.innerHTML = '';
    console.error('ML Detect error:', e);
  }
}

// Hiệu ứng typing chỉ chạy một lần, không bị chồng khi click nhanh
window.typeTextTimeouts = window.typeTextTimeouts || new WeakMap();
const typeTextTimeouts = window.typeTextTimeouts;
function typeText(element, text, speed = 4) {
  // Hủy các timeout typing cũ nếu có
  if (typeTextTimeouts.has(element)) {
    typeTextTimeouts.get(element).forEach(clearTimeout);
  }
  element.innerHTML = '';
  let i = 0;
  let timeouts = [];
  function typing() {
    if (i < text.length) {
      element.innerHTML += text.charAt(i);
      i++;
      timeouts.push(setTimeout(typing, speed));
    }
  }
  typing();
  typeTextTimeouts.set(element, timeouts);
}

// --- Refresh Button Handler for Detect Page ---
document.addEventListener('DOMContentLoaded', function() {
  const refreshBtn = document.querySelector('.btn-refresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', function() {
      // Hủy mọi tiến trình export nếu có
      const exportBtn = document.querySelector('.btn-export');
      if (exportBtn) {
        // Hủy timeout download nếu có
        if (window.exportDownloadTimeout) {
          clearTimeout(window.exportDownloadTimeout);
          window.exportDownloadTimeout = null;
        }
        // Reset trạng thái exportBtn
        exportBtn.innerHTML = exportBtn.dataset.originalText || 'Export';
        exportBtn.disabled = true;
        exportBtn.style.background = '#a3a3a3';
        exportBtn.style.color = '#fff';
        exportBtn.style.cursor = 'not-allowed';
        // Hủy blob/url
        window.exportDownloadUrl = null;
        window.exportDownloadBlob = null;
        window.exportDownloadReady = false;
          // Reset biến closure handler nếu có
          if (typeof window.resetExportButtonState === 'function') {
            window.resetExportButtonState();
          }
      }
      // Only refresh if Detect page is visible
      const detectPage = document.getElementById('detect');
      if (detectPage && detectPage.classList.contains('active')) {
        // Call the main render functions for Detect page
        if (typeof renderMLDetect_Overview === 'function') renderMLDetect_Overview();
        if (typeof renderAnomalyScoreChart === 'function') renderAnomalyScoreChart();
        if (typeof renderMLDetect_DetectSection === 'function') renderMLDetect_DetectSection();
      }
    });
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

  // --- Export PDF Button Handler ---
  const exportBtn = document.querySelector('.btn-export');
  if (exportBtn) {
    let originalText = exportBtn.textContent;
    exportBtn.dataset.originalText = originalText;
    let downloadUrl = null;
    let downloadBlob = null;
    let downloadReady = false;
    // Lưu vào window để có thể hủy khi refresh
    window.exportDownloadUrl = null;
    window.exportDownloadBlob = null;
    window.exportDownloadReady = false;
      // Hàm reset closure biến, để gọi từ refresh
      window.resetExportButtonState = function() {
        downloadUrl = null;
        downloadBlob = null;
        downloadReady = false;
      };
    exportBtn.addEventListener('click', async function handler(e) {
      if (e) { e.preventDefault(); e.stopPropagation && e.stopPropagation(); }
      if (exportBtn.disabled) return;
      // Nếu đang ở trạng thái Download, thì click này là để tải file
      if (downloadReady && downloadUrl && downloadBlob) {
        // Tải file
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = 'ueba_anomaly_report.pdf';
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
          window.URL.revokeObjectURL(downloadUrl);
          document.body.removeChild(a);
        }, 100);
        exportBtn.innerHTML = '<span style="color:#ffffff;font-weight:bold;">Downloaded</span>';
        exportBtn.disabled = true;
        setTimeout(() => {
          exportBtn.innerHTML = originalText;
          exportBtn.disabled = false;
          downloadUrl = null;
          downloadBlob = null;
          downloadReady = false;
        }, 1800);
        return;
      }
      // Nếu chưa có file, thực hiện export
      exportBtn.disabled = true;
      originalText = originalText || exportBtn.textContent;
      exportBtn.innerHTML = '<span class="loader" style="margin-right:8px;width:16px;height:16px;border-width:2px;"></span>Loading...';
      try {
        // Lấy JSON detect đã lưu trước đó
        const detectJson = window.lastDetectJson || {};
        const res = await fetch('http://127.0.0.1:8000/ueba/export-pdf', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(detectJson)
        });
        if (!res.ok) throw new Error('Export failed');
        downloadBlob = await res.blob();
        downloadUrl = window.URL.createObjectURL(downloadBlob);
        downloadReady = true;
        exportBtn.innerHTML = '<span style="color:#ffffff;font-weight:bold;">Download</span>';
        exportBtn.disabled = false;
        // Lưu vào window để có thể hủy khi refresh
        window.exportDownloadUrl = downloadUrl;
        window.exportDownloadBlob = downloadBlob;
        window.exportDownloadReady = downloadReady;
        // Nếu người dùng không click Download trong 7 giây, revert về Export
        window.exportDownloadTimeout = setTimeout(() => {
          if (window.exportDownloadReady) {
            exportBtn.innerHTML = originalText;
            exportBtn.disabled = false;
            window.exportDownloadUrl = null;
            window.exportDownloadBlob = null;
            window.exportDownloadReady = false;
              // Reset closure biến
              window.resetExportButtonState && window.resetExportButtonState();
          }
        }, 7000);
        // Khi click Download, clear timeout
        exportBtn.addEventListener('click', function clearDownloadTimeout() {
          if (window.exportDownloadTimeout) {
            clearTimeout(window.exportDownloadTimeout);
            window.exportDownloadTimeout = null;
          }
          exportBtn.removeEventListener('click', clearDownloadTimeout);
        });
      } catch (e) {
        exportBtn.innerHTML = '<span style="color:#e11d48;font-weight:bold;">Error</span>';
        setTimeout(() => {
          exportBtn.innerHTML = originalText;
          exportBtn.disabled = false;
          downloadUrl = null;
          downloadBlob = null;
          downloadReady = false;
            window.resetExportButtonState && window.resetExportButtonState();
        }, 1800);
      }
    });
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

async function renderMLDetect() {
  // Hiển thị trạng thái loading
  const overview = document.getElementById('ml-overview-evaluation');
  if (overview) {
    overview.innerHTML = `
      <span>Risk Level Avg: <b style="color:#e11d48;">--</b></span><br>
      <span>Anomalies Detected: <b>--</b></span><br>
      <span>Avg. Anomaly Score: <b>--</b></span>
    `;
  }
  const contextDiv = document.getElementById('ml-context-render');
  if (contextDiv) contextDiv.innerHTML = `<b>--</b>`;

  // Render leaderboard loading
  const leaderboard = document.querySelector('.detect-grid .flex-end > div');
  if (leaderboard) {
    leaderboard.innerHTML = `
      <div id="ml-leaderboard-scroll" style="max-height:420px;overflow-y:auto;display:flex;flex-direction:column;gap:10px;">
        <div style="background:#f8c58e; border-radius:12px; padding:18px 16px; display:flex; align-items:center; gap:14px; font-size:1.1rem;">
          <div style="width:48px;height:48px;border-radius:50%;background:#eee;"></div>
          <div style="flex:1;">
            <div style="font-weight:bold;">--</div>
            <div style="font-size:0.9em;color:#888;">--</div>
          </div>
          <span style="font-weight:bold;color:#e11d48;font-size:1.2em;">--</span>
        </div>
        <div style="background:#cdcdcd; border-radius:10px; padding:8px 10px; display:flex; align-items:center; gap:8px; font-size:0.95rem; width:280px; margin-left:auto; justify-content:flex-end;">
          <div style="width:28px;height:28px;border-radius:50%;background:#eee;"></div>
          <div style="flex:1;">--</div>
          <span style="font-weight:bold;color:#80550a;">--</span>
        </div>
        <div style="background:#cdcdcd; border-radius:10px; padding:8px 10px; display:flex; align-items:center; gap:8px; font-size:0.95rem; width:280px; margin-left:auto; justify-content:flex-end;">
          <div style="width:28px;height:28px;border-radius:50%;background:#eee;"></div>
          <div style="flex:1;">--</div>
          <span style="font-weight:bold;color:#58e11d;">--</span>
        </div>
      </div>
    `;
  }
  try {
    const res = await fetch('http://127.0.0.1:8000/ueba/explain');
    console.log('API response:', res);
    const data = await res.json();
    console.log('API data:', data);

    // Render lại overview
    if (overview) {
      overview.innerHTML = `
        <span>Risk Level Avg: <b style="color:#e11d48;">${data.summary?.high_risk > 0 ? 'HIGH' : data.summary?.medium_risk > 0 ? 'MEDIUM' : 'LOW'}</b></span><br>
        <span>Anomalies Detected: <b>${data.anomalies_found ?? '--'}</b></span><br>
        <span>Avg. Anomaly Score: <b>${(data.explanations?.reduce((a, b) => a + b.anomaly_score, 0) / (data.explanations?.length || 1)).toFixed(3)}</b></span>
      `;
    }

    // Sau khi sort explanations:
    const sorted = [...(data.explanations ?? [])].sort((a, b) => a.anomaly_score - b.anomaly_score);

    // Render context cho top 1 (đúng thứ tự leaderboard)
    if (contextDiv && sorted.length > 0) {
      typeText(contextDiv, sorted[0].explanation);
    }

    // Render leaderboard
    const leaderboard = document.getElementById('ml-leaderboard');
    if (leaderboard) {
      leaderboard.innerHTML = '';
      // Tạo container scroll cho leaderboard
      const scrollDiv = document.createElement('div');
      scrollDiv.id = 'ml-leaderboard-scroll';
      scrollDiv.style.maxHeight = '282px';
      scrollDiv.style.overflowY = 'auto';
      scrollDiv.style.display = 'flex';
      scrollDiv.style.flexDirection = 'column';
      scrollDiv.style.gap = '10px';
      // Sắp xếp theo anomaly_score tăng dần (thấp nhất lên đầu)
      let selectedIdx = 0;
      // Nếu đã có contextDiv thì lấy context hiện tại
        if (contextDiv && contextDiv.dataset.selectedIdx) {
          selectedIdx = parseInt(contextDiv.dataset.selectedIdx, 10);
        }
        function getCardStyle(isActive, idx) {
        if (isActive) {
          return 'background:#f8c58e; border-radius:20px; padding:18px 16px; display:flex; align-items:center; gap:14px; box-shadow:0 2px 8px #0001; font-size:1.1rem; cursor:pointer;';
        } else {
          return 'background:#cdcdcd; border-radius:10px; padding:8px 10px; display:flex; align-items:center; gap:8px; font-size:0.95rem; width:280px; margin-left:auto; justify-content:flex-end; cursor:pointer;';
        }
      }
      scrollDiv.innerHTML = '';
      sorted.slice(0, 10).forEach((item, idx) => {
        let isActive = idx === selectedIdx;
        let cardStyle = getCardStyle(isActive, idx);
        let avatarUrl = item.avatar_url ? item.avatar_url : './assets/UnknowUser.png';
        const card = document.createElement('div');
        card.setAttribute('data-idx', idx);
        card.setAttribute('tabindex', 0);
        card.style.cssText = cardStyle;
        card.innerHTML = `
            <img src="${avatarUrl}" alt="Avatar" style="width:${idx===0?'48':'28'}px;height:${idx===0?'48':'28'}px;border-radius:50%;object-fit:cover;">
            <div style="flex:1;">
              <div style="font-weight:bold;">${item.full_name ?? '--'}</div>
              <div style="font-size:0.9em;color:#888;">${item.role ?? ''}</div>
            </div>
            <span style="font-weight:bold;color:${item.risk_level==='HIGH'?'#e11d48':item.risk_level==='MEDIUM'?'#e59915':'#58e11d'};">${item.anomaly_score?.toFixed(3) ?? '--'}</span>
        `;
        card.addEventListener('click', function() {
          // Bỏ active cũ
          scrollDiv.querySelectorAll('div[data-idx]').forEach((el, i) => {
            el.style.cssText = getCardStyle(false, i);
          });
          // Active mới
          card.style.cssText = getCardStyle(true, idx);
          // Render context
          if (contextDiv) {
            typeText(contextDiv, item.explanation);
            contextDiv.dataset.selectedIdx = idx;
          }
          // Cuộn card ra giữa vùng scroll, không ảnh hưởng scroll toàn trang
          const scrollParent = scrollDiv;
          const cardRect = card.getBoundingClientRect();
          const parentRect = scrollParent.getBoundingClientRect();
          // Kiểm tra nếu card đã nằm trong vùng nhìn thấy thì không cuộn nữa
          if (cardRect.top < parentRect.top || cardRect.bottom > parentRect.bottom) {
            // Tính toán vị trí để card ra giữa vùng scroll
            const offset = card.offsetTop - scrollParent.offsetTop - (scrollParent.clientHeight/2) + (card.clientHeight/2);
            scrollParent.scrollTo({top: offset, behavior: 'smooth'});
          }
        });
        scrollDiv.appendChild(card);
      });
      // Khi load lần đầu, set context đúng card đầu tiên
      if (contextDiv) contextDiv.dataset.selectedIdx = selectedIdx;
      // Thêm fade overlay cho card
      const fadeTop = document.createElement('div');
      fadeTop.id = 'ml-leaderboard-scroll-fade-top';
      const fadeBot = document.createElement('div');
      fadeBot.id = 'ml-leaderboard-scroll-fade-bottom';
      // Container bọc để fade overlay nằm trên card
      const wrap = document.createElement('div');
      wrap.style.position = 'relative';
      wrap.appendChild(scrollDiv);
      wrap.appendChild(fadeTop);
      wrap.appendChild(fadeBot);
      leaderboard.appendChild(wrap);
    }
  } catch (e) {
    console.error("ML Detect error:", e);
    if (overview) overview.innerHTML = `<span style="color:red;">Lỗi khi tải dữ liệu ML</span>`;
    if (contextDiv) contextDiv.innerHTML = `<b>--</b>`;
    if (leaderboard) leaderboard.innerHTML = '';
  }
}

const anomalyTable = document.getElementById('ml-anomaly-table');
if (anomalyTable) {
  anomalyTable.innerHTML = `
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr>
          <th>EmployeeID</th>
          <th>QueryTime</th>
          <th>Anomaly Score</th>
          <th>RowsExamined</th>
          <th>RowsReturned</th>
          <th>ExecutionTime</th>
          <th>QueryLength</th>
          <th>IsSensitive</th>
          <th>Type</th>
        </tr>
      </thead>
      <tbody>
        ${data.data.map(row => `
          <tr>
            <td>${row.EmployeeID ?? '--'}</td>
            <td>${row.QueryTime ?? '--'}</td>
            <td>${row.anomaly_score?.toFixed(3) ?? '--'}</td>
            <td>${row.RowsExamined ?? '--'}</td>
            <td>${row.RowsReturned ?? '--'}</td>
            <td>${row.ExecutionTime !== undefined ? (Number(row.ExecutionTime) % 1 === 0 ? Number(row.ExecutionTime) : Number(row.ExecutionTime).toFixed(3)) : '--'}</td>
            <td>${row.QueryLength ?? '--'}</td>
            <td>${row.IsSensitive ?? '--'}</td>
            <td>${row.query_type ?? '--'}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

