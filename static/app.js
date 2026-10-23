document.addEventListener("DOMContentLoaded", () => {
  const node = document.getElementById("chart-data");
  if (node && window.Chart) {
    let data = {};
    try { data = JSON.parse(node.textContent); } catch(e) {}
    const money = v => new Intl.NumberFormat("en-IN", {style:"currency",currency:data.currency || "INR",maximumFractionDigits:0}).format(v);
    const days = data.days || [];
    const cash = document.getElementById("cashFlowChart");
    if (cash) new Chart(cash, {
      type:"line",
      data:{labels:days.map(x=>x.date.slice(5)),datasets:[
        {label:"Income",data:days.map(x=>x.income),borderColor:"#51c6a4",backgroundColor:"rgba(81,198,164,.10)",fill:true,tension:.38,pointRadius:2,borderWidth:2},
        {label:"Expenses",data:days.map(x=>x.expense),borderColor:"#a78bfa",backgroundColor:"rgba(167,139,250,.08)",fill:true,tension:.38,pointRadius:2,borderWidth:2}
      ]},
      options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>`${c.dataset.label}: ${money(c.raw)}`}}},scales:{x:{grid:{display:false},ticks:{color:"#8990a6",maxTicksLimit:8}},y:{grid:{color:"rgba(140,145,170,.12)"},ticks:{color:"#8990a6",callback:v=>money(v)}}}}
    });
    const donut=document.getElementById("categoryChart");
    if(donut) new Chart(donut,{type:"doughnut",data:{labels:Object.keys(data.categories||{}),datasets:[{data:Object.values(data.categories||{}),backgroundColor:["#a78bfa","#5bd1b0","#f4bd70","#6eabff","#f18ba9","#7ed8df","#c3a2ff","#9ca3af"],borderWidth:0,hoverOffset:5}]},options:{responsive:true,maintainAspectRatio:false,cutout:"72%",plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>`${c.label}: ${money(c.raw)}`}}}}});
  }
  document.querySelectorAll(".flash").forEach(el => setTimeout(()=>{if(el.isConnected){el.style.opacity="0";setTimeout(()=>el.remove(),300)}},6500));
  const upload=document.querySelector('input[type="file"]');
  if(upload) upload.addEventListener("change",()=>{const label=upload.closest(".upload-zone");if(label&&upload.files[0]){const strong=label.querySelector("strong");if(strong)strong.textContent=upload.files[0].name;}});
});
