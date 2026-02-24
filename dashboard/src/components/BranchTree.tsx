import { useCallback, useEffect, useMemo } from 'react';
import {
  ReactFlow,
  type Node,
  type Edge,
  useNodesState,
  useEdgesState,
  Background,
  Controls,
  type NodeMouseHandler,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useBranchStore } from '../stores/branchStore';
import type { Branch } from '../types/schema';

function branchColor(b: Branch, active: string): string {
  if (b.branch_name === active) return '#22c55e';
  if (b.status === 'merged') return '#9ca3af';
  if (b.branch_name === 'main') return '#3b82f6';
  return '#f59e0b';
}

export default function BranchTree() {
  const { branches, activeBranch, setActiveBranch, fetchBranches } =
    useBranchStore();

  useEffect(() => {
    fetchBranches();
  }, [fetchBranches]);

  const { initialNodes, initialEdges } = useMemo(() => {
    const levelMap: Record<string, number> = {};
    const childCount: Record<string, number> = {};

    // Build level map
    for (const b of branches) {
      if (b.branch_name === 'main') levelMap[b.branch_name] = 0;
    }
    let changed = true;
    while (changed) {
      changed = false;
      for (const b of branches) {
        if (levelMap[b.branch_name] === undefined && levelMap[b.parent_branch] !== undefined) {
          levelMap[b.branch_name] = levelMap[b.parent_branch] + 1;
          childCount[b.parent_branch] = (childCount[b.parent_branch] || 0) + 1;
          changed = true;
        }
      }
    }

    const xByParent: Record<string, number> = {};
    const nodes: Node[] = branches.map((b) => {
      const level = levelMap[b.branch_name] ?? 0;
      const idx = xByParent[b.parent_branch] || 0;
      xByParent[b.parent_branch] = idx + 1;

      return {
        id: b.branch_name,
        position: { x: idx * 220, y: level * 120 },
        data: {
          label: (
            <div className="text-sm font-medium px-2 py-1">
              <div>{b.branch_name}</div>
              <div className="text-xs opacity-70">{b.status}</div>
            </div>
          ),
        },
        style: {
          background: branchColor(b, activeBranch),
          color: '#fff',
          borderRadius: 8,
          border: b.branch_name === activeBranch ? '3px solid #1e40af' : '2px solid rgba(0,0,0,0.1)',
          minWidth: 140,
          boxShadow: b.branch_name === activeBranch ? '0 4px 12px rgba(59, 130, 246, 0.3)' : undefined,
        },
      };
    });

    const edges: Edge[] = branches
      .filter((b) => b.branch_name !== b.parent_branch)
      .map((b) => ({
        id: `${b.parent_branch}-${b.branch_name}`,
        source: b.parent_branch,
        target: b.branch_name,
        type: 'smoothstep',
        animated: b.status === 'active',
        style: { stroke: '#9ca3af', strokeWidth: 2 },
      }));

    return { initialNodes: nodes, initialEdges: edges };
  }, [branches, activeBranch]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const onNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      setActiveBranch(node.id);
    },
    [setActiveBranch]
  );

  return (
    <div className="h-full w-full bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        fitView
        minZoom={0.3}
        maxZoom={2}
      >
        <Background color="#e5e7eb" gap={20} />
        <Controls />
      </ReactFlow>
    </div>
  );
}
