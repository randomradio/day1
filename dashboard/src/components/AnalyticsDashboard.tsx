import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { useConversationStore } from '../stores/conversationStore';
import { useBranchStore } from '../stores/branchStore';
import { useVisiblePolling } from '../hooks/usePolling';

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-white rounded-lg p-3 border border-gray-200 shadow-sm">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-lg font-bold text-gray-800">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function TrendChart({ data, color, label }: { data: Array<{ period: string; count: number }>; color: string; label: string }) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = svgRef.current.clientWidth;
    const height = 80;
    const margin = { top: 8, right: 8, bottom: 20, left: 30 };

    const x = d3.scaleBand()
      .domain(data.map((d) => d.period))
      .range([margin.left, width - margin.right])
      .padding(0.3);

    const y = d3.scaleLinear()
      .domain([0, d3.max(data, (d) => d.count) || 1])
      .range([height - margin.bottom, margin.top]);

    svg.selectAll('rect')
      .data(data)
      .enter()
      .append('rect')
      .attr('x', (d) => x(d.period)!)
      .attr('y', (d) => y(d.count))
      .attr('width', x.bandwidth())
      .attr('height', (d) => height - margin.bottom - y(d.count))
      .attr('fill', color)
      .attr('rx', 2)
      .attr('opacity', 0.8);

    svg.append('g')
      .attr('transform', `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(x).tickValues(data.filter((_, i) => i % Math.ceil(data.length / 5) === 0).map((d) => d.period)))
      .selectAll('text')
      .attr('fill', '#6b7280')
      .attr('font-size', '8px')
      .attr('transform', 'rotate(-30)')
      .attr('text-anchor', 'end');

    svg.append('g')
      .attr('transform', `translate(${margin.left},0)`)
      .call(d3.axisLeft(y).ticks(3))
      .selectAll('text')
      .attr('fill', '#6b7280')
      .attr('font-size', '9px');
  }, [data, color]);

  return (
    <div className="bg-gray-50 rounded p-2 border border-gray-100">
      <span className="text-xs text-gray-500">{label}</span>
      <svg ref={svgRef} className="w-full" height={80} />
    </div>
  );
}

export default function AnalyticsDashboard() {
  const { analytics, trends, fetchAnalytics, fetchTrends, loading, pollingEnabled } =
    useConversationStore();
  const { activeBranch } = useBranchStore();

  // Initial fetch
  useEffect(() => {
    fetchAnalytics(activeBranch === 'main' ? undefined : activeBranch);
    fetchTrends(30, 'day', activeBranch === 'main' ? undefined : activeBranch);
  }, [activeBranch, fetchAnalytics, fetchTrends]);

  // Polling for analytics (every 10 seconds to avoid excessive load)
  useVisiblePolling(
    () => {
      fetchAnalytics(activeBranch === 'main' ? undefined : activeBranch);
      fetchTrends(30, 'day', activeBranch === 'main' ? undefined : activeBranch);
    },
    10000,
    pollingEnabled
  );

  if (loading && !analytics) {
    return (
      <div className="bg-white rounded-lg p-4 border border-gray-200 shadow-sm">
        <p className="text-xs text-gray-500">Loading analytics...</p>
      </div>
    );
  }

  if (!analytics) {
    return (
      <div className="bg-white rounded-lg p-4 border border-gray-200 shadow-sm">
        <p className="text-xs text-gray-500">No analytics data available.</p>
      </div>
    );
  }

  const c = analytics.counts;
  const t = analytics.tokens;
  const con = analytics.consolidation;

  return (
    <div className="bg-white rounded-lg p-3 space-y-3 border border-gray-200 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-700 font-medium">Analytics</span>
        <span className="text-xs text-gray-500">{analytics.period_days}d window</span>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-5 gap-2">
        <StatCard label="Sessions" value={c.sessions || 0} />
        <StatCard label="Conversations" value={c.conversations || 0} />
        <StatCard label="Messages" value={c.messages || 0} />
        <StatCard label="Facts" value={c.facts || 0} />
        <StatCard
          label="Tokens"
          value={t.total.toLocaleString()}
          sub={`${t.avg_per_conversation.toFixed(0)} avg/conv`}
        />
      </div>

      {/* Consolidation stats */}
      <div className="grid grid-cols-4 gap-2">
        <StatCard label="Facts Created" value={con.facts_created} />
        <StatCard label="Facts Updated" value={con.facts_updated} />
        <StatCard label="Deduplicated" value={con.facts_deduplicated} />
        <StatCard
          label="Yield Rate"
          value={`${(con.yield_rate * 100).toFixed(1)}%`}
          sub={`${con.observations_processed} obs processed`}
        />
      </div>

      {/* Trend charts */}
      {trends && (
        <div className="grid grid-cols-3 gap-2">
          <TrendChart data={trends.messages} color="#3b82f6" label="Messages / day" />
          <TrendChart data={trends.facts} color="#22c55e" label="Facts / day" />
          <TrendChart data={trends.conversations} color="#f59e0b" label="Conversations / day" />
        </div>
      )}

      {/* Recent conversations */}
      {analytics.activity.recent_conversations.length > 0 && (
        <div>
          <span className="text-xs text-gray-500">Recent Activity</span>
          <div className="mt-1 space-y-1">
            {analytics.activity.recent_conversations.map((rc) => (
              <div key={rc.id} className="flex items-center justify-between text-xs bg-gray-50 rounded px-2 py-1 border border-gray-100">
                <span className="text-gray-800 truncate">{rc.title || rc.id.slice(0, 12)}</span>
                <div className="flex gap-2 text-gray-500">
                  <span>{rc.status}</span>
                  <span>{rc.message_count} msgs</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
