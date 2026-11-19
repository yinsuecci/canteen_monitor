import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, AriaComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { Series } from './types';
echarts.use([LineChart, GridComponent, TooltipComponent, AriaComponent, CanvasRenderer]);
const formatTime = (value: number) => new Intl.DateTimeFormat('zh-CN', { timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hour12:false }).format(value);
export default function Chart({ series, utilization }: {series: Series[]; utilization: boolean}) {
  const node = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!node.current) return;
    const chart = echarts.init(node.current);
    chart.setOption({
      animation: !matchMedia('(prefers-reduced-motion: reduce)').matches,
      color: ['#b64a20', '#78833f'], aria: {enabled: true},
      grid: {top:25,right:28,bottom:35,left:43},
      tooltip: {trigger:'axis',renderMode:'richText',backgroundColor:'#fffdf9',borderColor:'#ded8cf',textStyle:{color:'#34332e'},valueFormatter:(v: unknown) => v == null ? '缺失' : `${v}${utilization?'%':''}`},
      xAxis: {type:'time',axisLine:{lineStyle:{color:'#d2cdc4'}},axisTick:{show:false},axisLabel:{color:'#888378',formatter:formatTime,hideOverlap:true},splitNumber:4},
      yAxis: {type:'value',min:0,max:utilization?100:undefined,minInterval:utilization?undefined:1,axisLabel:{color:'#888378',formatter:utilization?'{value}%':'{value}'},splitLine:{lineStyle:{color:'#ebe6de',type:'dashed'}}},
      series: series.map((s,i) => ({type:'line',name:s.name,symbol:i===0?'circle':'diamond',symbolSize:7,showSymbol:true,connectNulls:false,lineStyle:{width:2,type:i===0?'solid':'dashed'},data:s.points.map(p=>[Date.parse(p.timestamp),utilization?(p.channel_utilization_raw == null?null:Math.round(p.channel_utilization_raw/255*1000)/10):p.station_count])})),
    });
    const observer = new ResizeObserver(()=>chart.resize()); observer.observe(node.current);
    return ()=>{ observer.disconnect(); chart.dispose(); };
  }, [series, utilization]);
  return <div className="chart-canvas" ref={node} role="img" aria-label={`${utilization?'信道利用率':'关联终端数'}历史曲线，上海时间。缺失数据断开显示。`}/>;
}
