import { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import { useBranchStore } from '../stores/branchStore';

const CATEGORY_COLORS: Record<string, string> = {
  architecture: '#3b82f6',
  bug_fix: '#ef4444',
  preference: '#8b5cf6',
  code: '#22c55e',
  framework: '#f59e0b',
  database: '#06b6d4',
};

function getColor(category?: string): string {
  return CATEGORY_COLORS[category || ''] || '#9ca3af';
}

export default function Timeline() {
  const svgRef = useRef<SVGSVGElement>(null);
  const { facts, timeTravel, timeTravelTs } = useBranchStore();
  const [sliderValue, setSliderValue] = useState('');

  useEffect(() => {
    if (!svgRef.current || facts.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = svgRef.current.clientWidth;
    const height = 120;
    const margin = { top: 20, right: 20, bottom: 30, left: 20 };

    const dates = facts
      .filter((f) => f.created_at)
      .map((f) => new Date(f.created_at!));

    if (dates.length === 0) return;

    const xScale = d3
      .scaleTime()
      .domain(d3.extent(dates) as [Date, Date])
      .range([margin.left, width - margin.right]);

    const xAxis = d3.axisBottom(xScale).ticks(6).tickFormat(d3.timeFormat('%H:%M') as unknown as (d: d3.NumberValue, i: number) => string);

    svg
      .append('g')
      .attr('transform', `translate(0,${height - margin.bottom})`)
      .call(xAxis)
      .selectAll('text')
      .attr('fill', '#6b7280');

    svg
      .selectAll('circle')
      .data(facts.filter((f) => f.created_at))
      .enter()
      .append('circle')
      .attr('cx', (d) => xScale(new Date(d.created_at!)))
      .attr('cy', height / 2)
      .attr('r', 6)
      .attr('fill', (d) => getColor(d.category))
      .attr('opacity', 0.8)
      .append('title')
      .text(
        (d) =>
          `${d.fact_text.slice(0, 60)}${d.fact_text.length > 60 ? '...' : ''}\n${d.category || 'uncategorized'}`
      );
  }, [facts]);

  const handleTimeTravel = () => {
    if (sliderValue) {
      timeTravel(sliderValue);
    }
  };

  return (
    <div className="bg-white rounded-lg p-3 border border-gray-200 shadow-sm">
      <div className="flex items-center gap-3 mb-2">
        <span className="text-sm text-gray-600 font-medium">Timeline</span>
        <input
          type="datetime-local"
          className="bg-white text-gray-900 text-xs px-2 py-1 rounded border border-gray-300 focus:border-blue-500 focus:outline-none"
          value={sliderValue}
          onChange={(e) => setSliderValue(e.target.value)}
        />
        <button
          onClick={handleTimeTravel}
          disabled={!sliderValue}
          className="bg-cyan-600 text-white text-xs px-3 py-1 rounded hover:bg-cyan-700 disabled:opacity-50 shadow-sm"
        >
          Time Travel
        </button>
        {timeTravelTs && (
          <span className="text-xs text-cyan-600 font-medium">@ {timeTravelTs}</span>
        )}
      </div>
      <svg ref={svgRef} className="w-full" height={120} />
      <div className="flex gap-3 mt-1 flex-wrap">
        {Object.entries(CATEGORY_COLORS).map(([cat, color]) => (
          <span key={cat} className="flex items-center gap-1 text-xs text-gray-500">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ backgroundColor: color }}
            />
            {cat}
          </span>
        ))}
      </div>
    </div>
  );
}
